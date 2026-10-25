"""
Lists what the BT Smart Hub knows about each device: name, address, MAC,
whether it's connected now, and how it's connected. No password, only reads.

    py hub_devices.py
"""

import re
import sys
import urllib.parse
import urllib.request

HUB = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.254"
req = urllib.request.Request(f"http://{HUB}/cgi/cgi_basicMyDevice.js",
                             headers={"User-Agent": "Mozilla/5.0", "Referer": f"http://{HUB}/"})
with urllib.request.urlopen(req, timeout=8) as r:
    body = r.read().decode("utf-8", "replace")

# What lists does the file hold, and what does one entry look like?
print("Lists in the file:")
for name in re.findall(r"var\s+(\w+)\s*=", body):
    print("  " + name)
entries = re.findall(r"\{[^{}]*mac:'[^']+'[^{}]*\}", body)
keys = {}
for e in entries:
    for k in re.findall(r"(\w+):'", e):
        keys[k] = keys.get(k, 0) + 1
print("\nFields seen:", ", ".join(f"{k} ({n})" for k, n in keys.items()))

print("\nDevices with a name:")
seen = set()
for e in entries:
    fields = dict(re.findall(r"(\w+):'([^']*)'", e))
    fields = {k: urllib.parse.unquote(v) for k, v in fields.items()}
    name = fields.get("hostname") or fields.get("name") or fields.get("device_name") or fields.get("devicename")
    mac = fields.get("mac", "").lower()
    if not name or mac in seen:
        continue
    seen.add(mac)
    other = {k: v for k, v in fields.items() if k not in ("hostname", "name", "mac") and len(v) < 40}
    print(f"  {name[:28]:<28} {mac}  {other}")

print("\nPaste all of that to Claude.")
