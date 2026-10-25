"""
Moby's Home: one page for the house.

Shows and switches the lights and plugs Alexa knows about, the front door,
your Echos and routines, plus tiles for Moby's Heat and the race dashboard.

Setup (once):
    pip install aiohttp aioamazondevices
    Run alexa_peek.py once, so alexa_login.json exists.
    Copy home_config.example.ini to home_config.ini and fill it in.

Run:
    py home_hub.py
Then open http://localhost:8095 (or whatever port is in home_config.ini).
"""

import argparse
import asyncio
import configparser
import hashlib
import hmac
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import aiohttp
from aiohttp import web
from yarl import URL

from alexa_link import Alexa
from devices_link import Devices
from psn_link import CHECK_EVERY as PSN_EVERY, PlayStation
from weather_link import Weather

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "home_config.ini"
PAGE_PATH = HERE / "home_page.html"
STATIC_PATH = HERE / "static"
SECRET_PATH = HERE / "home_secret.txt"

COOKIE_NAME = "home_auth"
MAX_PIN_TRIES = 5
PIN_LOCKOUT_SECONDS = 5 * 60

CONTENT_TYPES = {
    ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}

ALEXA = web.AppKey("alexa", object)
DEVICES = web.AppKey("devices", object)
PSN = web.AppKey("psn", object)
WEATHER = web.AppKey("weather", object)
CONFIG = web.AppKey("config", dict)
PIN = web.AppKey("pin", str)
SECRET = web.AppKey("secret", str)
PIN_LOCK = web.AppKey("pin_lock", dict)
STATE = web.AppKey("state", dict)
JOBS = web.AppKey("jobs", dict)


# ---------- settings ----------

def load_config():
    config = configparser.ConfigParser(interpolation=None)
    if CONFIG_PATH.exists():
        config.read(CONFIG_PATH, encoding="utf-8")
        print(f"Using settings from {CONFIG_PATH.name}")

    def get(section, key, default=""):
        return config.get(section, key, fallback=default).strip()

    return {
        "pin": get("dashboard", "pin"),
        "share": get("dashboard", "share").lower() in ("yes", "true", "on", "1"),
        "port": int(get("dashboard", "port") or 8095),
        "hostname": get("cloudflare", "hostname"),
        "tunnel": get("cloudflare", "tunnel") or "home-dashboard",
        "login_file": get("alexa", "login_file") or "alexa_login.json",
        "hide": [h for h in get("alexa", "hide").split(",") if h.strip()],
        "routine_echo": get("alexa", "routine_echo"),
        "heating_url": get("heating", "url") or "http://localhost:8090",
        "heating_pin": get("heating", "pin"),
        "heating_link": get("heating", "link"),
        "race_url": get("race", "url") or "http://localhost:8080",
        "tv_ip": get("devices", "tv"),
        "tv_mac": get("devices", "tv_mac"),
        "tv_name": get("devices", "tv_name"),
        "ps5_ip": get("devices", "ps5"),
        "ps5_name": get("devices", "ps5_name"),
        "xbox_ip": get("devices", "xbox"),
        "xbox_name": get("devices", "xbox_name"),
        "postcode": get("location", "postcode"),
        "psn_npsso": get("playstation", "npsso"),
        "psn_online_id": get("playstation", "online_id"),
        "race_link": get("race", "link"),
    }


def page_secret():
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text().strip()
    value = secrets.token_hex(32)
    SECRET_PATH.write_text(value)
    return value


# ---------- other dashboards ----------

async def read_heating(session, config):
    """Ask Moby's Heat for its current state, logging in with its PIN if it has one."""
    base = config["heating_url"].rstrip("/")
    try:
        async with session.get(base + "/api/status") as r:
            if r.status == 401 and config["heating_pin"]:
                async with session.post(base + "/api/login", json={"pin": config["heating_pin"]}):
                    pass
                async with session.get(base + "/api/status") as r2:
                    data = await r2.json(content_type=None)
            else:
                data = await r.json(content_type=None)
        if not data.get("ok"):
            return {"running": True, "error": data.get("error", "No data")}
        d = data["devices"][0]
        smart = data.get("smart") or {}
        return {
            "running": True, "name": d.get("name"), "room": d.get("room"), "target": d.get("target"),
            "mode": d.get("mode_name"), "boost_ends": d.get("boost_ends"),
            "outside": data.get("outside"), "smart_on": smart.get("enabled"),
            "smart_note": smart.get("note"),
        }
    except Exception:
        return {"running": False}


