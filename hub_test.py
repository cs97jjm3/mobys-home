"""
Looks at the BT Smart Hub's pages WITHOUT a password, to see whether the
device list and data figures can be read. Only reads; changes nothing.

    py hub_test.py
    py hub_test.py 192.168.1.254 7C:16:89:9C:05:97

Run it twice, a minute apart, while something is streaming on the EE box.
"""

import re
import sys
import urllib.request

HUB = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.254"
MAC = (sys.argv[2] if len(sys.argv) > 2 else "7C:16:89:9C:05:97").lower()
mac_forms = {MAC, MAC.replace(":", "-"), MAC.replace(":", ""), MAC.upper(),
             MAC.upper().replace(":", "-"), MAC.upper().replace(":", ""), MAC.replace(":", "%3A")}

PATHS = ["/", "/index.htm", "/index.html", "/basic_-_my_devices.htm", "/basic_-_home.htm",
         "/cgi/cgi_basicMyDevice.js", "/cgi/cgi_myNetwork.js", "/cgi/cgi_owl.js", "/cgi/cgi_helpdesk.js",
         "/cgi/cgi_home.js", "/cgi/cgi_basic.js", "/cgi/cgi_status.js", "/cgi/cgi_toplogy_info.js",
         "/cgi/cgi_topology_info.js", "/cgi/cgi_device_list.js", "/cgi/cgi_devices.js",
         "/cgi/cgi_basicStatus.js", "/cgi/cgi_trafficStat.js", "/cgi/cgi_stats.js",
         "/nonAuth/wan_conn.xml", "/nonAuth/home_status.xml", "/nonAuth/device_list.xml"]


def get(path):
    req = urllib.request.Request(f"http://{HUB}{path}", headers={"User-Agent": "Mozilla/5.0", "Referer": f"http://{HUB}/"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, ""
    except Exception as err:
        return None, err.__class__.__name__


print(f"Hub {HUB}, looking for {MAC.upper()}\n")
for path in PATHS:
    code, body = get(path)
    if code != 200:
        print(f"  {path:<32} {code}")
        continue
    hit = next((f for f in mac_forms if f in body), None)
    print(f"  {path:<32} 200  {len(body)} bytes  {'<-- has the EE box' if hit else ''}")
    if path == "/":
        title = re.search(r"<title>(.*?)</title>", body, re.S | re.I)
        print(f"      page title: {title.group(1).strip() if title else '?'}")
        scripts = sorted(set(re.findall(r"""(?:src|href)=["']([^"']*cgi[^"']*)["']""", body)))
        if scripts:
            print("      it loads: " + ", ".join(scripts[:20]))
    if hit:
        i = body.find(hit)
        print("      around it: " + " ".join(body[max(0, i - 400):i + 600].split()))

print("\nPaste all of that to Claude.")
