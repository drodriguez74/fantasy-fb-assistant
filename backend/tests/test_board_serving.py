"""GET /betting/board serving: saved board instantly, background rebuild when stale, one build for concurrent callers."""
import asyncio
from datetime import datetime, timedelta, timezone

from app.services import betting_service as bs


def _reset(monkeypatch):
    monkeypatch.setattr(bs, "_board_cache", {})
    monkeypatch.setattr(bs, "_saved", {})
    monkeypatch.setattr(bs, "_refreshing", set())
    monkeypatch.setattr(bs, "_build_locks", {})


def test_saved_board_is_served_and_refreshed_when_stale(monkeypatch):
    _reset(monkeypatch)
    builds = []

    async def fake_build(force=False):
        builds.append(force)
        return {"available": True, "week": 5, "fresh": True}
    monkeypatch.setattr(bs, "build_board", fake_build)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(bs.odds_service, "_db_read", lambda key: (old, {"available": True, "week": 5}))

    async def run():
        out = await bs.serve_board("nfl")
        await asyncio.sleep(0)  # let the background rebuild start
        return out
    out = asyncio.run(run())
    assert out["refreshing"] and out["saved_age_minutes"] == 120 and "fresh" not in out
    assert builds == [True]  # one background rebuild


def test_concurrent_builds_share_one(monkeypatch):
    _reset(monkeypatch)
    calls = []

    async def slow_build():
        calls.append(1)
        await asyncio.sleep(0.05)
        board = {"available": True, "week": 5}
        bs._board_cache["board"] = (bs.time.monotonic(), board)
        return board
    monkeypatch.setattr(bs, "_build_board_now", slow_build)

    async def no_store(sport, board):
        return None
    monkeypatch.setattr(bs, "_store_board", no_store)

    async def run():
        return await asyncio.gather(bs.build_board(), bs.build_board(), bs.build_board())
    a, b, c = asyncio.run(run())
    assert len(calls) == 1 and a is b is c