async def is_running(session, url):
    try:
        async with session.get(url, allow_redirects=False) as r:
            return r.status < 500
    except Exception:
        return False


async def background(app):
    """Keep everything fresh. Each part runs on its own, so a slow one can't hold up the others."""
    alexa, config, state = app[ALEXA], app[CONFIG], app[STATE]

    async def alexa_loop():
        while True:
            try:
                await asyncio.wait_for(alexa.refresh(), 60)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                print(f"Alexa: {err or err.__class__.__name__}")
            await asyncio.sleep(30)

    async def devices_loop():
        async with aiohttp.ClientSession() as s:
            while True:
                try:
                    await asyncio.wait_for(app[DEVICES].refresh(s), 25)
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    print(f"TV and consoles: {err or 'took too long'}")
                await asyncio.sleep(30)

    async def others_loop():
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=jar,
                                         timeout=aiohttp.ClientTimeout(total=10)) as s:
            while True:
                try:
                    await app[WEATHER].refresh(s)
                except Exception as err:
                    print(f"Weather: {err}")
                try:
                    state["heating"] = await read_heating(s, config)
                    state["race_running"] = await is_running(s, config["race_url"])
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    print(f"Heating or race check: {err}")
                await asyncio.sleep(30)

    async def psn_loop():
        while True:
            try:
                await asyncio.wait_for(app[PSN].refresh(), 60)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                print(f"PlayStation: {err or 'took too long'}")
            await asyncio.sleep(PSN_EVERY)

    await asyncio.gather(alexa_loop(), devices_loop(), others_loop(), psn_loop())


# ---------- PIN ----------

def pin_token(app):
    return hmac.new(app[SECRET].encode(), app[PIN].encode(), hashlib.sha256).hexdigest()


@web.middleware
async def pin_check(request, handler):
    app = request.app
    if not app[PIN] or not request.path.startswith("/api/") or request.path == "/api/login":
        return await handler(request)
    if hmac.compare_digest(request.cookies.get(COOKIE_NAME, ""), pin_token(app)):
        return await handler(request)
    return web.json_response({"ok": False, "error": "PIN needed", "need_pin": True}, status=401)


async def api_login(request):
    app = request.app
    if not app[PIN]:
        return web.json_response({"ok": True})
    lock = app[PIN_LOCK]
    if time.time() < lock["until"]:
        wait = int(lock["until"] - time.time()) // 60 + 1
        return web.json_response(
            {"ok": False, "error": f"Too many wrong tries. Try again in {wait} min."}, status=429)
    body = await request.json()
    if hmac.compare_digest(str(body.get("pin", "")), app[PIN]):
        lock["fails"] = lock["lockouts"] = 0
        response = web.json_response({"ok": True})
        secure = request.headers.get("X-Forwarded-Proto") == "https" or request.secure
        response.set_cookie(COOKIE_NAME, pin_token(app), max_age=180 * 86400,
                            httponly=True, samesite="Strict", secure=secure)
        return response
    lock["fails"] += 1
    if lock["fails"] >= MAX_PIN_TRIES:
        lock["fails"] = 0
        lock["lockouts"] += 1
        wait = min(24 * 3600, PIN_LOCKOUT_SECONDS * 2 ** (lock["lockouts"] - 1))
        lock["until"] = time.time() + wait
        who = request.headers.get("CF-Connecting-IP") or request.remote or "unknown"
        log(app, f"Page locked for {wait // 60} min after wrong PINs (from {who})", ok=False)
    return web.json_response({"ok": False, "error": "Wrong PIN"}, status=401)


# ---------- routes ----------

def log(app, text, ok=True):
    entries = app[STATE].setdefault("log", [])
    entries.insert(0, {"ts": int(time.time()), "text": text, "ok": ok})
    del entries[15:]


async def page(request):
    return web.Response(text=PAGE_PATH.read_text(encoding="utf-8"), content_type="text/html",
                        headers={"Cache-Control": "no-cache"})


async def static_folder(request):
    name = request.match_info["name"]
    path = STATIC_PATH / name
    if "/" in name or "\\" in name or name.startswith(".") or not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path, headers={
        "Content-Type": CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        "Cache-Control": "max-age=86400"})


