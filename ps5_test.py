"""
Tries every way of asking the PS5 if it's there, and says which one gets an answer.
Run with the PS5 switched on:   py ps5_test.py
"""

import socket
import subprocess
import sys
import time

PS5 = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.69"
MESSAGE = b"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:00030010\n"


def ask(label, target, local_port, broadcast=False):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if broadcast:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.bind(("0.0.0.0", local_port))
    except OSError as err:
        print(f"  {label}: couldn't use port {local_port} ({err})")
        s.close()
        return
    s.settimeout(2)
    started = time.time()
    try:
        for _ in range(2):
            s.sendto(MESSAGE, (target, 9302))
            try:
                data, addr = s.recvfrom(4096)
                first = data.decode("utf-8", "replace").splitlines()[0]
                print(f"  {label}: ANSWER from {addr[0]} in {time.time() - started:.1f}s -> {first}")
                for line in data.decode("utf-8", "replace").splitlines()[1:]:
                    if line.split(":")[0] in ("host-name", "host-type", "running-app-name"):
                        print(f"      {line}")
                return
            except socket.timeout:
                continue
        print(f"  {label}: no answer")
    except OSError as err:
        print(f"  {label}: error ({err})")
    finally:
        s.close()


print(f"Asking the PS5 at {PS5}\n")
ask("1. Direct, from port 9303", PS5, 9303)
ask("2. Direct, from any port", PS5, 0)
ask("3. To everyone on the network, from port 9303", "255.255.255.255", 9303, broadcast=True)
ask("4. To everyone on the network, from any port", "255.255.255.255", 0, broadcast=True)

ping = subprocess.run(["ping", "-n", "1", "-w", "1000", PS5], capture_output=True, text=True)
print(f"\n  5. Ping: {'answers' if ping.returncode == 0 else 'no answer'}")
print("\nPaste all of that to Claude.")
