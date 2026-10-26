import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import ring_link as rl


def test_history_item():
    when = datetime(2026, 10, 26, 17, 48, tzinfo=timezone.utc)
    assert rl.history_item({"kind": "ding", "created_at": when}) == {"ts": when.timestamp(), "kind": "press"}
    assert rl.history_item({"kind": "motion", "created_at": "2026-10-26T17:48:34Z"})["kind"] == "motion"
    assert rl.history_item({"kind": "on_demand", "created_at": when}) is None   # live view, not a visitor


def test_today_only():
    now = time.time()
    items = [{"ts": now - 60, "kind": "press"}, {"ts": now - 3 * 86400, "kind": "motion"}]
    assert rl.today_only(items, now) == items[:1]


def test_live_press(tmp_path):
    token = tmp_path / "ring_token.json"
    token.write_text("{}")
    door = rl.RingDoor(token, tmp_path / "listen.json")
    pressed = []

    async def on_press():
        pressed.append(True)
    door.on_press = on_press

    async def go():
        door._heard(NS(kind="motion"))
        door._heard(NS(kind="ding"))
        await asyncio.sleep(0)
    asyncio.run(go())
    snap = door.snapshot()
    assert snap["live"]["kind"] == "press" and snap["presses"] == 1 and snap["motions"] == 1
    assert snap["last_press"] and pressed == [True]


def test_off_without_sign_in(tmp_path):
    assert rl.RingDoor(tmp_path / "none.json", tmp_path / "l.json").snapshot() is None


def test_live_view_relay(tmp_path):
    from ring_doorbell.webrtcstream import RingWebRtcMessage as Msg
    token = tmp_path / "ring_token.json"
    token.write_text("{}")
    door = rl.RingDoor(token, tmp_path / "listen.json")
    sent = []

    class Bell:
        async def generate_async_webrtc_stream(self, offer, sid, cb, keep_alive_timeout=None):
            cb(Msg(answer="v=0 answer"))
            cb(Msg(candidate="candidate:1 1 udp 1 1.2.3.4 5 typ host", sdp_m_line_index=0))
        async def on_webrtc_candidate(self, sid, c, i): sent.append(c)
        async def keep_alive_webrtc_stream(self, sid): pass
        async def close_webrtc_stream(self, sid): sent.append("closed")
        def get_ice_servers(self): return ["stun:stun.l.google.com:19302"]
    door.bell = Bell()

    async def go():
        r = await door.view_start("v=0 offer")
        assert r["answer"] == "v=0 answer" and r["ice_servers"][0]["urls"].startswith("stun:")
        m = door.view_messages(r["id"])
        assert m["candidates"][0]["candidate"].startswith("candidate:")
        assert door.view_messages(r["id"])["candidates"] == []      # each candidate passed on once
        await door.view_candidate(r["id"], "candidate:browser", 0)
        assert await door.view_keep_alive(r["id"])
        await door.view_stop(r["id"])
        assert door.view_messages(r["id"])["closed"] and sent == ["candidate:browser", "closed"]
    asyncio.run(go())


def test_live_view_error(tmp_path):
    from ring_doorbell.webrtcstream import RingWebRtcMessage as Msg
    token = tmp_path / "t.json"; token.write_text("{}")
    door = rl.RingDoor(token, tmp_path / "l.json")

    class Bell:
        async def generate_async_webrtc_stream(self, offer, sid, cb, keep_alive_timeout=None):
            cb(Msg(error_code="busy", error_message="Device is busy"))
        async def close_webrtc_stream(self, sid): pass
    door.bell = Bell()
    try:
        asyncio.run(door.view_start("v=0"))
        assert False
    except RuntimeError as err:
        assert "busy" in str(err)
