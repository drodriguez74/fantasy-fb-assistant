"""Props are refetched only on Wednesdays and Sundays (free-tier credits); other days serve the last fetch."""
import asyncio
from datetime import datetime, timezone

from app.services import odds_service as osvc


def test_refresh_days_are_wednesday_and_sunday_eastern():
    assert osvc.prop_refresh_day(datetime(2026, 10, 7, 16, tzinfo=timezone.utc))      # Wed
    assert osvc.prop_refresh_day(datetime(2026, 10, 11, 16, tzinfo=timezone.utc))     # Sun
    assert not osvc.prop_refresh_day(datetime(2026, 10, 8, 16, tzinfo=timezone.utc))  # Thu
    # Thursday 02:00 UTC is still Wednesday night in New York.
    assert osvc.prop_refresh_day(datetime(2026, 10, 8, 2, tzinfo=timezone.utc))


def test_off_day_serves_stale_props_without_fetching(monkeypatch):
    calls = []

    async def fake_cache_get(key, ttl):
        return None if ttl != float("inf") else {"stale": True}

    async def fake_get(*a, **k):
        calls.append(a)
        return {"fresh": True}
    monkeypatch.setattr(osvc.settings, "ODDS_API_KEY", "k", raising=False)
    monkeypatch.setattr(osvc, "_cache_get", fake_cache_get)
    monkeypatch.setattr(osvc, "_get", fake_get)
    monkeypatch.setattr(osvc, "prop_refresh_day", lambda now=None: False)
    assert asyncio.run(osvc.get_event_props("e1")) == {"stale": True} and not calls


def test_reserve_falls_back_to_last_fetch(monkeypatch):
    async def fake_cache_get(key, ttl):
        return None if ttl != float("inf") else {"stale": True}

    async def credits():
        return osvc.CREDIT_RESERVE  # at the reserve: no spending

    async def fake_get(*a, **k):
        raise AssertionError("must not fetch below the reserve")
    monkeypatch.setattr(osvc.settings, "ODDS_API_KEY", "k", raising=False)
    monkeypatch.setattr(osvc, "_cache_get", fake_cache_get)
    monkeypatch.setattr(osvc, "credits_remaining_async", credits)
    monkeypatch.setattr(osvc, "_get", fake_get)
    monkeypatch.setattr(osvc, "prop_refresh_day", lambda now=None: True)
    assert asyncio.run(osvc.get_event_props("e1")) == {"stale": True}
