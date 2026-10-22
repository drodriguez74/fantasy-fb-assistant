"""Each game's props are fetched once in the 36h before kickoff and once more
in the last 2h (the closing line); college lines refetch only Thursday to
Saturday."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services import odds_service as osvc

KICKOFF = "2026-10-18T17:00:00Z"
K = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)


@pytest.fixture
def api(monkeypatch):
    """A fake cache holding one entry (age in seconds, data) and a counting _get."""
    state = {"entry": None, "calls": 0, "db": None}

    async def entry(key):
        return state["entry"]

    async def credits():
        return 400

    async def fake_get(*a, **k):
        state["calls"] += 1
        return {"fresh": True}

    async def put(key, data):
        state["entry"] = (0.0, data)
    monkeypatch.setattr(osvc.settings, "ODDS_API_KEY", "k", raising=False)
    monkeypatch.setattr(osvc, "_cache_entry", entry)
    monkeypatch.setattr(osvc, "_cache_put", put)
    monkeypatch.setattr(osvc, "credits_remaining_async", credits)
    monkeypatch.setattr(osvc, "_get", fake_get)
    monkeypatch.setattr(osvc, "_db_read", lambda key: state["db"])
    return state


def props(now):
    return asyncio.run(osvc.get_event_props("e1", KICKOFF, now=now))


def test_too_early_never_spends(api):
    assert props(K - timedelta(hours=37)) is None and api["calls"] == 0
    api["entry"] = (3600.0, {"old": True})
    assert props(K - timedelta(hours=37)) == {"old": True} and api["calls"] == 0


def test_fetched_once_inside_the_window(api):
    assert props(K - timedelta(hours=30)) == {"fresh": True} and api["calls"] == 1
    api["entry"] = (20 * 3600.0, {"fresh": True})  # fetched 20h ago, at kickoff - 30h
    assert props(K - timedelta(hours=10)) == {"fresh": True} and api["calls"] == 1


def test_fetch_from_before_the_window_is_refreshed_once(api):
    api["entry"] = (3 * 86400.0, {"old": True})  # fetched on Wednesday for a Sunday game
    assert props(K - timedelta(hours=12)) == {"fresh": True} and api["calls"] == 1


def test_one_more_fetch_in_the_closing_window(api):
    api["entry"] = (29 * 3600.0, {"early": True})  # fetched at kickoff - 30h
    now = K - timedelta(hours=1)
    assert props(now) == {"fresh": True} and api["calls"] == 1
    assert props(now + timedelta(minutes=30)) == {"fresh": True} and api["calls"] == 1  # only once


def test_closing_fetch_taken_by_another_process_is_read_not_repaid(api):
    now = K - timedelta(hours=1)
    api["entry"] = (29 * 3600.0, {"early": True})  # this process's memory: the early fetch
    api["db"] = (now - timedelta(minutes=20), {"close": True})  # the Mac's build took the close
    assert props(now) == {"close": True} and api["calls"] == 0


def test_no_closing_fetch_after_kickoff_or_when_first_fetch_was_late(api):
    api["entry"] = (29 * 3600.0, {"early": True})
    assert props(K + timedelta(minutes=5)) == {"early": True} and api["calls"] == 0
    api["entry"] = (600.0, {"late": True})  # first fetched 10 minutes ago, inside the closing window
    assert props(K - timedelta(hours=1)) == {"late": True} and api["calls"] == 0


def test_reserve_falls_back_to_last_fetch(api, monkeypatch):
    async def credits():
        return osvc.CREDIT_RESERVE  # at the reserve: no spending
    monkeypatch.setattr(osvc, "credits_remaining_async", credits)
    api["entry"] = (3 * 86400.0, {"old": True})
    assert props(K - timedelta(hours=12)) == {"old": True} and api["calls"] == 0


def test_college_line_days_are_thursday_to_saturday_eastern():
    assert osvc.cfb_line_day(datetime(2026, 10, 15, 16, tzinfo=timezone.utc))      # Thu
    assert osvc.cfb_line_day(datetime(2026, 10, 17, 16, tzinfo=timezone.utc))      # Sat
    assert not osvc.cfb_line_day(datetime(2026, 10, 14, 16, tzinfo=timezone.utc))  # Wed
    # Sunday 02:00 UTC is still Saturday night in New York.
    assert osvc.cfb_line_day(datetime(2026, 10, 18, 2, tzinfo=timezone.utc))
