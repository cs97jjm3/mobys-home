"""
A closer look at the EE TV box's three open doors (8888, 56789, 56790).
Tries some common addresses on each and shows exactly what comes back.
Only reads; doesn't change anything.

    py bt_box_look.py 192.168.1.70
"""

import base64
import os
import socket
import sys

BOX = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.70"
PORTS = [8888, 56789, 56790]
PATHS = ["/", "/status", "/info", "/api", "/api/v1", "/device", "/devices", "/state", "/power",
         "/description.xml", "/dd.xml", "/ssdp/device-desc.xml", "/apps", "/remote", "/rc",
         "/key", "/keys", "/channel", "/channels", "/now", "/nowplaying", "/epg", "/version",
         "/health", "/ping", "/favicon.ico", "/index.html", "/ws", "/websocket"]


def raw_get(port, path, extra=""):
    try:
        with socket.create_connection((BOX, port), timeout=3) as s:
            s.sendall(f"GET {path} HTTP/1.1\r\nHost: {BOX}:{port}\r\nUser-Agent: Moby\r\n{extra}Connection: close\r\n\r\n".encode())
            s.settimeout(3)
            data = b""
            while len(data) < 3000:
                chunk = s.recv(1024)
                if not chunk:
                    break
                data += chunk
            return data.decode("utf-8", "replace")
    except Exception as err:
        return f"(no answer: {err.__class__.__name__})"


for port in PORTS:
    print(f"\n=========== port {port} ===========")
    first = raw_get(port, "/")
    print("Full reply to / :")
    print("  " + first[:600].replace("\r\n", "\n  "))
    print("\nOther addresses (only the ones that aren't plain 404):")
    for path in PATHS[1:]:
        reply = raw_get(port, path)
        status = reply.split("\r\n", 1)[0]
        if " 404" not in status:
            body = reply.split("\r\n\r\n", 1)[-1][:200].replace("\n", " ")
            print(f"  {path:<22} {status}  {body}")
    key = base64.b64encode(os.urandom(16)).decode()
    ws = raw_get(port, "/", f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n")
    print(f"  WebSocket try: {ws.split(chr(13), 1)[0]}")
    # Some boxes don't speak web at all: see if it says anything first
    try:
        with socket.create_connection((BOX, port), timeout=3) as s:
            s.settimeout(2)
            hello = s.recv(200)
            print(f"  Says on connect: {hello[:120]!r}")
    except socket.timeout:
        print("  Says on connect: nothing")
    except Exception as err:
        print(f"  Says on connect: ({err.__class__.__name__})")

print("\nPaste all of that to Claude.")
