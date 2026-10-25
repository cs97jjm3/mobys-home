"""
Watches how fast the EE TV box is downloading, using the BT hub's device list
(no password needed). Reads every 15 seconds for 2 minutes. Only reads.

    py hub_rate_test.py
"""

import re
import sys
import time
import urllib.parse
import urllib.request

HUB = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.254"
MAC = (sys.argv[2] if len(sys.argv) > 2 else "7C:16:89:9C:05:97").lower()


def read():
    req = urllib.request.Request(f"http://{HUB}/cgi/cgi_basicMyDevice.js",
                                 headers={"User-Agent": "Mozilla/5.0", "Referer": f"http://{HUB}/"})
    with urllib.request.urlopen(req, timeout=6) as r:
        body = r.read().decode("utf-8", "replace")
    for mac, tx, rx in re.findall(r"mac:'([^']+)',tx:'(\d+)',rx:'(\d+)'", body):
        if urllib.parse.unquote(mac).lower() == MAC:
            return int(tx), int(rx)
    return None


last = read()
if not last:
    print("Couldn't find the EE box in the hub's list")
    raise SystemExit
last_time = time.time()
print(f"Start: received {last[1] / 1e9:.2f} GB so far. Checking every 15 seconds...\n")
for _ in range(8):
    time.sleep(15)
    now = read()
    t = time.time()
    if not now:
        print("  (missing this time)")
        continue
    got = now[1] - last[1]
    mbps = got * 8 / (t - last_time) / 1e6
    print(f"  {time.strftime('%H:%M:%S')}  +{got / 1e6:8.1f} MB   {mbps:6.2f} Mbit/s"
          f"{'   (no change)' if got == 0 else ''}")
    last, last_time = now, t
print("\nPaste all of that to Claude, and say what was on the box at the time.")
