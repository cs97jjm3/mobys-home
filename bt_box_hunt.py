"""
A bigger hunt on the EE TV box. Only reads: no power, standby, key or restart
addresses are tried, so it can't change anything on the box.

  Several hundred app names on the app port (56789), asked slowly, one at a time,
  because the box started refusing when asked lots at once.

Put something on the box first (live TV is fine), then:

    py bt_box_hunt.py 192.168.1.70

Takes a minute or two. Paste everything it prints to Claude.
"""

import asyncio
import sys

BOX = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.70"

# ---------- app names ----------
BASES = ["Netflix", "YouTube", "BBC iPlayer", "BBCiPlayer", "iPlayer", "BBC", "iplayer", "bbc.iplayer", "uk.co.bbc.iplayer",
         "ITVX", "ITV", "ITVHub", "itvx", "itv", "com.itv", "ITVPlayer",
         "Channel4", "Channel 4", "All4", "AllFour", "4OD", "C4", "Channel4Player", "com.channel4",
         "My5", "Channel5", "Demand5", "5", "Five", "C5",
         "Prime Video", "PrimeVideo", "AmazonInstantVideo", "AmazonVideo", "Amazon", "AIV", "amazon.aiv",
         "com.amazon.amazonvideo", "Prime",
         "Disney+", "DisneyPlus", "Disney", "com.disney.disneyplus", "disneyplus",
         "NOW", "NowTV", "NOWTV", "Now TV", "SkyNow", "Sky",
         "BritBox", "Britbox", "UKTV", "UKTVPlay", "U", "UPlay", "STV", "STVPlayer", "S4C", "Clic",
         "Spotify", "spotify", "com.spotify", "Deezer", "Tidal", "AmazonMusic", "AppleMusic",
         "AppleTV", "Apple TV", "AppleTVPlus", "TV+",
         "Paramount+", "ParamountPlus", "Paramount", "Pluto", "PlutoTV", "Pluto TV",
         "TNTSports", "TNT Sports", "BTSport", "BT Sport", "Discovery+", "DiscoveryPlus", "Discovery",
         "DAZN", "Dazn", "Eurosport", "F1TV", "F1 TV", "SkySports",
         "EE", "EETV", "EE TV", "BT", "BTTV", "BT TV", "YouView", "Youview", "TV", "LiveTV", "Live",
         "Freeview", "FreeviewPlay", "Freely", "Player", "Watch", "Home", "Launcher", "Guide", "EPG",
         "HbbTV", "hbbtv", "MHEG", "Recordings", "PVR",
         "Plex", "Emby", "Jellyfin", "Kodi", "VLC", "Rakuten", "RakutenTV", "Chili", "Curzon", "MUBI", "Mubi",
         "TikTok", "Twitch", "Vimeo", "Dailymotion", "YouTubeKids", "YouTube Kids", "YouTubeTV", "YouTubeMusic",
         "Peacock", "Max", "HBOMax", "Hayu", "Hulu", "Crunchyroll", "Tubi", "Samsung TV Plus", "Amazon Freevee",
         "Freevee", "GBNews", "Sky News", "SkyNews", "BBCNews", "Al Jazeera",
         "ChromeCast", "Chromecast", "Cast", "Airplay", "AirPlay", "DLNA", "Miracast", "Screen Mirroring"]


def variants(name):
    out = {name, name.replace(" ", ""), name.replace(" ", "_"), name.replace(" ", "-"),
           name.lower(), name.lower().replace(" ", ""), name.upper().replace(" ", "")}
    return [v for v in out if v]


APP_NAMES = list(dict.fromkeys(v for b in BASES for v in variants(b)))

# ---------- addresses to read ----------
WORDS = ["status", "state", "info", "information", "device", "deviceinfo", "device-info", "system", "systeminfo",
         "version", "versions", "about", "capabilities", "features", "config", "configuration", "settings",
         "tv", "live", "player", "playback", "nowplaying", "now-playing", "now_playing", "current", "currentservice",
         "current-service", "service", "services", "channel", "channels", "channellist", "lineup", "programme",
         "programmes", "program", "programs", "epg", "guide", "schedule", "events", "event", "content",
         "apps", "applications", "app", "launcher", "home", "menu", "ui", "screen", "display", "volume", "audio",
         "video", "subtitles", "recordings", "recording", "pvr", "dvr", "library", "bookings", "storage", "disk",
         "network", "wifi", "bluetooth", "hdmi", "cec", "pair", "pairing", "paired", "devices", "clients",
         "companion", "secondscreen", "second-screen", "mobile", "remote", "rc", "rcu",
         "discovery", "dial", "upnp", "ssdp", "cast", "airplay", "auth", "token", "session", "sessions",
         "register", "registration", "user", "users", "account", "profile", "profiles",
         "health", "healthcheck", "ping", "hello", "alive", "ready", "metrics", "stats", "diagnostics",
         "debug", "log", "logs", "events/stream", "notifications", "subscribe", "websocket", "ws", "socket",
         "graphql", "api", "openapi.json", "swagger.json", "swagger", "docs", "help", "index.json"]
PREFIXES = ["", "api/", "api/v1/", "api/v2/", "v1/", "v2/", "rest/", "tv/", "box/", "stb/", "local/"]
PATHS = list(dict.fromkeys(["/"] + [f"/{p}{w}" for p in PREFIXES for w in WORDS]))
PORTS = [8888, 56789, 56790]


async def get(port, path, origin=None):
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(BOX, port), 3)
        head = f"GET {path} HTTP/1.1\r\nHost: {BOX}:{port}\r\nUser-Agent: Moby\r\nConnection: close\r\n"
        if origin:
            head += f"Origin: {origin}\r\n"
        writer.write((head + "\r\n").encode())
        await writer.drain()
        data = await asyncio.wait_for(reader.read(4000), 4)
        writer.close()
        text = data.decode("utf-8", "replace")
        first, _, rest = text.partition("\r\n")
        _, _, body = rest.partition("\r\n\r\n")
        parts = first.split(" ")
        return (int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0), body
    except Exception as err:
        return None, err.__class__.__name__


async def main():
    print(f"Trying {len(APP_NAMES)} app names on port 56789, one at a time (about 2 minutes)")
    found, errors = 0, 0
    for name in APP_NAMES:
        code, body = await get(56789, "/apps/" + name.replace(" ", "%20"))
        if code is None:
            await asyncio.sleep(1)
            code, body = await get(56789, "/apps/" + name.replace(" ", "%20"))
        if code == 403:
            code, body = await get(56789, "/apps/" + name.replace(" ", "%20"), "https://www.youtube.com")
        if code is None:
            errors += 1
        elif code != 404:
            found += 1
            state = body.split("<state>")[1].split("</state>")[0] if "<state>" in body else ""
            print(f"  {name:<28} {code} {state}")
        await asyncio.sleep(0.15)
    print(f"\n{found} answered, {errors} got no reply at all")
    print("(Netflix and YouTube should be in the list: that shows the check is working.)")
    print("Paste all of that to Claude.")

asyncio.run(main())
