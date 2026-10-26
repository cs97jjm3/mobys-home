"""
The connection to Alexa for Moby's Home.

Logs in with the saved login from alexa_peek.py (alexa_login.json), then:
  - lists every device on the account and reads their current state
  - switches lights and plugs on and off, and sets brightness, using the
    same request the Alexa app and website use, so the Echo stays quiet
  - lists and runs your Alexa routines

This uses aioamazondevices, the library behind Home Assistant's Alexa Devices
integration, plus two of Amazon's own website requests for the parts it
doesn't cover. Alexa has no official API for this, so Amazon could change
something and break it without warning.
"""

import asyncio
import json
import time
from pathlib import Path

import aiohttp
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import REQUEST_AGENT, URI_NEXUS_GRAPHQL
from aioamazondevices.const.queries import QUERY_DEVICE_DATA
from aioamazondevices.structures import AmazonMediaControls, AmazonSaveDataConfig

MEDIA_COMMANDS = {"play": AmazonMediaControls.Play, "pause": AmazonMediaControls.Pause,
                  "next": AmazonMediaControls.Next, "previous": AmazonMediaControls.Previous,
                  "stop": AmazonMediaControls.Stop}

# How often to refresh, in seconds. Amazon limits how often you can ask, so
# don't make these much shorter.
STATE_EVERY = 60          # on/off, motion, light levels
DEVICE_LIST_EVERY = 900   # the list of devices and Echos
ROUTINES_EVERY = 3600
ECHO_STATUS_EVERY = 45    # what's playing, volume, Do Not Disturb, alarms and timers

# Types of device we can switch, and what to call them on the page
SWITCHABLE = {"LIGHT": "Light", "SMARTPLUG": "Plug", "SWITCH": "Switch", "FAN": "Fan"}

SET_FEATURES = """
mutation setEndpointFeatures($requests: [FeatureControlRequest!]!) {
  setEndpointFeatures(setEndpointFeaturesInput: { featureControlRequests: $requests }) {
    featureControlResponses { endpointId featureName featureOperationName code }
    errors { endpointId featureName featureOperationName code message }
  }
}
"""


def text(node, key):
    """Pull the text out of Alexa's nested {"value": {"text": ...}} shape."""
    return (((node or {}).get(key) or {}).get("value") or {}).get("text")


def iso_to_ts(value):
    """Alexa's '2026-10-25T10:01:02.123Z' -> seconds since 1970, or None."""
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_features(endpoint_features):
    """
    Turn Alexa's feature list for one device into a plain dict:
      {"power": "ON", "power_changed": ts, "brightness": 60, "can_dim": True,
       "motion": "DETECTED", "motion_changed": ts, "lux": 27.0,
       "temperature": 19.5, "reachable": True, "can_switch": True}
    """
    out = {}
    for feature in (endpoint_features or {}).get("features") or []:
        ops = {o.get("name") for o in feature.get("operations") or [] if o}
        name = feature.get("name")
        if name == "power" and ops & {"turnOn", "turnOff"}:
            out["can_switch"] = True
        if name == "brightness" and "setBrightness" in ops:
            out["can_dim"] = True
        if name == "color" and "setColor" in ops:
            out["can_colour"] = True
        if name == "colorTemperature" and "setColorTemperature" in ops:
            out["can_white"] = True
        for prop in feature.get("properties") or []:
            if prop.get("error"):
                continue
            changed = iso_to_ts(prop.get("timeOfLastChange"))
            if "powerStateValue" in prop:
                out["power"] = prop["powerStateValue"]
                out["power_changed"] = changed
            elif "brightnessStateValue" in prop:
                out["brightness"] = prop["brightnessStateValue"]
            elif prop.get("colorStateValue"):
                c = prop["colorStateValue"]
                if c.get("saturation"):          # 0 saturation means it's on white, not a colour
                    out["hue"], out["saturation"] = round(c.get("hue") or 0), c.get("saturation")
            elif "detectionStateValue" in prop:
                out["motion"] = prop["detectionStateValue"]
                out["motion_changed"] = changed
            elif "illuminanceValue" in prop:
                out["lux"] = (prop["illuminanceValue"] or {}).get("value")
            elif "reachabilityStatusValue" in prop:
                out["reachable"] = prop["reachabilityStatusValue"] == "OK"
            elif prop.get("__typename") == "TemperatureSensor" and prop.get("value"):
                out["temperature"] = prop["value"].get("value")
            elif "toggleStateValue" in prop:
                out["toggle"] = prop["toggleStateValue"]
    return out


