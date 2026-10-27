"""
Where the family is, from Google Maps location sharing, for Moby's Home.

Uses the unofficial locationsharinglib with cookies exported from a browser signed in
to Google (google_cookies.txt, kept private and off GitHub). Shows each person's
position on a map, how far they are from home, roughly how long it would take to
drive home, and whether they're heading home.

Driving times come from the free public OSRM route planner, asked only when someone
has moved, so it's very light use. If it doesn't answer, a simple estimate is used.
"""

import asyncio
import json
import math
import re
import time
import urllib.request
from pathlib import Path

CHECK_EVERY = 120          # Google, every 2 minutes
HOME_WITHIN_KM = 0.25      # this close to home counts as home
HEADING_HOME_KM = 0.3      # got at least this much closer in the last 10 minutes = heading home
POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{a},{b};{c},{d}?overview=false"


def km_between(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def rough_minutes(km):
    """If the route planner doesn't answer: roads are about 1.3 times the straight line, at about 45 km/h."""
    return max(1, round(km * 1.3 / 45 * 60))


def short_place(address):
    """'12 High Street, Wisbech PE13 1AB, UK' -> '12 High Street, Wisbech'"""
    if not address:
        return None
    parts = [p.strip() for p in address.split(",") if p.strip() not in ("", "UK", "United Kingdom")]
    keep = [POSTCODE.sub("", p).strip() for p in parts[:2]]
    return ", ".join(p for p in keep if p) or None


def match_name(google_name, wanted):
    """Does a Google name ('Edward Murrell', 'Claire Murrell (Claire Bear)', an email) match what's in the settings?"""
    g, w = (google_name or "").lower(), wanted.lower().strip()
    return bool(w) and w in g


class Locations:
    def __init__(self, cookies_file, account, names):
        """names: {"James": "murrell.james", "Claire": "Claire", "Ed": "Edward"}  (dashboard name -> part of Google name)"""
        self.cookies_file = Path(cookies_file)
        self.account = (account or "").strip()
        self.names = names or {}
        self.home = None
        self.people = {}            # dashboard name -> details
        self.trail = {}             # name -> [(time, km from home)], for "heading home"
        self.routes = {}            # name -> (lat, lon, minutes)
        self.fetched = 0
        self.error = None

    @property
    def enabled(self):
        return bool(self.account and self.names and self.cookies_file.exists())

    def _fetch(self):
        from locationsharinglib import Service
        service = Service(cookies_file=str(self.cookies_file), authenticating_account=self.account)
        found = list(service.get_shared_people())
        try:
            me = service.get_authenticated_person()
            if me:
                found.append(me)
        except Exception:
            pass
        return found

    def _route_minutes(self, name, pos):
        old = self.routes.get(name)
        if old and km_between(old[:2], pos) < 0.2:
            return old[2]
        try:
            url = ROUTE_URL.format(a=pos[1], b=pos[0], c=self.home[1], d=self.home[0])
            req = urllib.request.Request(url, headers={"User-Agent": "MobysHome/1.0 (family dashboard)"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            minutes = max(1, round(data["routes"][0]["duration"] / 60))
        except Exception:
            minutes = rough_minutes(km_between(pos, self.home))
        self.routes[name] = (pos[0], pos[1], minutes)
        return minutes

    def _work(self):
        found = self._fetch()
        now = time.time()
        for name, wanted in self.names.items():
            person = next((p for p in found if match_name(p.full_name, wanted) or match_name(p.nickname, wanted)), None)
            if not person or person.latitude is None:
                continue
            pos = (person.latitude, person.longitude)
            away = km_between(pos, self.home)
            at_home = away <= max(HOME_WITHIN_KM, (person.accuracy or 0) / 1000)
            trail = [t for t in self.trail.get(name, []) if now - t[0] < 15 * 60] + [(now, away)]
            self.trail[name] = trail
            # How far away they were about 10 minutes ago (the oldest reading at least 8 minutes old)
            ten_ago = next((d for t, d in trail if now - t >= 8 * 60), None)
            heading = (not at_home and ten_ago is not None and ten_ago - away >= HEADING_HOME_KM)
            try:
                seen = person.datetime.timestamp()
            except Exception:
                seen = None
            self.people[name] = {
                "name": name, "lat": round(pos[0], 5), "lon": round(pos[1], 5),
                "accuracy": person.accuracy, "seen": seen, "battery": person.battery_level,
                "charging": bool(person.charging), "home": at_home, "km": round(away, 1),
                "minutes": None if at_home else self._route_minutes(name, pos),
                "heading_home": heading, "place": short_place(person.address),
            }

    async def refresh(self, session_unused=None, postcode_home=None, force=False):
        if not self.enabled or (not force and time.time() - self.fetched < CHECK_EVERY):
            return
        if postcode_home:
            self.home = postcode_home
        if not self.home:
            return
        try:
            await asyncio.to_thread(self._work)
            self.fetched = time.time()
            self.error = None
        except Exception as err:
            self.fetched = time.time()   # don't hammer Google after a failure
            text = str(err)
            self.error = ("Google wants you to sign in again: export new cookies" if "cookie" in text.lower()
                          or "login" in text.lower() or "auth" in text.lower()
                          else f"Couldn't read locations ({err.__class__.__name__})")
            print(f"Locations: {err}")

    def snapshot(self):
        if not self.enabled:
            return None
        return {"home": {"lat": self.home[0], "lon": self.home[1]} if self.home else None,
                "people": [self.people[n] for n in self.names if n in self.people],
                "error": self.error, "updated": self.fetched or None}
