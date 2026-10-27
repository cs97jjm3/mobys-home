import time
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import location_link as ll

HOME = (52.666, 0.159)


def person(name, lat, lon, acc=10, battery=50):
    return NS(full_name=name, nickname=None, latitude=lat, longitude=lon, accuracy=acc, battery_level=battery,
              charging=False, address="12 High Street, Wisbech PE13 1AB, UK", datetime=datetime.now(timezone.utc))


def make(tmp_path, found):
    cookies = tmp_path / "google_cookies.txt"
    cookies.write_text("x")
    locs = ll.Locations(cookies, "me@example.com", {"James": "me@example", "Claire": "Claire", "Ed": "Edward"})
    locs.home = HOME
    locs._fetch = lambda: found
    locs._route_minutes = lambda name, pos: ll.rough_minutes(ll.km_between(pos, HOME))
    return locs


def test_home_and_away(tmp_path):
    locs = make(tmp_path, [person("me@example.com", 52.6661, 0.1591), person("Claire Murrell (Claire Bear)", 52.75, 0.40)])
    locs._work()
    snap = locs.snapshot()
    james, claire = snap["people"]
    assert james["home"] and james["minutes"] is None
    assert not claire["home"] and claire["minutes"] > 10 and claire["place"] == "12 High Street, Wisbech"
    assert [p["name"] for p in snap["people"]] == ["James", "Claire"]      # Ed not found: left out


def test_heading_home(tmp_path):
    found = [person("Edward Murrell", 52.70, 0.25)]
    locs = make(tmp_path, found)
    real = time.time
    try:
        ll.time.time = lambda: 1000.0
        locs._work()
        found[0].latitude, found[0].longitude = 52.68, 0.20          # 9 minutes later, closer to home
        ll.time.time = lambda: 1000.0 + 9 * 60
        locs._work()
    finally:
        ll.time.time = real
    assert locs.people["Ed"]["heading_home"]


def test_wifi_or_google_counts_as_home():
    import home_hub
    home = {"people": [{"name": "Claire", "home": False}, {"name": "Ed", "home": True}]}
    family = {"people": [{"name": "Claire", "home": True, "minutes": None, "heading_home": False},
                         {"name": "Ed", "home": False, "minutes": 7, "heading_home": True}]}
    out = home_hub.with_locations(home, family)
    claire, ed = out["people"]
    assert claire["home"] and ed["home"] and ed["minutes"] is None and not ed["heading_home"]
