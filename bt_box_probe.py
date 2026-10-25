"""
Has a look at what the BT TV box says about itself on the home network.
Find the box's address on the BT hub's device list first, then run:

    py bt_box_probe.py 192.168.1.xx

Run it once with the box ON, and once with it in STANDBY, and paste both to Claude.
Only looks; it doesn't change anything on the box.
"""

import asyncio
import re
import socket
import sys
import urllib.request

if len(sys.argv) < 2:
    print("Put the box's address after the name, e.g.  py bt_box_probe.py 192.168.1.50")
    raise SystemExit
BOX = sys.argv[1]

# 1. Is it there?
print(f"=== {BOX} ===")
try:
    print("Name on the network:", socket.gethostbyaddr(BOX)[0])
except Exception:
    print("Name on the network: (none)")

# 2. Does it announce itself? (the way TVs and boxes find each other)
print("\n--- Announcements (SSDP / UPnP / DIAL) ---")
search = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
          "MX: 2\r\nST: ssdp:all\r\n\r\n").encode()
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
s.settimeout(4)
for _ in range(2):
    s.sendto(search, ("239.255.255.250", 1900))
seen, locations = set(), set()
try:
    while True:
        data, addr = s.recvfrom(4096)
        if addr[0] != BOX:
            continue
        text = data.decode("utf-8", "replace")
        headers = dict((k.strip().upper(), v.strip()) for k, v in
                       (line.split(":", 1) for line in text.splitlines() if ":" in line))
        key = (headers.get("ST"), headers.get("LOCATION"))
        if key in seen:
            continue
        seen.add(key)
        print(f"  ST: {headers.get('ST')}\n    SERVER: {headers.get('SERVER')}\n    LOCATION: {headers.get('LOCATION')}")
        if headers.get("LOCATION"):
            locations.add(headers["LOCATION"])
except socket.timeout:
    pass
if not seen:
    print("  Nothing announced")

for url in sorted(locations):
    print(f"\n--- {url} ---")
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            xml = r.read().decode("utf-8", "replace")
        for tag in ("friendlyName", "manufacturer", "modelName", "modelNumber", "serviceType", "SCPDURL"):
            for value in re.findall(f"<{tag}>(.*?)</{tag}>", xml):
                print(f"  {tag}: {value}")
    except Exception as err:
        print(f"  couldn't read it ({err.__class__.__name__})")

# 3. Which doors are open?
print("\n--- Open ports ---")
PORTS = sorted(set(list(range(1, 1025)) + [1400, 1900, 2869, 3000, 4444, 5000, 5353, 5555, 7000, 7001,
               6466, 6467, 8000, 8001, 8008, 8009, 8060, 8080, 8081, 8443, 8888, 9000, 9080, 9090, 10000,
               49152, 49153, 49154, 50000, 50001, 50002, 52235, 55000, 56789, 56790]))


async def check(port, sem):
    async with sem:
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(BOX, port), 0.8)
            w.close()
            return port
        except Exception:
            return None


async def scan():
    sem = asyncio.Semaphore(200)
    found = [p for p in await asyncio.gather(*(check(p, sem) for p in PORTS)) if p]
    return found

open_ports = asyncio.run(scan())
print("  " + (", ".join(map(str, open_ports)) or "none"))

for port in open_ports:
    if port in (22, 23, 25, 53, 139, 445):
        continue
    for scheme in ("http", "https"):
        try:
            import ssl
            ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(f"{scheme}://{BOX}:{port}/", timeout=3,
                                        context=ctx if scheme == "https" else None) as r:
                body = r.read(300).decode("utf-8", "replace").replace("\n", " ")
                print(f"  {scheme}://{BOX}:{port}/ -> {r.status} {r.headers.get('Server', '')} {body[:150]}")
                break
        except urllib.error.HTTPError as err:
            print(f"  {scheme}://{BOX}:{port}/ -> {err.code} {err.headers.get('Server', '')}")
            break
        except Exception:
            continue

print("\nPaste all of that to Claude.")
