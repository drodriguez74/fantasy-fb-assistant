"""
Tests for Yahoo access-token renewal (app.services.yahoo_tokens).

Yahoo tokens last ~1hr; before this, nothing ever called
yahoo_service.refresh_access_token, so every Yahoo feature failed an hour
after connecting. Covers: a fresh token is used as-is, an expired one is
renewed and saved (to every league sharing that token pair, and only the
same user's), a failed renewal returns None without touching the DB,
concurrent callers share one renewal, and a detached row still gets saved.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.user_league import UserLeague, PlatformType
from app.services import yahoo_tokens
from app.services.yahoo_service import yahoo_service

engine = create_engine("sqlite:///./test_yahoo_tokens.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Detached-row renewals open their own session -- keep that on the test DB.
    monkeypatch.setattr(yahoo_tokens, "SessionLocal", TestingSessionLocal)
    session = TestingSessionLocal()
    yield session
    session.close()


def _league(db, *, user_id=1, league_id="1", access="old-access", refresh="old-refresh", expires_in_minutes=-5):
    row = UserLeague(
        user_id=user_id,
        platform=PlatformType.YAHOO,
        league_id=league_id,
        league_key=f"461.l.{league_id}",
        yahoo_access_token=access,
        yahoo_refresh_token=refresh,
        yahoo_token_expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
    )
    db.add(row)
    db.commit()
    return row


def _fake_refresh(monkeypatch, result):
    calls = []

    async def fake(refresh_token):
        calls.append(refresh_token)
        await asyncio.sleep(0)  # yield so concurrent callers really overlap
        return result

    monkeypatch.setattr(yahoo_service, "refresh_access_token", fake)
    return calls


def test_fresh_token_is_used_without_refreshing(db, monkeypatch):
    league = _league(db, access="good-access", expires_in_minutes=30)
    calls = _fake_refresh(monkeypatch, {"access_token": "should-not-be-used"})

    assert asyncio.run(yahoo_tokens.get_valid_yahoo_token(league)) == "good-access"
    assert calls == []


def test_token_inside_refresh_margin_is_renewed(db, monkeypatch):
    league = _league(db, expires_in_minutes=1)
    calls = _fake_refresh(monkeypatch, {"access_token": "new-access", "refresh_token": "old-refresh", "expires_in": 3600})

    assert asyncio.run(yahoo_tokens.get_valid_yahoo_token(league)) == "new-access"
    assert calls == ["old-refresh"]


def test_expired_token_is_renewed_and_saved_to_every_league_sharing_it(db, monkeypatch):
    mine = _league(db, league_id="1")
    sibling = _league(db, league_id="2")
    someone_else = _league(db, user_id=2, league_id="3")
    _fake_refresh(monkeypatch, {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600})

    assert asyncio.run(yahoo_tokens.get_valid_yahoo_token(mine)) == "new-access"

    check = TestingSessionLocal()
    try:
        rows = {r.league_id: r for r in check.query(UserLeague).all()}
        for lid in ("1", "2"):
            assert rows[lid].yahoo_access_token == "new-access"
            assert rows[lid].yahoo_refresh_token == "new-refresh"
            expires = rows[lid].yahoo_token_expires_at.replace(tzinfo=timezone.utc)
            assert expires > datetime.now(timezone.utc) + timedelta(minutes=50)
        assert rows["3"].yahoo_access_token == "old-access"
        assert rows["3"].yahoo_refresh_token == "old-refresh"
    finally:
        check.close()


def test_failed_renewal_returns_none_and_leaves_db_alone(db, monkeypatch):
    league = _league(db)
    _fake_refresh(monkeypatch, {"error": "Yahoo token refresh failed with status 400"})

    assert asyncio.run(yahoo_tokens.get_valid_yahoo_token(league)) is None

    check = TestingSessionLocal()
    try:
        row = check.query(UserLeague).one()
        assert row.yahoo_access_token == "old-access"
        assert row.yahoo_refresh_token == "old-refresh"
    finally:
        check.close()


def test_expired_token_with_no_refresh_token_returns_none(db, monkeypatch):
    league = _league(db, refresh=None)
    calls = _fake_refresh(monkeypatch, {"access_token": "should-not-be-used"})

    assert asyncio.run(yahoo_tokens.get_valid_yahoo_token(league)) is None
    assert calls == []


def test_concurrent_callers_share_one_renewal(db, monkeypatch):
    league = _league(db)
    calls = _fake_refresh(monkeypatch, {"access_token": "new-access", "refresh_token": "old-refresh", "expires_in": 3600})

    async def many():
        return await asyncio.gather(*(yahoo_tokens.get_valid_yahoo_token(league) for _ in range(5)))

    assert asyncio.run(many()) == ["new-access"] * 5
    assert len(calls) == 1


def test_detached_row_is_renewed_and_saved(db, monkeypatch):
    league = _league(db)
    db.refresh(league)  # load attributes before detaching (commit expired them)
    db.expunge(league)
    _fake_refresh(monkeypatch, {"access_token": "new-access", "refresh_token": "old-refresh", "expires_in": 3600})

    assert asyncio.run(yahoo_tokens.get_valid_yahoo_token(league)) == "new-access"
    assert league.yahoo_access_token == "new-access"

    check = TestingSessionLocal()
    try:
        assert check.query(UserLeague).one().yahoo_access_token == "new-access"
    finally:
        check.close()
