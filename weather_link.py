"""
The weather for Moby's Home, from Open-Meteo (free, no account needed).

Looks up the postcode once with postcodes.io, then fetches the current
weather, the next 12 hours and the next 5 days every 15 minutes.
"""

import time
from datetime import datetime
from pathlib import Path

REFRESH_EVERY = 15 * 60

# WMO weather codes -> (description, icon)
CODES = {
    0: ("Clear", "clear"), 1: ("Mostly clear", "clear"), 2: ("Partly cloudy", "part"),
    3: ("Cloudy", "cloud"), 45: ("Fog", "fog"), 48: ("Freezing fog", "fog"),
    51: ("Light drizzle", "drizzle"), 53: ("Drizzle", "drizzle"), 55: ("Heavy drizzle", "drizzle"),
    56: ("Freezing drizzle", "drizzle"), 57: ("Freezing drizzle", "drizzle"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"),
    80: ("Light showers", "showers"), 81: ("Showers", "showers"), 82: ("Heavy showers", "showers"),
    85: ("Snow showers", "snow"), 86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "thunder"), 96: ("Thunder and hail", "thunder"), 99: ("Thunder and hail", "thunder"),
}


def describe(code, is_day=True):
    text, icon = CODES.get(int(code) if code is not None else -1, ("–", "cloud"))
    if not is_day and icon in ("clear", "part"):
        icon += "-night"
    return text, icon


def shape(data, now=None):
    """Boil Open-Meteo's reply down to what the page shows."""
    now = now or time.time()
    cur = data.get("current") or {}
    text, icon = describe(cur.get("weather_code"), cur.get("is_day", 1))
    out = {
        "now": {
            "temp": cur.get("temperature_2m"), "feels": cur.get("apparent_temperature"),
            "wind": cur.get("wind_speed_10m"), "gusts": cur.get("wind_gusts_10m"),
            "text": text, "icon": icon,
        },
        "hours": [], "days": [],
    }
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    this_hour = datetime.fromtimestamp(now).replace(minute=0, second=0, microsecond=0)
    for i, t in enumerate(times):
        when = datetime.fromisoformat(t)
        if when < this_hour:
            continue
        h_text, h_icon = describe(hourly["weather_code"][i], (hourly.get("is_day") or [1] * len(times))[i])
        out["hours"].append({"time": when.strftime("%H:%M"), "temp": hourly["temperature_2m"][i],
                             "rain": hourly["precipitation_probability"][i], "icon": h_icon, "text": h_text})
        if len(out["hours"]) == 12:
            break
    daily = data.get("daily") or {}
    for i, d in enumerate(daily.get("time") or []):
        d_text, d_icon = describe(daily["weather_code"][i])
        day = datetime.fromisoformat(d)
        out["days"].append({
            "day": "Today" if i == 0 else day.strftime("%a"), "high": daily["temperature_2m_max"][i],
            "low": daily["temperature_2m_min"][i], "rain": daily["precipitation_probability_max"][i],
            "icon": d_icon, "text": d_text,
            "sunrise": (daily.get("sunrise") or [""] * 9)[i][-5:],
            "sunset": (daily.get("sunset") or [""] * 9)[i][-5:],
        })
    if out["days"]:
        out["today"] = out["days"][0]
    # When the rain is due, in words
    for h in out["hours"]:
        if (h["rain"] or 0) >= 50:
            out["rain_note"] = f"Rain likely from {h['time']}" if h is not out["hours"][0] else "Rain likely now"
            break
    else:
        out["rain_note"] = "Dry for the next 12 hours" if out["hours"] else ""
    return out


class Weather:
    def __init__(self, postcode, cache_file):
        self.postcode = postcode.strip()
        self.cache_file = Path(cache_file)
        self.where = None
        self.data = None
        self.fetched = 0
        self.error = None

    async def _locate(self, session):
        key = self.postcode.upper().replace(" ", "")
        if self.cache_file.exists():
            saved = self.cache_file.read_text().split(",")
            if len(saved) == 3 and saved[0] == key:
                self.where = (float(saved[1]), float(saved[2]))
                return
        async with session.get(f"https://api.postcodes.io/postcodes/{key}") as r:
            result = (await r.json(content_type=None))["result"]
        self.where = (result["latitude"], result["longitude"])
        self.cache_file.write_text(f"{key},{self.where[0]},{self.where[1]}")

    async def refresh(self, session, force=False):
        if not self.postcode or (not force and time.time() - self.fetched < REFRESH_EVERY):
            return
        try:
            if not self.where:
                await self._locate(session)
            params = {
                "latitude": self.where[0], "longitude": self.where[1], "timezone": "Europe/London",
                "wind_speed_unit": "mph", "forecast_days": 6,
                "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,"
                           "wind_gusts_10m,is_day",
                "hourly": "temperature_2m,precipitation_probability,weather_code,is_day",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max,sunrise,sunset",
            }
            async with session.get("https://api.open-meteo.com/v1/forecast", params=params) as r:
                raw = await r.json(content_type=None)
            if "current" not in raw:
                raise RuntimeError(raw.get("reason") or "no data")
            self.data = shape(raw)
            self.fetched = time.time()
            self.error = None
        except Exception as err:
            self.error = str(err) or err.__class__.__name__
            print(f"Weather: {self.error}")

    def snapshot(self):
        if not self.postcode:
            return None
        return dict(self.data or {}, error=self.error, updated=self.fetched or None)
