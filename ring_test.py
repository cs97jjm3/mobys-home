"""
Signs in to Ring once, then checks what the doorbell will tell us.

    py -m pip install ring_doorbell
    py ring_test.py             sign in (first time), list the doorbell, recent presses, try a picture
    py ring_test.py listen      also waits 2 minutes for live presses: go and press the doorbell

The first time it asks for your Ring email, password and the code Ring texts or emails you.
After that the sign-in is kept in ring_token.json. Keep that file private, like a password.
Only reads (and takes a picture); it doesn't change any settings.
"""

import asyncio
import getpass
import json
import sys
import time
from pathlib import Path

from ring_doorbell import Auth, Requires2FAError, Ring, RingEventListener

HERE = Path(__file__).parent
TOKEN = HERE / "ring_token.json"
LISTEN_FILE = HERE / "ring_listen.json"
AGENT = "MobysHome-1.0"


def save_token(token):
    TOKEN.write_text(json.dumps(token))


async def sign_in():
    if TOKEN.exists():
        return Auth(AGENT, json.loads(TOKEN.read_text()), save_token)
    auth = Auth(AGENT, None, save_token)
    email = input("Ring email: ").strip()
    password = getpass.getpass("Ring password (it won't show as you type): ")
    try:
        await auth.async_fetch_token(email, password)
    except Requires2FAError:
        code = input("Ring has sent you a code. Type it here: ").strip()
        await auth.async_fetch_token(email, password, code)
    print("Signed in. Saved to ring_token.json\n")
    return auth


async def main():
    auth = await sign_in()
    ring = Ring(auth)
    await ring.async_create_session()
    await ring.async_update_data()
    devices = ring.devices()
    bells = list(devices.doorbots) + list(getattr(devices, "authorized_doorbots", []))
    others = [d.name for d in devices.all_devices if d not in bells] if hasattr(devices, "all_devices") else []
    print(f"Doorbells: {len(bells)}" + (f"   Other Ring devices: {', '.join(others)}" if others else ""))
    for d in bells:
        print(f"\n=== {d.name} ===")
        for label, getter in [("Model", lambda: d.model), ("Battery", lambda: d.battery_life),
                              ("Wi-Fi", lambda: f"{d.wifi_name}, {d.wifi_signal_strength} dBm ({d.wifi_signal_category})"),
                              ("Firmware", lambda: d.firmware), ("Ring Protect", lambda: d.has_subscription),
                              ("Motion detection", lambda: d.motion_detection), ("Volume", lambda: d.volume),
                              ("Chime type", lambda: d.existing_doorbell_type)]:
            try:
                print(f"  {label}: {getter()}")
            except Exception as err:
                print(f"  {label}: (not available: {err.__class__.__name__})")
        print("\n  Last 10 events:")
        try:
            for h in await d.async_history(limit=10):
                rec = (h.get("recording") or {}).get("status")
                print(f"    {h.get('created_at')}  {h.get('kind'):<10} answered={h.get('answered')}  recording={rec}")
        except Exception as err:
            print(f"    couldn't read history ({err})")
        print("\n  Taking a picture...")
        try:
            pic = await d.async_get_snapshot(retries=6, delay=2)
            if pic:
                out = HERE / f"ring_snapshot_{d.id}.jpg"
                out.write_bytes(pic)
                print(f"    Got one: {len(pic) // 1024} KB, saved as {out.name}. Have a look at it.")
            else:
                print("    No picture came back")
        except Exception as err:
            print(f"    No picture ({err})")

    if len(sys.argv) > 1 and sys.argv[1] == "listen":
        print("\nListening for 2 minutes. Go and press the doorbell, or walk past it...")
        saved = json.loads(LISTEN_FILE.read_text()) if LISTEN_FILE.exists() else None
        listener = RingEventListener(ring, saved, lambda creds: LISTEN_FILE.write_text(json.dumps(creds)))
        listener.add_notification_callback(
            lambda e: print(f"  {time.strftime('%H:%M:%S')}  {e.kind} at {e.device_name}  (state {e.state})"))
        await listener.start()
        await asyncio.sleep(120)
        await listener.stop()
        print("Done listening.")

    await auth.async_close()
    print("\nPaste all of that to Claude.")

asyncio.run(main())
