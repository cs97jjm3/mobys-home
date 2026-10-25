"""
Checks each part of Moby's Home one at a time and says what happens.
Run it in the smarthome folder:   py check_home.py
It doesn't change anything.
"""

import asyncio
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))


def show(label, ok, detail=""):
    print(f"  {'OK  ' if ok else 'FAIL'} {label}{(': ' + str(detail)) if detail else ''}")


async def main():
    print(f"Python {sys.version.split()[0]} in {HERE}\n")

    print("Files")
    hub = (HERE / "home_hub.py").read_text(encoding="utf-8")
    show("home_hub.py is the latest version", "devices_loop" in hub)
    dev = HERE / "devices_link.py"
    show("devices_link.py is there", dev.exists())
    if dev.exists():
        show("devices_link.py is the latest version", "_load_apps_quietly" in dev.read_text(encoding="utf-8"))
    page = (HERE / "home_page.html").read_text(encoding="utf-8")
    show("home_page.html has the TV card", "mediaCard" in page)

    print("\nSettings")
    try:
        import home_hub
        config = home_hub.load_config()
        for key in ("tv_ip", "tv_mac", "ps5_ip", "xbox_ip", "heating_url", "race_url"):
            show(key, bool(config.get(key)), config.get(key) or "missing")
        show("heating PIN filled in", bool(config.get("heating_pin")))
    except Exception:
        show("reading home_config.ini", False, traceback.format_exc(limit=1))
        return

    import aiohttp
    print("\nOther dashboards")
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar, timeout=aiohttp.ClientTimeout(total=10)) as s:
        t = time.time()
        try:
            heat = await home_hub.read_heating(s, config)
            show("Moby's Heat", heat.get("room") is not None, heat)
        except Exception as err:
            show("Moby's Heat", False, repr(err))
        try:
            async with s.get(config["heating_url"].rstrip("/") + "/api/status") as r:
                show("Moby's Heat answers at all", True, f"HTTP {r.status}")
        except Exception as err:
            show("Moby's Heat answers at all", False, repr(err))
        try:
            show("Race dashboard", await home_hub.is_running(s, config["race_url"]))
        except Exception as err:
            show("Race dashboard", False, repr(err))

    print("\nTV and consoles")
    try:
        import devices_link as dl
    except Exception:
        show("loading devices_link.py", False, traceback.format_exc(limit=2))
        return
    async with aiohttp.ClientSession() as s:
        if config.get("tv_ip"):
            tv = dl.SamsungTV(config["tv_ip"], config["tv_mac"], HERE / "samsung_token.txt")
            t = time.time()
            try:
                info = await tv._device_info(s)
                show("TV info page", bool(info),
                     (info or {}).get("device", {}).get("PowerState", "no answer"))
            except Exception as err:
                show("TV info page", False, repr(err))
            show("TV remote port 8002 open", await tv._port_open(8002))
            show("TV token saved (you pressed Allow)", (HERE / "samsung_token.txt").exists())
            print(f"     ({time.time() - t:.1f}s)")
        if config.get("ps5_ip"):
            t = time.time()
            try:
                r = await dl.ps5_status(config["ps5_ip"], asyncio.Lock())
                show("PS5", True, f"{r}  ({time.time() - t:.1f}s)")
            except Exception as err:
                show("PS5", False, repr(err))
        if config.get("xbox_ip"):
            t = time.time()
            try:
                r = await dl.xbox_status(config["xbox_ip"])
                show("Xbox", True, f"{r}  ({time.time() - t:.1f}s)")
            except Exception as err:
                show("Xbox", False, repr(err))
        try:
            d = dl.Devices(config, HERE)
            t = time.time()
            await asyncio.wait_for(d.refresh(s), 25)
            show("All three together", True, f"{list(d.snapshot())}  ({time.time() - t:.1f}s)")
        except Exception as err:
            show("All three together", False, repr(err))

    print("\nDone. Copy everything above and paste it to Claude.")


if __name__ == "__main__":
    asyncio.run(main())