def static_file(name):
    async def handler(request):
        return web.FileResponse(STATIC_PATH / name, headers={
            "Content-Type": CONTENT_TYPES.get(Path(name).suffix.lower(), "application/octet-stream")})
    return handler


def devices_with_game(app):
    """Add what's being played (from the PlayStation account) to the PS5 tile."""
    devices = app[DEVICES].snapshot()
    psn = app[PSN].snapshot()
    if psn and "ps5" in devices:
        ps5 = devices["ps5"]
        if ps5.get("state") == "on" and psn.get("online") and psn.get("game") \
                and psn.get("platform") in ("PS5", ""):
            ps5["game"] = psn["game"]
            ps5["game_icon"] = psn.get("icon")
        ps5["psn_warning"] = psn.get("warning")
    return devices


def status_payload(app):
    config, state = app[CONFIG], app[STATE]
    return {
        "ok": True,
        "now": int(time.time()),
        "alexa": app[ALEXA].snapshot(config["hide"]),
        "heating": dict(state.get("heating") or {"running": False},
                        link=config["heating_link"] or config["heating_url"]),
        "race": {"running": state.get("race_running", False),
                 "link": config["race_link"] or config["race_url"],
                 "port": URL(config["race_url"]).port or 8080},
        "devices": devices_with_game(app),
        "weather": app[WEATHER].snapshot(),
        "log": state.get("log", []),
    }


async def api_status(request):
    return web.json_response(status_payload(request.app))


async def api_switch(request):
    app = request.app
    alexa = app[ALEXA]
    body = await request.json()
    device_id = str(body.get("id", ""))
    name = alexa.name_of(device_id)
    try:
        if "brightness" in body:
            value = int(body["brightness"])
            await alexa.set_brightness(device_id, value)
            log(app, f"{name} set to {value}%")
        else:
            on = bool(body.get("on"))
            await alexa.switch(device_id, on)
            log(app, f"{name} switched {'on' if on else 'off'}")
    except Exception as err:
        log(app, f"{name}: couldn't change it ({err})", ok=False)
        return web.json_response({"ok": False, "error": f"Alexa didn't do that: {err}"}, status=502)
    return web.json_response(status_payload(app))


async def api_routine(request):
    app = request.app
    name = str((await request.json()).get("name", ""))
    try:
        await app[ALEXA].run_routine(name)
        log(app, f"Ran routine: {name}")
    except Exception as err:
        log(app, f"Routine {name} failed ({err})", ok=False)
        return web.json_response({"ok": False, "error": f"Couldn't run it: {err}"}, status=502)
    return web.json_response(status_payload(app))


async def api_tv(request):
    app = request.app
    tv = app[DEVICES].tv
    body = await request.json()
    action = str(body.get("action", ""))
    if not tv:
        return web.json_response({"ok": False, "error": "No TV set up in home_config.ini"}, status=400)
    words = {"power_on": "TV switched on", "power_off": "TV switched off", "volume_up": None,
             "volume_down": None, "mute": "TV muted or unmuted"}
    try:
        await tv.act(action, body.get("app_id"))
        if action == "app":
            log(app, f"TV: opened {body.get('app_name') or 'an app'}")
        elif words.get(action):
            log(app, words[action])
    except Exception as err:
        hint = (" Look at the TV and choose Allow, then try again." if tv.needs_allow else "")
        log(app, f"TV: couldn't do that ({err})", ok=False)
        return web.json_response({"ok": False, "error": f"The TV didn't respond.{hint}"}, status=502)
    async with aiohttp.ClientSession() as s:
        await app[DEVICES].refresh(s)
    return web.json_response(status_payload(app))


async def api_echo(request):
    app = request.app
    alexa = app[ALEXA]
    body = await request.json()
    serial, action, value = str(body.get("serial", "")), str(body.get("action", "")), body.get("value")
    name = alexa.echo_name(serial)
    words = {"play": "playing", "pause": "paused", "next": "next track", "previous": "previous track",
             "stop": "stopped"}
    try:
        await alexa.echo_control(serial, action, value)
        if action == "dnd":
            log(app, f"{name}: Do Not Disturb {'on' if value else 'off'}")
        elif action in words:
            log(app, f"{name}: {words[action]}")
    except Exception as err:
        log(app, f"{name}: couldn't do that ({err})", ok=False)
        return web.json_response({"ok": False, "error": f"Alexa didn't do that: {err}"}, status=502)
    return web.json_response(status_payload(app))


