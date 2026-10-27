"""
Checks Google location sharing works with your cookies, before Moby's Home uses it.

1. In a browser signed in to Google, export your google.com cookies as a cookies.txt
   file (Netscape format), and save it next to this script as google_cookies.txt.
   Keep that file private: it's as good as your Google password.
2. Run:   py location_test.py your.address@gmail.com

Only reads. Shows each person's name, how old the location is, accuracy,
whether there's an address, and how far they are from home. It doesn't
print exact coordinates.
"""

import configparser
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from locationsharinglib import Service

HERE = Path(__file__).parent
COOKIES = HERE / "google_cookies.txt"

if len(sys.argv) < 2:
    print("Use:  py location_test.py your.address@gmail.com")
    raise SystemExit
if not COOKIES.exists():
    print("google_cookies.txt isn't here yet (see the steps at the top of this file)")
    raise SystemExit

# Where home is, from the postcode in home_config.ini
config = configparser.ConfigParser()
config.read(HERE / "home_config.ini", encoding="utf-8")
postcode = config.get("location", "postcode", fallback="").replace(" ", "")
home = None
if postcode:
    with urllib.request.urlopen(f"https://api.postcodes.io/postcodes/{postcode}", timeout=10) as r:
        res = json.loads(r.read())["result"]
        home = (res["latitude"], res["longitude"])


def km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


service = Service(cookies_file=str(COOKIES), authenticating_account=sys.argv[1].strip())
people = list(service.get_shared_people())
try:
    me = service.get_authenticated_person()
    if me:
        people.insert(0, me)
except Exception as err:
    print(f"(Couldn't get your own location: {err})")

print(f"Found {len(people)} people\n")
now = datetime.now(timezone.utc)
for p in people:
    age = ""
    try:
        when = p.datetime if p.datetime.tzinfo else p.datetime.replace(tzinfo=timezone.utc)
        age = f"{int((now - when).total_seconds() // 60)} min old"
    except Exception:
        pass
    away = f"{km(home, (p.latitude, p.longitude)):.1f} km from home" if home and p.latitude else "no position"
    print(f"  {p.full_name or p.nickname}:  {away},  {age},  accuracy {p.accuracy} m,"
          f"  address {'yes' if p.address else 'no'},  battery {p.battery_level}%")
print("\nPaste all of that to Claude.")
