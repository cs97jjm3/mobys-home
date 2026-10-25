"""
Who's home, and which computers are on, from the BT Smart Hub's device list.
No password needed: the hub shares this list with anything on the home network.

People are tracked by their phone being on the Wi-Fi. Phones nap off the
Wi-Fi now and then to save battery, so someone only shows as "out" after
their phone has been gone for a while.

Computers show on or off, and "busy" when they're moving a lot of data.
"""

import asyncio
import re
import time
import urllib.parse
from pathlib import Path

import aiohttp

OUT_AFTER = 10 * 60      # seconds a phone must be gone before we say "out"
BUSY_MBPS = 2.0          # a computer moving more than this is "busy"


def clean_mac(mac):
    return mac.strip().lower().replace("-", ":")


def hub_time(text):
    """The hub writes times like 2026/10/25 16:31:52, in UK time."""
    try:
        return time.mktime(time.strptime(text, "%Y/%m/%d %H:%M:%S"))
    except (TypeError, ValueError):
        return None


def this_computer():
    """Processor, memory, disk and time switched on, for the PC running Moby's Home. Needs psutil."""
    try:
        import psutil
    except ImportError:
        return None, set()
    macs = set()
    for addrs in psutil.net_if_addrs().values():
        for a in addrs:
            if getattr(a, "family", None) == getattr(psutil, "AF_LINK", -1) and a.address:
                macs.add(clean_mac(a.address))
    disk = psutil.disk_usage(Path(__file__).resolve().anchor or "/")   # the drive Moby's Home is on
    stats = {"cpu": round(psutil.cpu_percent(interval=None)), "memory": round(psutil.virtual_memory().percent),
             "disk_free_gb": round(disk.free / 1e9), "disk_used": round(disk.percent),
             "uptime": int(time.time() - psutil.boot_time())}
    return stats, macs


def parse_hub(body):
    """Turn the hub's device list into {mac: {"name", "ip", "connected", "rx", "tx"}}."""
    devices = {}
    for entry in re.findall(r"\{[^{}]*mac:'[^']+'[^{}]*\}", body):
        fields = {k: urllib.parse.unquote(v) for k, v in re.findall(r"(\w+):'([^']*)'", entry)}
        mac = clean_mac(fields.get("mac", ""))
        if not mac:
            continue
        d = devices.setdefault(mac, {})
        if "activity" in fields:
            d["name"] = fields.get("hostname") or fields.get("name")
            d["ip"] = fields.get("ip")
            d["connected"] = fields.get("activity") == "1"
            port = fields.get("port", "")
            d["link"] = "Wi-Fi" if port.startswith("wl") else "Cable" if port.startswith("eth") else None
            d["last_seen"] = hub_time(fields.get("time_last_active"))
        if "rx" in fields:
            d["rx"], d["tx"] = int(fields["rx"] or 0), int(fields.get("tx") or 0)
    return devices


class HomeNetwork:
    def __init__(self, hub_ip, people, computers):
        self.hub_ip = hub_ip
        self.people = {name: clean_mac(mac) for name, mac in people.items()}
        self.computers = {name: clean_mac(mac) for name, mac in computers.items()}
        self.last_home = {}     # name -> last time the phone was seen
        self.changed = {}       # name -> when they last arrived or left
        self.was_home = {}
        self.counts = {}        # mac -> (time, rx + tx)
        self.speed = {}         # mac -> Mbit/s
        self.devices = {}
        self.error = None
        self.updated = None
        self.local_stats, self.local_macs = None, set()

    @property
    def enabled(self):
        return bool(self.people or self.computers)

    async def refresh(self, session):
        if not self.enabled:
            return
        headers = {"Referer": f"http://{self.hub_ip}/", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            async with session.get(f"http://{self.hub_ip}/cgi/cgi_basicMyDevice.js", headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                body = await r.text(errors="replace")
        except Exception as err:
            self.error = f"Couldn't read the hub ({err.__class__.__name__})"
            return
        self.update(parse_hub(body), time.time())
        try:
            self.local_stats, self.local_macs = await asyncio.to_thread(this_computer)
        except Exception:
            self.local_stats, self.local_macs = None, set()

    def update(self, devices, now):
        """Work out who's home and how busy each computer is. Separate so it can be tested."""
        if not devices:
            self.error = "The hub didn't send its device list"
            return
        self.devices, self.error, self.updated = devices, None, now
        for mac in self.computers.values():
            d = devices.get(mac, {})
            if "rx" in d:
                total = d["rx"] + d["tx"]
                if mac in self.counts and now > self.counts[mac][0] and total >= self.counts[mac][1]:
                    self.speed[mac] = (total - self.counts[mac][1]) * 8 / (now - self.counts[mac][0]) / 1e6
                self.counts[mac] = (now, total)
        for name, mac in self.people.items():
            if devices.get(mac, {}).get("connected"):
                self.last_home[name] = now
            home = now - self.last_home.get(name, 0) < OUT_AFTER
            if self.was_home.get(name) is not None and self.was_home[name] != home:
                self.changed[name] = now if home else self.last_home.get(name, now)
            self.was_home[name] = home

    def snapshot(self):
        if not self.enabled:
            return None
        people = []
        for name, mac in self.people.items():
            if self.updated is None:
                people.append({"name": name, "home": None, "since": None})
                continue
            home = self.was_home.get(name, False)
            people.append({"name": name, "home": home, "since": self.changed.get(name)})
        computers = []
        for name, mac in self.computers.items():
            d = self.devices.get(mac, {})
            mbps = self.speed.get(mac)
            on = bool(d.get("connected"))
            item = {"name": name, "on": on if self.updated else None,
                    "busy": on and mbps is not None and mbps >= BUSY_MBPS,
                    "mbps": round(mbps, 1) if on and mbps is not None else None,
                    "ip": d.get("ip") if on else None, "link": d.get("link"),
                    "last_seen": d.get("last_seen") if not on else None}
            if mac in self.local_macs and self.local_stats:
                item["stats"] = self.local_stats
            computers.append(item)
        return {"people": people, "computers": computers, "error": self.error, "updated": self.updated}
