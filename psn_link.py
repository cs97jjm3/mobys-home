"""
What's being played on the PS5, from your PlayStation account.

Uses PSNAWP, an unofficial library that talks to PlayStation Network the way
the PlayStation app does. It needs a sign-in code (the "npsso") from the
PlayStation website, which lasts about two months.

Go easy on it: this checks every couple of minutes, which is very light use.
The library's author warns that heavy use could get an account blocked.
"""

import asyncio
import json
import time
from pathlib import Path

CHECK_EVERY = 120   # seconds


def parse_presence(response):
    """Turn PlayStation's presence reply into something simple."""
    basic = (response or {}).get("basicPresence") or {}
    platform_info = basic.get("primaryPlatformInfo") or {}
    games = basic.get("gameTitleInfoList") or []
    game = games[0] if games else {}
    online = (platform_info.get("onlineStatus") == "online"
              or basic.get("availability") == "availableToPlay")
    return {
        "online": online,
        "platform": (platform_info.get("platform") or game.get("launchPlatform") or "").upper(),
        "game": (game.get("titleName") or "").replace("®", "").replace("™", "").strip() or None,
        "icon": game.get("conceptIconUrl") or game.get("npTitleIconUrl") or None,
    }


class PlayStation:
    def __init__(self, npsso, token_file, online_id=""):
        self.npsso = npsso.strip()
        self.token_file = Path(token_file)
        self.online_id = online_id.strip()
        self.psn = None
        self.account_id = None
        self.state = {}
        self.error = None
        self.days_left = None
        self.wait_until = 0       # after PlayStation refuses us, leave it alone for a while

    def _connect(self):
        from psnawp_api import PSNAWP
        saved = None
        if self.token_file.exists():
            try:
                saved = json.loads(self.token_file.read_text())
            except ValueError:
                saved = None
        # A saved sign-in is used first, so the code from the website isn't needed every restart
        same = bool(saved and saved.get("npsso") == self.npsso)
        if same:
            self.psn = PSNAWP(self.npsso, token_response=saved["token"])
        else:
            self.psn = PSNAWP(self.npsso)
        # The account number is remembered too: looking up the profile on every restart is what
        # gets PlayStation to start refusing us ("Access Denied")
        if same and saved.get("account_id") and saved.get("online_id", "") == self.online_id:
            self.account_id = saved["account_id"]
        else:
            user = (self.psn.user(online_id=self.online_id) if self.online_id else self.psn.me())
            self.account_id = user.account_id

    def _save_token(self):
        token = getattr(self.psn.authenticator, "token_response", None)
        if token:
            self.token_file.write_text(json.dumps({"npsso": self.npsso, "token": token,
                                                   "account_id": self.account_id, "online_id": self.online_id}))
            expires = token.get("refresh_token_expires_at")
            if expires:
                self.days_left = max(0, int((expires - time.time()) / 86400))

    def _read(self):
        if self.psn is None:
            self._connect()
        response = self.psn.user(account_id=self.account_id).get_presence()
        self._save_token()
        return parse_presence(response)

    async def refresh(self):
        if not self.npsso or time.time() < self.wait_until:
            return
        try:
            self.state = await asyncio.to_thread(self._read)
            self.error = None
        except Exception as err:
            name = err.__class__.__name__
            if "Access Denied" in str(err) or "403" in str(err)[:200]:
                self.error = "PlayStation is refusing requests for now. Trying again in 30 minutes."
                self.wait_until = time.time() + 30 * 60
                if self.account_id is None:      # it failed while looking us up: start afresh next time
                    self.psn = None
                print("PlayStation: refused for now (Access Denied), trying again in 30 minutes")
                return
            if "Auth" in name or "Unauthorized" in name or "InvalidToken" in name or "npsso" in str(err):
                self.error = "The PlayStation sign-in code has run out. Get a new one (see the README)."
                self.psn = None
            else:
                self.error = f"PlayStation didn't answer ({name})"
            print(f"PlayStation: {err}")

    def snapshot(self):
        if not self.npsso:
            return None
        warning = self.error
        if not warning and self.days_left is not None and self.days_left <= 7:
            warning = f"PlayStation sign-in code runs out in {self.days_left} days"
        return dict(self.state, warning=warning)
