"""
Reads the EE TV box's full device description (port 56790, /dd.xml), then
follows any addresses it mentions, just reading them. Changes nothing.

    py bt_box_dd.py 192.168.1.70
"""

import re
import socket
import sys

BOX = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.70"


def get(port, path):
    try:
        with socket.create_connection((BOX, port), timeout=4) as s:
            s.sendall(f"GET {path} HTTP/1.1\r\nHost: {BOX}:{port}\r\nUser-Agent: Moby\r\nConnection: close\r\n\r\n".encode())
            s.settimeout(4)
            data = b""
            while len(data) < 20000:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        text = data.decode("utf-8", "replace")
        head, _, body = text.partition("\r\n\r\n")
        return head.split("\r\n", 1)[0], head, body
    except Exception as err:
        return f"(no answer: {err.__class__.__name__})", "", ""


status, head, xml = get(56790, "/dd.xml")
print("=== /dd.xml on 56790 ===")
print(head)
print()
print(xml)

# Anything that looks like an address or a path inside it
found = set(re.findall(r"https?://[^\s<\"']+", xml + head))
found |= set(re.findall(r">(/[^<\s]+)<", xml))
print("\n=== Following what it mentions ===")
for item in sorted(found):
    if item.startswith("http"):
        m = re.match(r"https?://([^/:]+)(?::(\d+))?(/.*)?", item)
        host, port, path = m.group(1), int(m.group(2) or 80), m.group(3) or "/"
        if host != BOX:
            print(f"  {item}  (another address, not followed)")
            continue
    else:
        port, path = 56790, item
    for p in dict.fromkeys([port, 56789, 56790, 8888]):
        st, _, body = get(p, path)
        if " 404" not in st:
            print(f"\n  port {p}{path} -> {st}\n  {body[:1500]}")

print("\nPaste all of that to Claude.")
