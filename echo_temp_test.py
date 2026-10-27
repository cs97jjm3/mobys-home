"""
Looks for temperature readings from your Echos (newer Echo Dots and the Echo Show 8 have a thermometer).

    py echo_temp_test.py

Close Moby's Home first, so the two don't talk to Alexa at once. Only reads.
"""

import asyncio
import json
from pathlib import Path

from alexa_link import Alexa, text

HERE = Path(__file__).parent


async def main():
    alexa = Alexa(HERE / "alexa_login.json", HERE / "alexa_data")
    await alexa.start()
    try:
        await alexa.refresh(force=True)
        ids = {e["endpointId"]: text(e, "friendlyNameObject") for e in alexa.endpoints if e.get("endpointId")}
        raw = {}
        keys = list(ids)
        for i in range(0, len(keys), 25):
            raw.update(await alexa.api._device_handler._get_endpoints_features(keys[i:i + 25]))
        found = 0
        for eid, name in ids.items():
            feats = (raw.get(eid) or {}).get("features") or []
            for f in feats:
                props = f.get("properties") or []
                temp_like = "temperature" in (f.get("name") or "").lower() or any(
                    "Temperature" in (p.get("__typename") or "") for p in props)
                if temp_like:
                    found += 1
                    clean = [{k: v for k, v in p.items() if k not in ("timeOfSample", "accuracy")} for p in props]
                    print(f"{name}\n   feature: {f.get('name')} ({f.get('instance')})\n   {json.dumps(clean)}\n")
        print(f"{found} temperature features found." if found else
              "No temperature features found. Try in the Alexa app: Devices > the Echo > is there a temperature shown?")
        print("Paste all of that to Claude.")
    finally:
        await alexa.stop()

asyncio.run(main())
