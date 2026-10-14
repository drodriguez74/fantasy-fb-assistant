"""Each game's props are fetched once, in the 36h before kickoff (free-tier
credits); college lines refetch only Thursday to Saturday."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services import odds_service as osvc

KICKOFF = "2026-10-18T17:00:00Z"
K = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)


@pytest.fixture
def api(monkeypatch):
    """A fake cache holding one entry (age in seconds, data) and a counting _get."""
    state = {"entry": None, "calls": 0}

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
