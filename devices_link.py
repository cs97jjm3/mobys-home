"""
The TV and games consoles, for Moby's Home. Everything here works over the
home network, with no accounts or cloud logins.

Samsung TV (2016 or newer):
  - on / standby / off, read from the TV's own little web page on port 8001
  - which app is on screen (Netflix, YouTube...), or your usual source, e.g. "BT TV"
  - power off, volume and mute, and opening apps, over the TV's remote-control
    connection (port 8002). The first time, the TV asks you to Allow it.
  - power on with a Wake-on-LAN message (needs "Power On with Mobile" on the TV)

PS5: asks the console directly, the same way the PS Remote Play app finds it.
  Answers "on" or "rest mode", and often the name of the game that's running.

TV box (BT / EE TV Box Pro): asks which streaming app it's running (Netflix,
  YouTube). Live TV and standby both show as nothing running. With its MAC
  address, the BT Smart Hub's device list shows when it's streaming any other app.

Xbox: asks the console directly, the same way the Xbox app finds it. If it
  doesn't answer but is still on the network, it's asleep.
"""

import asyncio
import platform
import socket
import struct
import re
import time
import urllib.parse
from pathlib import Path

import aiohttp


# ---------- Wake-on-LAN ----------

def wake_on_lan(mac):
    """Send the 'wake up' message for a device's MAC address."""
    hex_mac = mac.replace(":", "").replace("-", "").strip()
    if len(hex_mac) != 12:
        raise ValueError("The TV's MAC address isn't set")
    packet = b"\xff" * 6 + bytes.fromhex(hex_mac) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for target in ("255.255.255.255", "192.168.1.255"):
            try:
                s.sendto(packet, (target, 9))
            except OSError:
                pass


# ---------- a quick UDP question-and-answer ----------

class _Reply(asyncio.DatagramProtocol):
    def __init__(self, ip):
        self.ip, self.future = ip, asyncio.get_running_loop().create_future()

    def datagram_received(self, data, addr):
        if addr[0] == self.ip and not self.future.done():
            self.future.set_result(data)

    def error_received(self, exc):
        if not self.future.done():
            self.future.set_result(None)


async def udp_ask(ip, port, message, local_port=0, timeout=1.5, tries=2):
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: _Reply(ip), local_addr=("0.0.0.0", local_port), reuse_port=None,
        allow_broadcast=False)
    try:
        for _ in range(tries):
            transport.sendto(message, (ip, port))
            try:
                return await asyncio.wait_for(asyncio.shield(protocol.future), timeout)
            except asyncio.TimeoutError:
                continue
        return None
    finally:
        transport.close()


async def on_network(ip):
    """True if the device answers a ping."""
    count = "-n" if platform.system() == "Windows" else "-c"
    wait = ["-w", "800"] if platform.system() == "Windows" else ["-W", "1"]
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", count, "1", *wait, ip,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        return await asyncio.wait_for(proc.wait(), 5) == 0
    except (OSError, asyncio.TimeoutError):
        return False


# ---------- PS5 ----------

PS5_PORT = 9302
PS5_LOCAL_PORT = 9303   # the PS5 only answers questions sent from this port
PS5_SEARCH = b"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:00030010\n"


def parse_ps5(reply):
    """Turn the PS5's reply into {"state": "on"/"rest", "game": ..., "name": ...}."""
    text = reply.decode("utf-8", "replace")
    info = {}
    for line in text.splitlines():
        if line.startswith("HTTP/1.1"):
            parts = line.split(" ", 2)
            info["code"] = parts[1] if len(parts) > 1 else ""
        elif ":" in line:
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
    state = "on" if info.get("code") == "200" else "rest" if info.get("code") == "620" else "unknown"
    return {"state": state, "game": info.get("running-app-name") or None,
            "name": info.get("host-name") or None}


async def ps5_status(ip, lock):
    async with lock:   # only one question at a time can use port 9303
        try:
            reply = await udp_ask(ip, PS5_PORT, PS5_SEARCH, local_port=PS5_LOCAL_PORT)
        except OSError:
            reply = None
    if reply:
        return parse_ps5(reply)
    return {"state": "off", "game": None, "name": None}


# ---------- Xbox ----------

