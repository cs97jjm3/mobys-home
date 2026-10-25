"""
Checks what the Samsung TV and the Chromecasts will tell us about what's on.
Put something on first (Netflix or YouTube on the TV, and cast something to a Chromecast), then run:

    py whats_on_test.py

Needs:  py -m pip install pychromecast
"""

import configparser
import json
import ssl
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent

print("=== Samsung TV ===")
config = configparser.ConfigParser()
config.read(HERE / "home_config.ini", encoding="utf-8")
tv_ip = config.get("devices", "tv", fallback="").strip()
no_check = ssl.create_default_context()
no_check.check_hostname = False
no_check.verify_mode = ssl.CERT_NONE


def ask(url):
    try:
        with urllib.request.urlopen(url, timeout=3, context=no_check if url.startswith("https") else None) as r:
            return r.status, r.read().decode("utf-8", "replace")[:200]
    except urllib.error.HTTPError as err:
        return err.code, ""
    except Exception as err:
        return None, err.__class__.__name__


if not tv_ip:
    print("No TV address in home_config.ini")
else:
    # Well-known Samsung app numbers, so we don't depend on the TV sending its app list
    apps = [{"appId": i, "name": n} for i, n in [
        ("3201907018807", "Netflix"), ("11101200001", "Netflix (old)"), ("111299001912", "YouTube"),
        ("3201910019365", "Prime Video"), ("3201901017640", "Disney+"), ("3201807016597", "Apple TV"),
        ("3201606009684", "Spotify"), ("3201512006963", "Plex")]]
    print("Checking the main apps (put Netflix or YouTube on the TV first)")
    for app in apps[:12]:
        app_id, name = app.get("appId"), app.get("name")
        for url in (f"http://{tv_ip}:8001/api/v2/applications/{app_id}",
                    f"https://{tv_ip}:8002/api/v2/applications/{app_id}"):
            code, body = ask(url)
            print(f"  {name:<20} {url.split(':')[0]:<5} -> {code} {body}")

print("\n=== Chromecasts ===")
try:
    import pychromecast
except ImportError:
    print("Run this first:  py -m pip install pychromecast")
    raise SystemExit

casts, browser = pychromecast.get_chromecasts(timeout=10)
print(f"Found {len(casts)}")
for cc in casts:
    try:
        cc.wait(timeout=10)
        info = cc.cast_info
        print(f"\n  {info.friendly_name}  ({info.model_name}, {info.host})")
        status = cc.status
        print(f"    App: {status.display_name if status else None}   Volume: {round(status.volume_level * 100) if status else None}")
        mc = cc.media_controller
        try:
            mc.block_until_active(timeout=4)
            mc.update_status()
            time.sleep(1.5)
        except Exception:
            pass
        m = mc.status
        if m and m.player_state and m.player_state != "UNKNOWN":
            print(f"    Playing: {m.player_state}  Title: {m.title}  Artist/Show: {m.artist or m.series_title}")
            print(f"    Picture: {'yes' if m.images else 'no'}   Can pause: {m.supports_pause}")
        else:
            print("    Nothing playing that it will describe")
        cc.disconnect()
    except Exception as err:
        print(f"    Error: {err}")
pychromecast.discovery.stop_discovery(browser)
print("\nPaste all of that to Claude.")
