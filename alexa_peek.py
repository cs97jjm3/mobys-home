"""
Read-only look at everything Alexa knows about in your house.

Logs in to your Amazon account (the same way the Alexa app does), then lists:
  - your Echo devices, and whether they're online
  - your Alexa routines
  - every smart home device Alexa controls (Smart Life lights, plugs and so
    on), with its current state: on/off, brightness, colour, temperature

It changes nothing. Everything is saved to alexa_devices.json next to this
script, with serial numbers and account IDs left out, so you can send it over.

Setup (once):
    pip install aioamazondevices

Run:
    python alexa_peek.py

Amazon login needs two-step verification with an authenticator app (Google
Authenticator, Microsoft Authenticator and so on). Text-message codes don't
work for this. The first run asks for your email, password and a 6-digit code;
after that the login is remembered in alexa_login.json. Keep that file private:
it lets anyone who has it use your Alexa account.
"""

import asyncio
import getpass
import json
import sys
from pathlib import Path

import aiohttp
from yarl import URL

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.const.http import REQUEST_AGENT, URI_NEXUS_GRAPHQL
from aioamazondevices.const.queries import QUERY_DEVICE_DATA
from aioamazondevices.exceptions import AmazonError, CannotAuthenticate
from aioamazondevices.structures import AmazonSaveDataConfig

HERE = Path(__file__).parent
LOGIN_FILE = HERE / "alexa_login.json"
DATA_DIR = HERE / "alexa_data"
OUT_FILE = HERE / "alexa_devices.json"


def text(node, key):
    """Pull the text out of Alexa's nested {"value": {"text": ...}} shape."""
    return (((node or {}).get(key) or {}).get("value") or {}).get("text")


def read_state(endpoint):
    """Turn Alexa's list of features into a simple {"power": "ON", ...}."""
    state = {}
    for feature in endpoint.get("features") or []:
        name = feature.get("name") or "feature"
        if feature.get("instance"):
            name += f" ({feature['instance']})"
        for prop in feature.get("properties") or []:
            if prop.get("error"):
                continue
            for key, value in prop.items():
                if key in ("name", "type", "accuracy", "error", "__typename",
                           "timeOfSample", "timeOfLastChange"):
                    continue
                if isinstance(value, dict) and set(value) == {"value"}:
                    value = value["value"]
                if value is not None:
                    state[f"{name}: {prop.get('name') or key}"] = value
    return state


async def list_all_endpoints(api):
    """Every device on the account, including other brands' lights and plugs."""
    session = api._session_state_data
    _, raw = await api._http_wrapper.session_request(
        method="POST",
        url=URL.joinpath(session.alexa_website_url, URI_NEXUS_GRAPHQL),
        input_data={"operationName": "getDevicesBaseData", "query": QUERY_DEVICE_DATA},
        json_data=True,
        extended_headers={"User-Agent": REQUEST_AGENT["Amazon"]},
    )
    data = await api._http_wrapper.response_to_json(raw, "endpoints")
    return ((data.get("data") or {}).get("listEndpoints") or {}).get("endpoints") or []


async def main():
    saved_login = json.loads(LOGIN_FILE.read_text()) if LOGIN_FILE.exists() else {}
    login_data = saved_login.get("login")
    email = saved_login.get("email") or input("Amazon email: ").strip()
    password = "" if login_data else getpass.getpass("Amazon password: ")
    DATA_DIR.mkdir(exist_ok=True)

    async with aiohttp.ClientSession() as http:
        api = AmazonEchoApi(http, email, password,
                            save_data=AmazonSaveDataConfig(path=DATA_DIR),
                            login_data=login_data)
        try:
            if login_data:
                await api.login.login_mode_stored_data()
            else:
                code = input("6-digit code from your authenticator app: ").strip()
                saved = await api.login.login_mode_interactive(code)
                LOGIN_FILE.write_text(json.dumps({"email": email, "login": saved}))
                print("Logged in. The login is saved in alexa_login.json, so next time "
                      "it won't ask.")
        except CannotAuthenticate as err:
            sys.exit(f"Amazon didn't accept the login: {err}\n"
                     "Check the email, password and code, and that your Amazon account "
                     "uses an authenticator app for two-step verification.")

        # Echo devices
        echos = []
        for device in (await api.get_devices_data()).values():
            echos.append({
                "name": device.account_name,
                "model": device.model,
                "manufacturer": device.manufacturer,
                "family": device.device_family,
                "online": device.online,
            })

        # Routines
        try:
            await api.update_routines()
            routines = list(api.routines)
        except AmazonError as err:
            routines = [f"(couldn't read routines: {err})"]

        # Every smart home device, with its current state
        endpoints = await list_all_endpoints(api)
        ids = [e["endpointId"] for e in endpoints if e.get("endpointId")]
        features = {}
        for start in range(0, len(ids), 25):
            try:
                features.update(await api._device_handler._get_endpoints_features(
                    ids[start:start + 25]))
            except AmazonError as err:
                print(f"Couldn't read the state of some devices: {err}")

        smart_home = []
        for e in endpoints:
            meta = e.get("alexaEnabledMetadata") or {}
            if meta.get("category") == "APP":
                continue
            categories = e.get("displayCategories") or {}
            primary = ((categories.get("primary") or {}).get("value"))
            smart_home.append({
                "name": text(e, "friendlyNameObject"),
                "manufacturer": text(e, "manufacturer"),
                "model": text(e, "model"),
                "type": primary,
                "endpoint_id": e.get("endpointId"),
                "state": read_state(features.get(e.get("endpointId"), {})),
            })
        smart_home.sort(key=lambda d: ((d["type"] or ""), (d["name"] or "")))

    result = {"echo_devices": echos, "routines": routines, "smart_home_devices": smart_home}
    OUT_FILE.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    print(f"\nEcho devices: {len(echos)}")
    for d in echos:
        print(f"  {d['name']:<28} {d['model'] or '':<20} {'online' if d['online'] else 'offline'}")
    print(f"\nRoutines: {len(routines)}")
    for r in routines:
        print(f"  {r}")
    print(f"\nSmart home devices: {len(smart_home)}")
    for d in smart_home:
        power = next((v for k, v in d["state"].items() if "power" in k.lower()), "")
        print(f"  {(d['name'] or '?'):<28} {(d['type'] or ''):<14} "
              f"{(d['manufacturer'] or ''):<22} {power}")
    print(f"\nEverything is saved in {OUT_FILE.name}. Have a look, then send it over.")


if __name__ == "__main__":
    asyncio.run(main())
