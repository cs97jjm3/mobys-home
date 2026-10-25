"""
Moby's Home helper: shares this computer's processor, memory, disk and
time-switched-on with Moby's Home, so the dashboard can show them.

It only shares those figures. It can't change or control anything.
Works with plain Python on Windows and on a Raspberry Pi (even an old one),
with nothing extra to install.

    Windows:       py moby_agent.py
    Raspberry Pi:  python3 moby_agent.py

Then leave it running. It answers on port 8097.
"""

import json
import os
import platform
import socket
import sys
import time

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:          # very old Python
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

PORT = 8097
WINDOWS = platform.system() == "Windows"
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- Windows ----------

if WINDOWS:
    import ctypes
    from ctypes import wintypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    def _times():
        idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        as_int = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime
        return as_int(idle), as_int(kernel) + as_int(user)

    def cpu_sample():
        return _times()

    def memory_percent():
        m = MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return int(m.dwMemoryLoad)

    def disk(path):
        free, total = ctypes.c_ulonglong(), ctypes.c_ulonglong()
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(path), None, ctypes.byref(total), ctypes.byref(free))
        return free.value, total.value

    def uptime():
        ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        return int(ctypes.windll.kernel32.GetTickCount64() / 1000)

    def temperature():
        return None

# ---------- Linux / Raspberry Pi ----------

else:
    def cpu_sample():
        with open("/proc/stat") as f:
            parts = [int(x) for x in f.readline().split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        return idle, sum(parts)

    def memory_percent():
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, value = line.split(":", 1)
                info[key] = int(value.split()[0])
        available = info.get("MemAvailable", info.get("MemFree", 0) + info.get("Cached", 0))
        return int(round(100 - available * 100.0 / info["MemTotal"]))

    def disk(path):
        s = os.statvfs(path)
        free = s.f_bavail * s.f_frsize
        used = (s.f_blocks - s.f_bfree) * s.f_frsize
        return free, used + free

    def uptime():
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))

    def temperature():
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return round(int(f.read()) / 1000.0, 1)
        except (IOError, OSError, ValueError):
            return None


def cpu_percent(before, after):
    idle = after[0] - before[0]
    total = after[1] - before[1]
    if WINDOWS:   # Windows' kernel time already includes idle time
        return int(round(100.0 * (total - idle) / total)) if total else 0
    return int(round(100.0 * (total - idle) / total)) if total else 0


LAST = {"cpu": cpu_sample(), "percent": 0}


def stats():
    now = cpu_sample()
    if now[1] != LAST["cpu"][1]:
        LAST["percent"] = cpu_percent(LAST["cpu"], now)
        LAST["cpu"] = now
    root = os.path.splitdrive(HERE)[0] + "\\" if WINDOWS else "/"
    free, total = disk(root)
    return {"cpu": LAST["percent"], "memory": memory_percent(),
            "disk_free_gb": int(round(free / 1e9)), "disk_used": int(round(100 - free * 100.0 / total)) if total else 0,
            "uptime": uptime(), "temp": temperature(), "name": socket.gethostname(), "system": platform.system()}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") != "/stats":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(stats()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):   # keep the window quiet
        pass


if __name__ == "__main__":
    print("Moby's Home helper on port {0}. Sharing processor, memory, disk and time on.".format(PORT))
    print("Leave this running. Close the window to stop it.")
    try:
        HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