XBOX_PORT = 5050
# SmartGlass discovery request: header (type 0xDD00, 10-byte payload, version 0),
# then flags 0, client type 8 (Android), versions 0 to 2
XBOX_SEARCH = struct.pack(">HHH", 0xDD00, 10, 0) + struct.pack(">IHHH", 0, 8, 0, 2)


def parse_xbox(reply):
    """Pull the console's name out of a discovery reply."""
    try:
        if struct.unpack(">H", reply[:2])[0] != 0xDD01:
            return None
        offset = 6 + 4 + 2           # header, flags, device type
        length = struct.unpack(">H", reply[offset:offset + 2])[0]
        return reply[offset + 2:offset + 2 + length].decode("utf-8", "replace")
    except (struct.error, IndexError):
        return None


async def xbox_status(ip):
    try:
        reply = await udp_ask(ip, XBOX_PORT, XBOX_SEARCH)
    except OSError:
        reply = None
    if reply and reply[:2] == b"\xdd\x01":
        return {"state": "on", "name": parse_xbox(reply)}
    if await on_network(ip):
        return {"state": "asleep", "name": None}
    return {"state": "off", "name": None}


# ---------- TV box (BT / EE TV Box Pro, and others that speak DIAL) ----------

BOX_PORT = 56789
BOX_APPS = ["Netflix", "YouTube"]
# Some apps only answer when the question says it comes from them
BOX_ORIGINS = [None, "https://www.youtube.com", "https://www.netflix.com"]


def parse_dial_state(xml):
    """Pull <state> out of a DIAL app reply: running, stopped or hidden."""
    start, end = xml.find("<state>"), xml.find("</state>")
    return xml[start + 7:end].strip().lower() if start != -1 and end > start else None


class TVBox:
    """Asks the TV box which streaming app is running. Live TV or standby shows as nothing running."""

    def __init__(self, ip):
        self.ip = ip
        self.origin = {}   # app -> the Origin header it accepted

    async def _state(self, session, app):
        tries = [self.origin[app]] if app in self.origin else BOX_ORIGINS
        for origin in tries:
            try:
                async with session.get(f"http://{self.ip}:{BOX_PORT}/apps/{app}",
                                       headers={"Origin": origin} if origin else {},
                                       timeout=aiohttp.ClientTimeout(total=3)) as r:
                    if r.status == 403:
                        continue
                    if r.status != 200:
                        return None
                    self.origin[app] = origin
                    return parse_dial_state(await r.text())
            except Exception:
                return "unreachable"
        return None

    async def status(self, session):
        states = await asyncio.gather(*(self._state(session, a) for a in BOX_APPS))
        if all(s == "unreachable" for s in states):
            return {"reachable": False, "app": None}
        running = [a for a, s in zip(BOX_APPS, states) if s == "running"]
        return {"reachable": True, "app": running[0] if running else None}


# ---------- BT Smart Hub: how much each device is downloading ----------

STREAMING_MBPS = 1.5   # above this, the box is streaming; live channels from the aerial are near 0


class HubTraffic:
    """Reads the BT Smart Hub's device list (no password needed) and works out the box's download speed."""

    def __init__(self, hub_ip, mac):
        self.hub_ip = hub_ip
        self.mac = mac.lower().replace("-", ":")
        self.last = None   # (time, bytes received)
        self.mbps = None

    @staticmethod
    def parse(body, mac):
        for found, tx, rx in re.findall(r"mac:'([^']+)',tx:'(\d+)',rx:'(\d+)'", body):
            if urllib.parse.unquote(found).lower() == mac:
                return int(rx)
        return None

    async def status(self, session):
        url = f"http://{self.hub_ip}/cgi/cgi_basicMyDevice.js"
        async with session.get(url, headers={"Referer": f"http://{self.hub_ip}/"},
                               timeout=aiohttp.ClientTimeout(total=6)) as r:
            body = await r.text(errors="replace")
        rx, now = self.parse(body, self.mac), time.time()
        if rx is not None and self.last and now > self.last[0] and rx >= self.last[1]:
            self.mbps = (rx - self.last[1]) * 8 / (now - self.last[0]) / 1e6
        elif rx is None:
            self.mbps = None
        if rx is not None:
            self.last = (now, rx)
        return {"mbps": round(self.mbps, 1) if self.mbps is not None else None,
                "streaming": self.mbps is not None and self.mbps >= STREAMING_MBPS}