def control_error(response):
    """Return Amazon's error message from a setEndpointFeatures reply, or None."""
    result = ((response or {}).get("data") or {}).get("setEndpointFeatures") or {}
    errors = result.get("errors") or []
    if errors:
        first = errors[0]
        return first.get("message") or first.get("code") or "Alexa refused the change"
    if (response or {}).get("errors"):
        return response["errors"][0].get("message", "Alexa refused the change")
    if not result.get("featureControlResponses"):
        return "Alexa didn't confirm the change"
    return None


class Alexa:
    def __init__(self, login_file, data_dir, routine_echo=""):
        self.routine_echo = routine_echo.strip().lower()
        self.login_file = Path(login_file)
        self.data_dir = Path(data_dir)
        self.http = None
        self.api = None
        self.lock = asyncio.Lock()
        self.endpoints = []        # raw device list
        self.states = {}           # endpoint id -> read_features() output
        self.echos = []
        self.routines = []
        self.updated = {"devices": 0, "states": 0, "routines": 0, "echo_status": 0}
        self.devices = {}          # serial number -> AmazonDevice
        self.echo_status = {}      # serial number -> playing, volume, dnd, next alarm/timer
        self.error = None

    # ----- login -----
    async def start(self):
        if not self.login_file.exists():
            raise RuntimeError("alexa_login.json is missing. Run alexa_peek.py once to log in.")
        saved = json.loads(self.login_file.read_text())
        self.data_dir.mkdir(exist_ok=True)
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self.api = AmazonEchoApi(self.http, saved["email"], "",
                                 save_data=AmazonSaveDataConfig(path=self.data_dir),
                                 login_data=saved["login"])
        await self.api.login.login_mode_stored_data()
        self._email = saved["email"]
        self._saved_login = json.dumps(saved["login"], sort_keys=True)

    def save_login_if_changed(self):
        """Amazon refreshes its tokens now and then; keep the file up to date."""
        current = self.api._session_state_data.login_stored_data
        as_text = json.dumps(current, sort_keys=True, default=str)
        if as_text != self._saved_login:
            self.login_file.write_text(json.dumps({"email": self._email, "login": current},
                                                  default=str))
            self._saved_login = as_text

    async def stop(self):
        if self.http:
            await self.http.close()

    # ----- raw requests -----
    async def _graphql(self, payload, what):
        session = self.api._session_state_data
        _, raw = await self.api._http_wrapper.session_request(
            method="POST",
            url=URL.joinpath(session.alexa_website_url, URI_NEXUS_GRAPHQL),
            input_data=payload,
            json_data=True,
            extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
        )
        return await self.api._http_wrapper.response_to_json(raw, what)

    # ----- reading -----
    async def refresh(self, force=False):
        """Bring everything up to date, without asking Amazon too often."""
        async with self.lock:
            now = time.time()
            try:
                if force or now - self.updated["devices"] > DEVICE_LIST_EVERY:
                    data = await self._graphql(
                        {"operationName": "getDevicesBaseData", "query": QUERY_DEVICE_DATA},
                        "endpoints")
                    self.endpoints = (((data.get("data") or {}).get("listEndpoints") or {})
                                      .get("endpoints") or [])
                    devices = await self.api.get_devices_data()
                    self.devices = dict(devices)
                    self.echos = [{
                        "serial": d.serial_number, "name": d.account_name, "model": d.model,
                        "online": d.online, "family": d.device_family,
                        "media": bool(d.media_player_supported),
                    } for d in devices.values() if d.device_family != "WHA"]
                    self.updated["devices"] = now

                if force or now - self.updated["states"] > STATE_EVERY:
                    ids = [e["endpointId"] for e in self.endpoints if e.get("endpointId")]
                    features = {}
                    for start in range(0, len(ids), 25):
                        features.update(await self.api._device_handler._get_endpoints_features(
                            ids[start:start + 25]))
                    self.states = {eid: read_features(f) for eid, f in features.items()}
                    self.updated["states"] = now

                if self.devices and (force or now - self.updated["echo_status"] > ECHO_STATUS_EVERY):
                    await self._refresh_echo_status()
                    self.updated["echo_status"] = now

                if force or now - self.updated["routines"] > ROUTINES_EVERY:
                    await self.api.update_routines()
                    self.routines = sorted(r.strip() for r in self.api.routines)
                    self.updated["routines"] = now

                self.error = None
                self.save_login_if_changed()
            except Exception as err:
                self.error = str(err) or err.__class__.__name__
                raise

    async def _refresh_echo_status(self):
        api = self.api
        try:
            await api.sync_media_state()
            media = await api._media_handler.media_states
            volumes = await api._media_handler.device_volumes
        except Exception as err:
            print(f"Alexa: couldn't read what's playing ({err})")
            media, volumes = {}, {}
        try:
            await api.sync_dnd_state()
            dnd = dict(api._dnd_handler.dnd_states)
        except Exception:
            dnd = {}
        try:
            schedules = await api._notification_handler.get_notifications() or {}
        except Exception:
            schedules = {}

        status = {}
        for serial in self.devices:
            m = media.get(serial)
            v = volumes.get(serial)
            upcoming = []
            for kind, sched in (schedules.get(serial) or {}).items():
                when = getattr(sched, "next_occurrence", None)
                if when is not None:
                    upcoming.append({"kind": kind, "label": getattr(sched, "label", "") or "",
                                     "at": when.timestamp()})
            upcoming.sort(key=lambda x: x["at"])
            status[serial] = {
                "playing": (m.player_state or "").upper() == "PLAYING" if m else False,
                "title": (m.now_playing_title or m.now_playing_line1) if m else None,
                "subtitle": (m.now_playing_line2 or m.media_provider) if m else None,
                "art": m.now_playing_url if m else None,
                "can_next": bool(m and m.next_enabled), "can_pause": bool(m and m.pause_enabled),
                "has_media": bool(m and (m.now_playing_title or m.now_playing_line1)),
                "volume": v.volume if v else None,
                "muted": v.is_muted if v else None,
                "dnd": dnd.get(serial),
                "next": upcoming[0] if upcoming else None,
            }
        self.echo_status = status

    def snapshot(self, hidden=()):
        """Everything the page needs, grouped and tidied."""
        hidden = {h.strip().lower() for h in hidden if h.strip()}
        switches, sensors, other = [], [], []
        for e in self.endpoints:
            name = text(e, "friendlyNameObject") or "Unnamed"
            if name.lower() in hidden:
                continue
            meta = e.get("alexaEnabledMetadata") or {}
            if meta.get("category") == "APP":
                continue
            kind = ((e.get("displayCategories") or {}).get("primary") or {}).get("value") or ""
            state = self.states.get(e.get("endpointId"), {})
            item = {
                "id": e.get("endpointId"),
                "name": name,
                "kind": kind,
                "maker": text(e, "manufacturer") or "",
                "reachable": state.get("reachable", True),
                **{k: v for k, v in state.items() if k != "reachable"},
            }
            if kind in SWITCHABLE or state.get("can_switch"):
                item["label"] = SWITCHABLE.get(kind, "Switch")
                switches.append(item)
            elif kind in ("CAMERA", "SECURITY_PANEL", "MOTION_SENSOR", "CONTACT_SENSOR",
                          "TEMPERATURE_SENSOR", "DOORBELL"):
                sensors.append(item)
            elif kind not in ("ALEXA_VOICE_ENABLED", "SCENE_TRIGGER", "APPLICATION"):
                other.append(item)

        # Light level and temperature from the Echos themselves
        rooms = []
        for e in self.endpoints:
            name = text(e, "friendlyNameObject") or ""
            state = self.states.get(e.get("endpointId"), {})
            if name.lower() in hidden or ("lux" not in state and "temperature" not in state):
                continue
            rooms.append({"name": name, "lux": state.get("lux"),
                          "temperature": state.get("temperature")})

        echos = [dict(d, **self.echo_status.get(d["serial"], {}))
                 for d in self.echos if d["name"].lower() not in hidden]
        switches.sort(key=lambda d: (not d["reachable"], d["name"].lower()))
        return {
            "switches": switches,
            "sensors": sorted(sensors, key=lambda d: d["name"].lower()),
            "other": sorted(other, key=lambda d: d["name"].lower()),
            "rooms": sorted(rooms, key=lambda d: d["name"].lower()),
            "echos": sorted(echos, key=lambda d: (not d["online"], d["name"].lower())),
            "routines": [r for r in self.routines if r.lower() not in hidden],
            "updated": self.updated["states"],
            "error": self.error,
        }

    # ----- doing things -----
    async def _control(self, endpoint_id, feature, operation, payload=None):
        request = {"endpointId": endpoint_id, "featureName": feature,
                   "featureOperationName": operation}
        if payload is not None:
            request["payload"] = payload
        async with self.lock:
            response = await self._graphql({
                "operationName": "setEndpointFeatures",
                "variables": {"requests": [request]},
                "query": SET_FEATURES,
            }, "control")
        problem = control_error(response)
        if problem:
            raise RuntimeError(problem)

    async def switch(self, endpoint_id, on):
        await self._control(endpoint_id, "power", "turnOn" if on else "turnOff")
        self.states.setdefault(endpoint_id, {})["power"] = "ON" if on else "OFF"
        self.states[endpoint_id]["power_changed"] = time.time()

    async def set_brightness(self, endpoint_id, percent):
        percent = max(1, min(100, int(percent)))
        await self._control(endpoint_id, "brightness", "setBrightness", {"brightness": percent})
        self.states.setdefault(endpoint_id, {})["brightness"] = percent
        self.states[endpoint_id]["power"] = "ON"

    async def set_colour(self, endpoint_id, hue, saturation=1.0):
        """Hue 0-360, saturation 0-1. Alexa wants it as {"color": {hue, saturation, brightness}}."""
        state = self.states.setdefault(endpoint_id, {})
        level = (state.get("brightness") or 100) / 100
        await self._control(endpoint_id, "color", "setColor",
                            {"color": {"hue": float(hue) % 360, "saturation": max(0.0, min(1.0, float(saturation))),
                                       "brightness": level}})
        state.update(hue=round(float(hue) % 360), saturation=float(saturation), kelvin=None, power="ON")

    async def set_white(self, endpoint_id, kelvin):
        """Warm to cool white, 2200 (candle) to 6500 (daylight)."""
        kelvin = max(2200, min(6500, int(kelvin)))
        await self._control(endpoint_id, "colorTemperature", "setColorTemperature",
                            {"colorTemperatureInKelvin": kelvin})
        state = self.states.setdefault(endpoint_id, {})
        state.update(kelvin=kelvin, hue=None, saturation=None, power="ON")

    async def run_routine(self, name):
        names = {r.strip(): r for r in self.api.routines}
        if name not in names:
            raise ValueError(f"No routine called {name}")
        async with self.lock:
            # Routines run "on" an Echo; anything they say is said there
            chosen = [d for d in self.api._device_handler.devices.values()
                      if self.routine_echo and d.account_name.lower() == self.routine_echo]
            if chosen and chosen[0].serial_number != self.api._default_device_serial:
                await self.api.set_default_device(chosen[0])
            elif not self.api._default_device_serial:
                await self.api._init_default_device()
            await self.api.call_routine(names[name])

    def _device(self, serial):
        device = self.devices.get(serial)
        if not device:
            raise ValueError("That Echo isn't known")
        return device

    async def echo_control(self, serial, action, value=None):
        device = self._device(serial)
        async with self.lock:
            if action in MEDIA_COMMANDS:
                await self.api.send_media_command(device, MEDIA_COMMANDS[action])
            elif action == "volume":
                await self.api.set_device_volume(device, max(0, min(100, int(value))))
                self.echo_status.setdefault(serial, {})["volume"] = int(value)
            elif action == "dnd":
                await self.api.set_do_not_disturb(device, bool(value))
                self.echo_status.setdefault(serial, {})["dnd"] = bool(value)
            else:
                raise ValueError(f"Unknown action: {action}")
        # Pick up the new state shortly after (what's playing takes a moment to change)
        self.updated["echo_status"] = time.time() - ECHO_STATUS_EVERY + 4

    def echo_name(self, serial):
        device = self.devices.get(serial)
        return device.account_name if device else "Echo"

    def name_of(self, endpoint_id):
        for e in self.endpoints:
            if e.get("endpointId") == endpoint_id:
                return text(e, "friendlyNameObject") or "device"
        return "device"
