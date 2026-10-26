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