# ---------- Samsung TV ----------

# Samsung's app numbers for the main apps. Checked on our 2023 TV; any the TV doesn't
# have just answer "not found" and are skipped.
KNOWN_APPS = {
    "3201907018807": "Netflix", "111299001912": "YouTube", "3201910019365": "Prime Video",
    "3201901017640": "Disney+", "3201807016597": "Apple TV", "3201606009684": "Spotify",
}

FAVOURITE_APPS = ["Netflix", "YouTube", "Prime Video", "Disney+", "BBC iPlayer", "ITVX",
                  "Channel 4", "My5", "Apple TV", "NOW", "Spotify", "Plex", "F1 TV"]


class SamsungTV:
    def __init__(self, ip, mac, token_file, default_source=""):
        self.ip, self.mac = ip, mac
        self.default_source = default_source   # what's on when no app is showing, e.g. "BT TV"
        self.token_file = Path(token_file)
        self.apps = []
        self.apps_fetched = 0
        self.needs_allow = False

    def _remote(self, timeout=8):
        from samsungtvws import SamsungTVWS
        return SamsungTVWS(self.ip, port=8002, token_file=str(self.token_file),
                           name="Moby's Home", timeout=timeout)

    async def _device_info(self, session):
        """The TV's own info page: plain on 8001 on most TVs, secure on 8002 on some newer ones."""
        for url, ssl in ((f"http://{self.ip}:8001/api/v2/", None),
                         (f"https://{self.ip}:8002/api/v2/", False)):
            try:
                async with session.get(url, ssl=ssl, timeout=aiohttp.ClientTimeout(total=2.5)) as r:
                    data = await r.json(content_type=None)
                if isinstance(data, dict) and (data.get("device") or data.get("name")):
                    return data
            except Exception:
                continue
        return None

    async def _port_open(self, port):
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(self.ip, port), 1.5)
            writer.close()
            return True
        except Exception:
            return False

    async def status(self, session):
        data = await self._device_info(session)
        if data:
            device = data.get("device") or {}
            state = (device.get("PowerState") or "on").lower()
            result = {"state": "on" if state == "on" else "standby",
                      "name": device.get("name") or data.get("name"),
                      "model": device.get("modelName")}
        elif await self._port_open(8002):
            # It answers but won't say more: it's on (or at least awake on the network)
            result = {"state": "on", "name": None, "model": None}
        else:
            result = {"state": "off", "name": None, "model": None}
        # Fetch the app list in the background, so it never slows the status check down
        if (result["state"] == "on" and time.time() - self.apps_fetched > 6 * 3600
                and not getattr(self, "_loading", False)):
            self._loading = True
            self.apps_fetched = time.time() - 6 * 3600 + 300   # retry in 5 minutes if it fails
            asyncio.create_task(self._load_apps_quietly())
        if result["state"] == "on":
            result["watching"] = await self._on_screen(session) or self.default_source or None
        result["apps"] = self.apps
        result["needs_allow"] = self.needs_allow and not self.token_file.exists()
        return result

    async def _app_state(self, session, app_id):
        try:
            async with session.get(f"http://{self.ip}:8001/api/v2/applications/{app_id}",
                                   timeout=aiohttp.ClientTimeout(total=2.5)) as r:
                if r.status != 200:
                    return None
                return await r.json(content_type=None)
        except Exception:
            return None

    async def _on_screen(self, session):
        """The app that's on screen right now, if any. Nothing means another input, like the BT box."""
        ids = list(dict.fromkeys(list(KNOWN_APPS) + [a["id"] for a in self.apps]))
        answers = await asyncio.gather(*(self._app_state(session, i) for i in ids))
        installed = []
        showing = None
        for app_id, info in zip(ids, answers):
            if not isinstance(info, dict):
                continue
            name = KNOWN_APPS.get(app_id) or info.get("name") or "an app"
            installed.append({"id": app_id, "name": name})
            if info.get("visible") and not showing:
                showing = name
        # Some TVs never send their full app list, so offer the main apps we know are there
        if not self.apps and installed:
            self.apps = installed
        return showing

    async def _run(self, action, timeout=8):
        def work():
            remote = self._remote(timeout)
            try:
                return action(remote)
            finally:
                remote.close()
        try:
            result = await asyncio.to_thread(work)
            self.needs_allow = False
            return result
        except Exception:
            if not self.token_file.exists():
                self.needs_allow = True
            raise

    async def _load_apps_quietly(self):
        try:
            await asyncio.wait_for(self.load_apps(), 30)
        except Exception:
            pass
        finally:
            self._loading = False

    async def load_apps(self):
        try:
            found = await self._run(lambda r: r.app_list(), timeout=15) or []
        except Exception:
            return
        def rank(app):
            name = app.get("name", "")
            return (FAVOURITE_APPS.index(name) if name in FAVOURITE_APPS else 99, name.lower())
        self.apps = [{"id": a.get("appId"), "name": a.get("name")}
                     for a in sorted(found, key=rank) if a.get("appId") and a.get("name")]
        self.apps_fetched = time.time()

    async def act(self, action, app_id=None):
        if action == "power_on":
            wake_on_lan(self.mac)
            # A TV in standby that's still on the network may need a nudge as well
            await asyncio.sleep(4)
            async with aiohttp.ClientSession() as session:
                if (await self.status(session))["state"] == "standby":
                    await self._run(lambda r: r.send_key("KEY_POWER"))
            return
        keys = {"power_off": "KEY_POWER", "volume_up": "KEY_VOLUP",
                "volume_down": "KEY_VOLDOWN", "mute": "KEY_MUTE"}
        if action in keys:
            await self._run(lambda r: r.send_key(keys[action]))
        elif action == "app" and app_id:
            await self._run(lambda r: r.run_app(app_id))
        else:
            raise ValueError(f"Unknown TV action: {action}")


