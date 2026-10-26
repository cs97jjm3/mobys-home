"""
The Ring doorbell, for Moby's Home.

Uses the unofficial ring_doorbell library. Sign in once with ring_test.py (it saves
ring_token.json), then this keeps the sign-in fresh by itself.

  - live presses and motion, within a few seconds, from Ring's own push messages
  - today's presses and motion, last press, last motion, battery
  - motion alerts on or off

Without a Ring Protect plan there are no pictures or recordings, so none are used.
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

REFRESH_EVERY = 300      # battery and history, every 5 minutes (Ring doesn't like being asked often)
LIVE_FOR = 120           # how long a press stays "live" on the page, in seconds
AGENT = "MobysHome-1.0"


def history_item(h):
    """One entry from Ring's history -> {"ts", "kind"}."""
    when = h.get("created_at")
    if isinstance(when, datetime):
        ts = when.timestamp()
    else:
        try:
            ts = datetime.fromisoformat(str(when).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    kind = h.get("kind")
    return {"ts": ts, "kind": "press" if kind == "ding" else kind} if kind in ("ding", "motion") else None


def today_only(items, now=None):
    start = datetime.fromtimestamp(now or time.time()).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return [i for i in items if i["ts"] >= start]


class RingDoor:
    def __init__(self, token_file, listen_file):
        self.token_file = Path(token_file)
        self.listen_file = Path(listen_file)
        self.auth = self.ring = self.listener = self.bell = None
        self.info = {}
        self.events = []          # today's presses and motion, newest first
        self.live = None          # the latest live event: {"id", "kind", "ts"}
        self.counter = 0
        self.fetched = 0
        self.error = None
        self.on_press = None      # set by the hub: called (async) when someone presses the bell

    @property
    def enabled(self):
        return self.token_file.exists()

    def _save_token(self, token):
        self.token_file.write_text(json.dumps(token))

    async def start(self):
        if not self.enabled:
            return
        from ring_doorbell import Auth, Ring, RingEventListener
        try:
            self.auth = Auth(AGENT, json.loads(self.token_file.read_text()), self._save_token)
            self.ring = Ring(self.auth)
            await self.ring.async_create_session()
            await self.ring.async_update_data()
            bells = list(self.ring.devices().doorbells)
            self.bell = bells[0] if bells else None
            saved = json.loads(self.listen_file.read_text()) if self.listen_file.exists() else None
            self.listener = RingEventListener(self.ring, saved,
                                              lambda creds: self.listen_file.write_text(json.dumps(creds)))
            self.listener.add_notification_callback(self._heard)
            await self.listener.start()
            await self.refresh(force=True)
        except Exception as err:
            self.error = f"Ring: {err or err.__class__.__name__}"
            print(self.error)

    async def stop(self):
        try:
            if self.listener:
                await self.listener.stop()
            if self.auth:
                await self.auth.async_close()
        except Exception:
            pass

    def _heard(self, event):
        """Ring pushed a press or motion to us."""
        kind = "press" if event.kind == "ding" else event.kind
        if kind not in ("press", "motion"):
            return
        self.counter += 1
        now = time.time()
        self.live = {"id": self.counter, "kind": kind, "ts": now}
        self.events.insert(0, {"ts": now, "kind": kind})
        if kind == "press" and self.on_press:
            asyncio.get_running_loop().create_task(self.on_press())

    async def refresh(self, force=False):
        if not self.bell or (not force and time.time() - self.fetched < REFRESH_EVERY):
            return
        try:
            await self.bell.async_update()
            try:
                await self.bell.async_update_health_data()
            except Exception:
                pass
            history = await self.bell.async_history(limit=60)
            items = [i for i in (history_item(h) for h in history) if i]
            self.events = sorted(today_only(items), key=lambda i: -i["ts"])
            last = {k: next((i["ts"] for i in items if i["kind"] == k), None) for k in ("press", "motion")}
            self.info = {"name": self.bell.name, "battery": self._safe(lambda: self.bell.battery_life),
                         "wifi": self._safe(lambda: self.bell.wifi_signal_category),
                         "motion_on": self._safe(lambda: self.bell.motion_detection),
                         "last_press": last["press"], "last_motion": last["motion"]}
            self.fetched = time.time()
            self.error = None
        except Exception as err:
            self.error = f"Ring didn't answer ({err.__class__.__name__})"
            print(f"Ring: {err}")

    @staticmethod
    def _safe(getter):
        try:
            return getter()
        except Exception:
            return None

    async def set_motion(self, on):
        await self.bell.async_set_motion_detection(bool(on))
        self.info["motion_on"] = bool(on)

    def snapshot(self, quiet_until=None):
        if not self.enabled:
            return None
        now = time.time()
        today = today_only(self.events, now)
        live = self.live if self.live and now - self.live["ts"] < LIVE_FOR else None
        info = dict(self.info)
        # Live events are newer than the last history fetch
        for e in today:
            key = "last_press" if e["kind"] == "press" else "last_motion"
            if not info.get(key) or e["ts"] > info[key]:
                info[key] = e["ts"]
        return dict(info, presses=sum(1 for e in today if e["kind"] == "press"),
                    motions=sum(1 for e in today if e["kind"] == "motion"),
                    timeline=today[:80], live=live, error=self.error,
                    quiet_until=quiet_until if quiet_until and quiet_until > now else None)
