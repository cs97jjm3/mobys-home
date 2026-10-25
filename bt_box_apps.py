"""
Asks the EE TV box which apps it knows about, and whether each is running
(DIAL, the way phone apps find the box). Only asks; changes nothing.

    py bt_box_apps.py 192.168.1.70
"""

import re
import sys
import urllib.error
import urllib.request

BOX = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.70"
BASE = f"http://{BOX}:56789/apps/"
NAMES = ["YouTube", "Netflix", "BBCiPlayer", "iPlayer", "BBC iPlayer", "ITVX", "ITV", "ITVHub", "AllFour",
         "Channel4", "4OD", "My5", "Demand5", "Channel5", "AmazonInstantVideo", "PrimeVideo", "Amazon",
         "DisneyPlus", "Disney+", "Disney", "NowTV", "NOW", "BritBox", "Spotify", "AppleTV", "ParamountPlus",
         "Paramount", "UKTVPlay", "U", "STV", "STVPlayer", "TNTSports", "BTSport", "Discovery", "Discovery+",
         "DAZN", "Pluto", "PlutoTV", "Rakuten", "TikTok", "Twitch", "Plex", "Freeview", "EETV", "EE", "BT",
         "YouView", "TV", "LiveTV", "Player", "HbbTV", "ChromeCast", "Chromecast", "Peacock", "Max", "Hayu"]


def ask(name, origin=None):
    url = BASE + urllib.request.quote(name)
    req = urllib.request.Request(url, headers={"Origin": origin} if origin else {})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            body = r.read().decode("utf-8", "replace")
            state = re.search(r"<state>(.*?)</state>", body)
            return r.status, state.group(1) if state else "?", body
    except urllib.error.HTTPError as err:
        return err.code, None, ""
    except Exception as err:
        return None, None, err.__class__.__name__


found = 0
for name in NAMES:
    code, state, body = ask(name)
    if code == 403:   # some apps only answer when asked "from" their own website
        for origin in ("https://www.youtube.com", "https://www.netflix.com", "package:com.google.android.youtube"):
            code, state, body = ask(name, origin)
            if code == 200:
                break
    if code == 200:
        found += 1
        print(f"  {name:<20} {state}")
        if True:
            print("    (full reply:)", " ".join(body.split())[:600])
    elif code not in (404,):
        print(f"  {name:<20} answered {code} {body}")
print(f"\nThe box knows {found} of these apps.")
print("Paste all of that to Claude.")