async def api_refresh(request):
    try:
        await request.app[ALEXA].refresh(force=True)
    except Exception as err:
        return web.json_response({"ok": False, "error": f"Alexa: {err}"}, status=502)
    return web.json_response(status_payload(request.app))


def build_app(alexa, config, pin):
    app = web.Application(middlewares=[pin_check])
    app[ALEXA] = alexa
    app[DEVICES] = Devices(config, HERE)
    app[WEATHER] = Weather(config["postcode"], HERE / "weather_location.txt")
    app[PSN] = PlayStation(config["psn_npsso"], HERE / "psn_token.json", config["psn_online_id"])
    app[CONFIG] = config
    app[PIN] = pin or ""
    app[SECRET] = page_secret()
    app[PIN_LOCK] = {"fails": 0, "lockouts": 0, "until": 0}
    app[STATE] = {}
    app[JOBS] = {}

    async def on_startup(app):
        await alexa.start()
        try:
            await alexa.refresh(force=True)
        except Exception as err:
            print(f"Alexa: first refresh failed ({err}), will keep trying")
        app[JOBS]["background"] = asyncio.create_task(background(app))

    async def on_cleanup(app):
        if "background" in app[JOBS]:
            app[JOBS]["background"].cancel()
        await alexa.stop()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", page)
    app.router.add_get("/static/{name}", static_folder)
    app.router.add_get("/manifest.webmanifest", static_file("manifest.webmanifest"))
    app.router.add_get("/favicon.ico", static_file("favicon.ico"))
    app.router.add_get("/apple-touch-icon.png", static_file("apple-touch-icon.png"))
    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/login", api_login)
    app.router.add_post("/api/switch", api_switch)
    app.router.add_post("/api/routine", api_routine)
    app.router.add_post("/api/refresh", api_refresh)
    app.router.add_post("/api/tv", api_tv)
    app.router.add_post("/api/echo", api_echo)
    return app


# ---------- your own web address through Cloudflare ----------

def find_cloudflared():
    found = shutil.which("cloudflared")
    if found:
        return found
    for guess in (r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
                  r"C:\Program Files\cloudflared\cloudflared.exe"):
        if os.path.exists(guess):
            return guess
    return None


def start_tunnel(hostname, tunnel, port):
    exe = find_cloudflared()
    if not exe:
        print("Couldn't find cloudflared, so the web address isn't running.")
        return
    cmd = [exe, "tunnel", "--no-autoupdate", "run", "--url", f"http://localhost:{port}", tunnel]

    def run():
        announced = False
        while True:
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", errors="replace")
                for line in proc.stdout:
                    low = line.lower()
                    if "registered tunnel connection" in low and not announced:
                        print(f"Online at https://{hostname}")
                        announced = True
                    elif "origin cert" in low or ("tunnel" in low and "not found" in low):
                        print(f"Cloudflare says: {line.strip()}")
                proc.wait()
            except Exception as err:
                print(f"Web address: {err}")
            print("The web address stopped, starting it again in 30 seconds")
            announced = False
            time.sleep(30)

    threading.Thread(target=run, daemon=True).start()


def main():
    config = load_config()
    parser = argparse.ArgumentParser(description="Moby's Home: one page for the house")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    port = args.port or config["port"]
    pin = config["pin"]
    if pin and not pin.isdigit():
        sys.exit("The PIN should be numbers only")
    if config["hostname"] and len(pin) < 6:
        sys.exit("To use a web address, set a PIN of at least 6 numbers in home_config.ini first.")

    host = "0.0.0.0" if config["share"] else "127.0.0.1"
    print(f"\nMoby's Home on http://localhost:{port}  (Ctrl+C to stop)")
    if config["hostname"]:
        print(f"Starting your web address, https://{config['hostname']}")
        start_tunnel(config["hostname"], config["tunnel"], port)
    alexa = Alexa(HERE / config["login_file"], HERE / "alexa_data", config["routine_echo"])
    web.run_app(build_app(alexa, config, pin), host=host, port=port, print=None)


if __name__ == "__main__":
    main()