class Devices:
    """Keeps the latest state of the TV and consoles."""

    def __init__(self, config, folder):
        self.config = config
        self.tv = (SamsungTV(config["tv_ip"], config["tv_mac"], Path(folder) / "samsung_token.txt",
                             config.get("tv_default", ""))
                   if config.get("tv_ip") else None)
        self.box = TVBox(config["box_ip"]) if config.get("box_ip") else None
        self.traffic = (HubTraffic(config.get("hub_ip") or "192.168.1.254", config["box_mac"])
                        if config.get("box_mac") else None)
        self.ps5_lock = asyncio.Lock()
        self.state = {}

    async def refresh(self, session):
        jobs, names = [], []
        if self.tv:
            jobs.append(self.tv.status(session)); names.append("tv")
        if self.box:
            jobs.append(self.box.status(session)); names.append("box")
        if self.traffic:
            jobs.append(self.traffic.status(session)); names.append("traffic")
        if self.config.get("ps5_ip"):
            jobs.append(ps5_status(self.config["ps5_ip"], self.ps5_lock)); names.append("ps5")
        if self.config.get("xbox_ip"):
            jobs.append(xbox_status(self.config["xbox_ip"])); names.append("xbox")
        results = await asyncio.gather(*(asyncio.wait_for(j, 15) for j in jobs),
                                       return_exceptions=True)
        for name, result in zip(names, results):
            if isinstance(result, Exception):
                print(f"{name}: {result or 'no answer in time'}")
            else:
                self.state[name] = result
        self.state["updated"] = time.time()

    def snapshot(self):
        out = {}
        labels = {"tv": self.config.get("tv_name") or "TV",
                  "ps5": self.config.get("ps5_name") or "PS5",
                  "xbox": self.config.get("xbox_name") or "Xbox"}
        for key in ("tv", "ps5", "xbox"):
            if key in self.state:
                out[key] = dict(self.state[key], label=labels[key])
        # When the TV is showing the box, say which app the box is running, e.g. "BT TV · Netflix"
        tv, box = out.get("tv"), self.state.get("box") or {}
        traffic = self.state.get("traffic") or {}
        what = box.get("app") or ("streaming" if traffic.get("streaming") else None)
        if tv and tv.get("state") == "on" and what:
            default = self.tv.default_source if self.tv else ""
            if tv.get("watching") in (None, "", default):
                tv["watching"] = f"{default} · {what}" if default else what
        return out
