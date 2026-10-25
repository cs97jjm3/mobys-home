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


def test_dial_state():
    xml = ('<?xml version="1.0"?><service xmlns="urn:dial-multiscreen-org:schemas:dial" dialVer="2.2">'
           '<name>Netflix</name><options allowStop="true"/><state>running</state></service>')
    assert dl.parse_dial_state(xml) == "running"
    assert dl.parse_dial_state("<x/>") is None


def test_box_app_added_to_tv():
    devices = dl.Devices({"tv_ip": "1.2.3.4", "tv_mac": "", "tv_default": "BT TV", "box_ip": "1.2.3.5"}, "/tmp")
    devices.state = {"tv": {"state": "on", "watching": "BT TV", "apps": []},
                     "box": {"reachable": True, "app": "Netflix"}}
    assert devices.snapshot()["tv"]["watching"] == "BT TV · Netflix"
    devices.state["tv"]["watching"] = "YouTube"     # an app on the Samsung itself wins
    assert devices.snapshot()["tv"]["watching"] == "YouTube"
    devices.state["box"]["app"] = None
    devices.state["tv"]["watching"] = "BT TV"
    assert devices.snapshot()["tv"]["watching"] == "BT TV"


HUB_BODY = ("{timestamp:'0',app:'4294967295',mac:'72%3A6b%3Aa0%3A98%3A52%3Ad6',tx:'258535792',rx:'2645303994'}, "
            "{timestamp:'0',app:'4294967295',mac:'7c%3A16%3A89%3A9c%3A05%3A97',tx:'1360554892',rx:'105964860177'}")


def test_hub_traffic_parse():
    assert dl.HubTraffic.parse(HUB_BODY, "7c:16:89:9c:05:97") == 105964860177
    assert dl.HubTraffic.parse(HUB_BODY, "00:11:22:33:44:55") is None


def test_streaming_shown_on_tv():
    devices = dl.Devices({"tv_ip": "1.2.3.4", "tv_mac": "", "tv_default": "BT TV", "box_ip": "1.2.3.5",
                          "box_mac": "7C:16:89:9C:05:97"}, "/tmp")
    devices.state = {"tv": {"state": "on", "watching": "BT TV", "apps": []},
                     "box": {"reachable": True, "app": None}, "traffic": {"mbps": 9.6, "streaming": True}}
    assert devices.snapshot()["tv"]["watching"] == "BT TV · streaming"
    devices.state["box"]["app"] = "Netflix"       # a named app wins over plain "streaming"
    assert devices.snapshot()["tv"]["watching"] == "BT TV · Netflix"
    devices.state["box"]["app"] = None
    devices.state["traffic"] = {"mbps": 0.1, "streaming": False}
    assert devices.snapshot()["tv"]["watching"] == "BT TV"
