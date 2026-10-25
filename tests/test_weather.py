"""Tests for shaping the weather. No internet needed."""

from datetime import datetime

import weather_link as wl


def sample():
    hours = [f"2026-10-25T{h:02d}:00" for h in range(24)]
    return {
        "current": {"temperature_2m": 11.6, "apparent_temperature": 9.2, "weather_code": 2,
                    "wind_speed_10m": 12.4, "wind_gusts_10m": 25.1, "is_day": 1},
        "hourly": {"time": hours, "temperature_2m": [10 + h / 10 for h in range(24)],
                   "precipitation_probability": [0] * 17 + [70] * 7,
                   "weather_code": [2] * 17 + [61] * 7, "is_day": [1] * 18 + [0] * 6},
        "daily": {"time": ["2026-10-25", "2026-10-26"], "weather_code": [61, 0],
                  "temperature_2m_max": [12.1, 13.4], "temperature_2m_min": [6.0, 4.2],
                  "precipitation_probability_max": [70, 5],
                  "sunrise": ["2026-10-25T06:52", "2026-10-26T06:54"],
                  "sunset": ["2026-10-25T16:44", "2026-10-26T16:42"]},
    }


def test_shapes_now_hours_and_days():
    now = datetime(2026, 10, 25, 14, 20).timestamp()
    w = wl.shape(sample(), now)
    assert w["now"]["text"] == "Partly cloudy" and w["now"]["icon"] == "part"
    assert w["hours"][0]["time"] == "14:00" and len(w["hours"]) == 10
    assert w["rain_note"] == "Rain likely from 17:00"
    assert w["today"]["sunrise"] == "06:52" and w["days"][1]["day"] == "Mon"


def test_night_icons_and_unknown_codes():
    assert wl.describe(0, is_day=False) == ("Clear", "clear-night")
    assert wl.describe(61, is_day=False)[1] == "rain"
    assert wl.describe(None)[1] == "cloud"
