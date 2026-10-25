import asyncio
from types import SimpleNamespace as NS

import chromecast_link as cl
import devices_link as dl

INFO = NS(friendly_name="Lounge TV", model_name="Chromecast")


def media(**kw):
    base = dict(player_state="PLAYING", title="Yellow", artist=None, series_title=None, season=None,
                episode=None, album_name=None, images=[NS(url="http://x/a.jpg")], supports_pause=True)
    base.update(kw)
    return NS(**base)


def test_idle_chromecast():
    out = cl.describe(INFO, NS(display_name="Backdrop", volume_level=0.5, volume_muted=False), None)
    assert out["state"] == "idle" and out["app"] is None and out["volume"] == 50


def test_music_playing():
    out = cl.describe(INFO, NS(display_name="Spotify", volume_level=0.3, volume_muted=False),
                      media(artist="Coldplay"))
    assert out["state"] == "playing" and out["title"] == "Yellow" and out["subtitle"] == "Coldplay"
    assert out["art"] == "http://x/a.jpg" and out["can_pause"]


def test_tv_show_paused():
    out = cl.describe(INFO, NS(display_name="Netflix", volume_level=1.0, volume_muted=False),
                      media(player_state="PAUSED", title="Episode 1", series_title="Slow Horses", season=2, episode=1))
    assert out["state"] == "paused" and out["subtitle"] == "Slow Horses · S2 E1"


def test_casting_without_details():
    out = cl.describe(INFO, NS(display_name="BBC iPlayer", volume_level=0.2, volume_muted=False), None)
    assert out["state"] == "casting" and out["title"] is None


def test_offline():
    out = cl.describe(INFO, None, None, connected=False)
    assert not out["online"] and out["volume"] is None


def run_on_screen(answers, default=""):
    tv = dl.SamsungTV("1.2.3.4", "", "/nonexistent/token.txt", default)

    async def fake(session, app_id):
        return answers.get(app_id)
    tv._app_state = fake
    return tv, asyncio.run(tv._on_screen(None))


def test_tv_app_on_screen():
    tv, showing = run_on_screen({"111299001912": {"name": "YouTube", "visible": True},
                                 "3201907018807": {"name": "Netflix", "visible": False}})
    assert showing == "YouTube"
    assert {a["name"] for a in tv.apps} == {"YouTube", "Netflix"}


def test_tv_no_app_on_screen():
    tv, showing = run_on_screen({"3201907018807": {"name": "Netflix", "visible": False, "running": True}})
    assert showing is None
