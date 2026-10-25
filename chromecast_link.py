"""
Chromecasts, for Moby's Home. Works over the home network with no account.

Finds every Chromecast (and Google TV) on the network, stays connected to each
one, and reports what's being cast: the app, the title, the artist or show,
the cover picture, playing or paused, and the volume. Can play, pause, stop
and change the volume.

Needs:  py -m pip install pychromecast
"""

import asyncio
import threading
import time

IDLE_APPS = {"Backdrop", "Ambient Mode", ""}   # what a Chromecast shows when nothing is cast


def describe(cast_info, status, media, connected=True):
    """Boil a Chromecast's state down to what the page shows. Kept separate so it can be tested."""
    app = (getattr(status, "display_name", None) or "") if status else ""
    out = {
        "name": getattr(cast_info, "friendly_name", None) or "Chromecast",
        "model": getattr(cast_info, "model_name", None) or "",
        "online": connected,
        "app": None if app in IDLE_APPS else app,
        "volume": round(status.volume_level * 100) if status and status.volume_level is not None else None,
        "muted": bool(getattr(status, "volume_muted", False)) if status else False,
        "state": "idle", "title": None, "subtitle": None, "art": None, "can_pause": False,
    }
    if out["app"]:
        out["state"] = "casting"
    player = getattr(media, "player_state", None) if media else None
    if out["app"] and player in ("PLAYING", "PAUSED", "BUFFERING"):
        out["state"] = "paused" if player == "PAUSED" else "playing"
        out["title"] = media.title or None
        show = media.series_title
        if show and media.season and media.episode:
            show = f"{show} · S{media.season} E{media.episode}"
        out["subtitle"] = media.artist or show or media.album_name or None
        out["art"] = media.images[0].url if media.images else None
        out["can_pause"] = bool(media.supports_pause)
    return out


class Chromecasts:
    def __init__(self, enabled=True, hosts=None):
        self.enabled = enabled
        self.hosts = hosts or None
        self.casts = {}          # id -> pychromecast.Chromecast
        self.browser = None
        self.error = None

    def start(self):
        if not self.enabled:
            return
        try:
            import pychromecast
        except ImportError:
            self.error = "Chromecasts need:  py -m pip install pychromecast"
            print(self.error)
            return

        def found(cc):
            uid = str(cc.uuid)
            if uid in self.casts:
                return
            self.casts[uid] = cc

            def connect():
                try:
                    cc.wait(timeout=30)
                    print(f"Chromecast: connected to {cc.cast_info.friendly_name}")
                except Exception as err:
                    print(f"Chromecast: couldn't connect to {cc.cast_info.friendly_name} ({err})")
            threading.Thread(target=connect, daemon=True).start()

        try:
            self.browser = pychromecast.get_chromecasts(blocking=False, callback=found,
                                                        known_hosts=self.hosts)
        except Exception as err:
            self.error = f"Couldn't look for Chromecasts ({err})"
            print(self.error)

    def stop(self):
        for cc in list(self.casts.values()):
            try:
                cc.disconnect(timeout=2)
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.stop_discovery()
            except Exception:
                pass

    def snapshot(self):
        if not self.enabled:
            return None
        out = []
        for uid, cc in list(self.casts.items()):
            try:
                connected = bool(cc.socket_client and cc.socket_client.is_connected)
                media = cc.media_controller.status if connected else None
                item = describe(cc.cast_info, cc.status if connected else None, media, connected)
            except Exception:
                item = describe(cc.cast_info, None, None, False)
            item["id"] = uid
            out.append(item)
        return sorted(out, key=lambda c: (not c["online"], c["name"].lower()))

    def name_of(self, uid):
        cc = self.casts.get(uid)
        return cc.cast_info.friendly_name if cc else "Chromecast"

    async def control(self, uid, action, value=None):
        cc = self.casts.get(uid)
        if not cc:
            raise ValueError("That Chromecast isn't connected")

        def work():
            mc = cc.media_controller
            if action == "play":
                mc.play()
            elif action == "pause":
                mc.pause()
            elif action == "stop":
                cc.quit_app()
            elif action == "volume":
                cc.set_volume(max(0, min(100, int(value))) / 100)
            else:
                raise ValueError(f"Unknown action: {action}")
        await asyncio.to_thread(work)
        await asyncio.sleep(0.6)   # let the new state come back before the page redraws
