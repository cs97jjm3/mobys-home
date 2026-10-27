"""Tests for reading PlayStation presence. No account or internet needed."""

import psn_link as pl


def test_reads_the_game_being_played():
    reply = {"basicPresence": {
        "availability": "availableToPlay",
        "primaryPlatformInfo": {"onlineStatus": "online", "platform": "ps5"},
        "gameTitleInfoList": [{"npTitleId": "PPSA01234_00", "titleName": "F1® 25",
                               "format": "PS5", "launchPlatform": "PS5",
                               "conceptIconUrl": "https://image.example/f1.png"}]}}
    assert pl.parse_presence(reply) == {"online": True, "platform": "PS5", "game": "F1 25",
                                        "icon": "https://image.example/f1.png"}


def test_online_but_not_in_a_game():
    reply = {"basicPresence": {"availability": "availableToPlay",
                               "primaryPlatformInfo": {"onlineStatus": "online", "platform": "PS5"}}}
    result = pl.parse_presence(reply)
    assert result["online"] and result["game"] is None


def test_offline():
    reply = {"basicPresence": {"availability": "unavailable",
                               "primaryPlatformInfo": {"onlineStatus": "offline", "platform": "PS5"}}}
    assert pl.parse_presence(reply)["online"] is False


def test_no_code_means_nothing_shown():
    assert pl.PlayStation("", "x.json").snapshot() is None


def test_warns_before_the_code_runs_out():
    psn = pl.PlayStation("abc", "x.json")
    psn.state, psn.days_left = {"online": True, "game": "F1 25"}, 5
    assert "5 days" in psn.snapshot()["warning"]


def test_access_denied_backs_off(tmp_path):
    import asyncio, time
    import psn_link as pl
    ps = pl.PlayStation("code", tmp_path / "t.json", "Someone")
    calls = []

    def refused():
        calls.append(1)
        raise RuntimeError("<HTML><TITLE>Access Denied</TITLE> You don't have permission")
    ps._read = refused
    asyncio.run(ps.refresh())
    asyncio.run(ps.refresh())                      # within 30 minutes: doesn't ask again
    assert len(calls) == 1 and "refusing" in ps.snapshot()["warning"]
    assert ps.wait_until > time.time() + 25 * 60


def test_account_remembered(tmp_path):
    import json
    import psn_link as pl
    token = tmp_path / "t.json"
    ps = pl.PlayStation("code", token, "Someone")
    ps.account_id = "123"

    class Auth:
        token_response = {"access_token": "x", "refresh_token_expires_at": 0}
    ps.psn = type("P", (), {"authenticator": Auth()})()
    ps._save_token()
    saved = json.loads(token.read_text())
    assert saved["account_id"] == "123" and saved["online_id"] == "Someone"
