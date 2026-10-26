"""
Finds out how Alexa wants to be asked to change a light's colour.

    py colour_test.py                  lists which lights can do colour
    py colour_test.py "Lounge lamp"    also tries to change that light's colour

When you name a light, watch it. It tries three ways, two seconds apart:
    1. red      2. green      3. blue
then two warm/cool white ways:
    4. warm white      5. cool white
and finally puts it back to warm white. Tell Claude which colours it actually went.
Run this while Moby's Home is stopped, so the two don't talk to Alexa at once.
"""

import asyncio
import json
import sys
from pathlib import Path

from alexa_link import Alexa, text

HERE = Path(__file__).parent


async def main():
    alexa = Alexa(HERE / "alexa_login.json", HERE / "alexa_data")
    await alexa.start()
    try:
        await alexa.refresh(force=True)
        lights = {e["endpointId"]: text(e, "friendlyNameObject") for e in alexa.endpoints
                  if e.get("endpointId") and "LIGHT" in json.dumps(e.get("displayCategories") or {})}
        raw = await alexa.api._device_handler._get_endpoints_features(list(lights))
        print("Lights and what Alexa says they can do:\n")
        for eid, name in lights.items():
            feats = (raw.get(eid) or {}).get("features") or []
            colour_bits = []
            for f in feats:
                if f.get("name") in ("color", "colorTemperature", "colorProperties"):
                    ops = [o.get("name") for o in f.get("operations") or [] if o]
                    props = [{k: v for k, v in p.items() if k not in ("timeOfSample", "accuracy")}
                             for p in f.get("properties") or []]
                    colour_bits.append(f"{f['name']}: operations {ops}, now {props}")
            names = sorted({f.get("name") for f in feats if f.get("name")})
            print(f"  {name}")
            print(f"     features: {', '.join(names)}")
            for bit in colour_bits:
                print(f"     {bit}")
        if len(sys.argv) < 2:
            print("\nName one of the colour lights after the command to try changing it.")
            return
        target = sys.argv[1].strip().lower()
        eid = next((i for i, n in lights.items() if (n or "").lower() == target), None)
        if not eid:
            print(f"\nNo light called {sys.argv[1]!r}")
            return
        print(f"\nTrying {sys.argv[1]}. Watch it:\n")
        tries = [
            ("1 red (by name)", "color", "setColor", {"colorName": "red"}),
            ("2 green (hue/saturation)", "color", "setColor",
             {"color": {"hue": 120, "saturation": 1, "brightness": 1}}),
            ("3 blue (hue/saturation, flat)", "color", "setColor", {"hue": 240, "saturation": 1, "brightness": 1}),
            ("4 warm white (kelvin)", "colorTemperature", "setColorTemperature", {"colorTemperatureInKelvin": 2700}),
            ("5 cool white (by name)", "colorTemperature", "setColorTemperature", {"colorTemperatureName": "cool_white"}),
        ]
        for label, feature, op, payload in tries:
            try:
                await alexa._control(eid, feature, op, payload)
                print(f"  {label}: Alexa said OK")
            except Exception as err:
                print(f"  {label}: refused ({err})")
            await asyncio.sleep(2.5)
        try:
            await alexa._control(eid, "colorTemperature", "setColorTemperature", {"colorTemperatureInKelvin": 2700})
        except Exception:
            pass
        print("\nWhich colours did the light actually go? Paste all of this to Claude.")
    finally:
        await alexa.stop()

asyncio.run(main())
