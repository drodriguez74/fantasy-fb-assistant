"""
Tests for the real Yahoo Fantasy connect flow.

Covers:
  - yahoo_service no longer holds any shared/mutable per-user token state
    (the P0 multi-user-leak bug this phase fixes), proven by running two
    different tokens through the same singleton instance concurrently.
  - POST /leagues/yahoo/connect requires auth, does a real
    authenticate() -> get_user_leagues() -> persist flow (with Yahoo's
    network calls mocked out), and scopes everything to current_user --
    two different users connecting Yahoo never see each other's leagues
    or credentials.
  - Yahoo OAuth errors propagate as a 400 instead of a fake success.
  - Expired/missing Yahoo tokens fail with a clear "reconnect" error
    instead of a silent/generic failure (league_management_service's
    _get_yahoo_token helper).
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.api.deps import get_db
from app.models.user_league import UserLeague, PlatformType
from app.services.yahoo_service import yahoo_service
from app.services.league_management_service import LeagueManagementService

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_yahoo_connect.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def override_db_dependency():
    # Scoped per-test, same reasoning as test_auth.py: a bare module-level
    # override never gets torn down and leaks into other test files.
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def register_and_login(client, email, username):
    user_data = {
        "email": email,
        "username": username,
        "password": "TestPassword123",
        "full_name": "Test User",
    }
    resp = client.post("/api/v1/auth/register", json=user_data)
    assert resp.status_code == 200, resp.text
    login_resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "TestPassword123"}
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def yahoo_leagues_payload(league_id: str, league_name: str, num_teams: int = 10):
    """Shape yahoo_service.get_user_leagues() is expected to return -- this
    mirrors what get_user_leagues() itself produces after parsing Yahoo's
    raw fantasy_content JSON, since we mock at that boundary rather than
    re-implementing Yahoo's XML/JSON quirks in the test.
    """
    return [
        {
            "league_key": f"423.l.{league_id}",
            "league_id": league_id,
            "name": league_name,
            "num_teams": num_teams,
            "scoring_type": "headpoint",
            "league_type": "private",
        }
    ]


# ---------------------------------------------------------------------------
# 1. Service-layer proof: the singleton no longer leaks tokens across users
# ---------------------------------------------------------------------------

def test_yahoo_service_has_no_shared_token_state():
    """Structural proof of the fix: the module-level yahoo_service singleton
    must not carry any per-user token as instance state. Before this fix,
    self.access_token was set by authenticate() and read by every other
    method -- meaning one user's Yahoo session could silently leak into or
    get clobbered by another user's concurrent request.
    """
    assert not hasattr(yahoo_service, "access_token")


def test_yahoo_service_multi_user_token_isolation(monkeypatch):
    """Run two different users' tokens through the same yahoo_service
    instance concurrently and confirm each gets back only their own data --
    the concrete proof that per-user credentials are threaded as explicit
    parameters, not shared mutable state.
    """

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.headers = {"content-type": "application/json"}
            self.status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    call_log = []

    async def fake_get(self, url, headers=None, params=None):
        # Simulate network latency/interleaving so a shared-state bug would
        # actually have a chance to manifest under concurrency.
        await asyncio.sleep(0.01)
        token = (headers or {}).get("Authorization", "")
        call_log.append(token)

        if token == "Bearer token_alice":
            league_name, season = "Alice's League", "2024"
        elif token == "Bearer token_bob":
            league_name, season = "Bob's League", "2024"
        else:
            raise AssertionError(f"Unexpected token in request: {token}")

        payload = {
            "fantasy_content": {
                "users": {
                    "0": {
                        "user": {
                            "games": {
                                "0": {
                                    "game": {
                                        "code": "nfl",
                                        "season": season,
                                        "leagues": {
                                            "0": {
                                                "league": {
                                                    "league_key": "423.l.1",
                                                    "league_id": "1",
                                                    "name": league_name,
                                                    "num_teams": 10,
                                                    "scoring_type": "headpoint",
                                                    "league_type": "private",
                                                }
                                            }
                                        },
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        return FakeResponse(payload)

    # Patch at the httpx.AsyncClient class level (not on a specific client
    # instance) -- yahoo_service.client is a lazily-created,
    # event-loop-scoped instance, so patching one instance's bound method
    # wouldn't reliably survive into the fresh instance asyncio.run()
    # creates below.
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    async def run_both():
        return await asyncio.gather(
            yahoo_service.get_user_leagues("token_alice", season=2024),
            yahoo_service.get_user_leagues("token_bob", season=2024),
        )

    alice_leagues, bob_leagues = asyncio.run(run_both())

    assert len(call_log) == 2
    assert alice_leagues[0]["name"] == "Alice's League"
    assert bob_leagues[0]["name"] == "Bob's League"
    # The cross-contamination this bug used to cause: one user's result
    # bleeding into the other's.
    assert alice_leagues[0]["name"] != bob_leagues[0]["name"]


# ---------------------------------------------------------------------------
# 2. Endpoint-level: real auth requirement, real persistence, per-user scope
# ---------------------------------------------------------------------------

def test_yahoo_connect_requires_authentication(client, setup_database):
    """The old handler ignored its request body and current_user entirely.
    The real one must require a logged-in user like /espn/connect does.
    """
    response = client.post(
        "/api/v1/leagues/yahoo/connect",
        json={"authorization_code": "some-code", "redirect_uri": "http://localhost:3001/yahoo/callback"},
    )
    assert response.status_code in (401, 403)


def test_yahoo_connect_propagates_oauth_error(client, setup_database, monkeypatch):
    headers = register_and_login(client, "erroruser@example.com", "erroruser")

    monkeypatch.setattr(yahoo_service, "credentials_configured", True)
    monkeypatch.setattr(
        yahoo_service,
        "authenticate",
        AsyncMock(return_value={"error": "Yahoo OAuth failed with status 400: invalid_grant"}),
    )

    response = client.post(
        "/api/v1/leagues/yahoo/connect",
        json={"authorization_code": "bad-code", "redirect_uri": "http://localhost:3001/yahoo/callback"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "invalid_grant" in response.json()["detail"]


def test_yahoo_connect_persists_real_credentials_scoped_per_user(client, setup_database, monkeypatch):
    """End-to-end: two different users each connect a Yahoo account (each
    with a distinct authorization_code, as real OAuth would produce distinct
    tokens per user). Assert each user's UserLeague row carries their own
    real access/refresh token + expiry, and that neither user's leagues or
    credentials are visible to the other -- the same isolation guarantee
    the ESPN P0 fix (8b97ec2) established for ESPN.
    """
    alice_headers = register_and_login(client, "alice@example.com", "alice")
    bob_headers = register_and_login(client, "bob@example.com", "bob")

    monkeypatch.setattr(yahoo_service, "credentials_configured", True)

    async def fake_authenticate(authorization_code, redirect_uri):
        if authorization_code == "alice-code":
            return {"access_token": "alice-access-tok", "refresh_token": "alice-refresh-tok", "expires_in": 3600}
        elif authorization_code == "bob-code":
            return {"access_token": "bob-access-tok", "refresh_token": "bob-refresh-tok", "expires_in": 3600}
        raise AssertionError("unexpected authorization_code")

    async def fake_get_user_leagues(access_token, season=2024):
        if access_token == "alice-access-tok":
            return yahoo_leagues_payload("111", "Alice's League")
        elif access_token == "bob-access-tok":
            return yahoo_leagues_payload("222", "Bob's League")
        raise AssertionError("unexpected access_token")

    monkeypatch.setattr(yahoo_service, "authenticate", fake_authenticate)
    monkeypatch.setattr(yahoo_service, "get_user_leagues", fake_get_user_leagues)

    alice_resp = client.post(
        "/api/v1/leagues/yahoo/connect",
        json={"authorization_code": "alice-code", "redirect_uri": "http://localhost:3001/yahoo/callback"},
        headers=alice_headers,
    )
    assert alice_resp.status_code == 200, alice_resp.text
    alice_body = alice_resp.json()
    assert alice_body["success"] is True
    assert alice_body["leagues_connected"] == 1
    assert alice_body["leagues"][0]["league_name"] == "Alice's League"

    bob_resp = client.post(
        "/api/v1/leagues/yahoo/connect",
        json={"authorization_code": "bob-code", "redirect_uri": "http://localhost:3001/yahoo/callback"},
        headers=bob_headers,
    )
    assert bob_resp.status_code == 200, bob_resp.text
    bob_body = bob_resp.json()
    assert bob_body["leagues"][0]["league_name"] == "Bob's League"

    # Each user's /leagues/ listing shows only their own league.
    alice_list = client.get("/api/v1/leagues/", headers=alice_headers)
    assert alice_list.status_code == 200
    alice_names = [l["league_name"] for l in alice_list.json()]
    assert alice_names == ["Alice's League"]

    bob_list = client.get("/api/v1/leagues/", headers=bob_headers)
    assert bob_list.status_code == 200
    bob_names = [l["league_name"] for l in bob_list.json()]
    assert bob_names == ["Bob's League"]

    # Verify the actual persisted credentials in the DB are distinct and
    # correctly scoped -- this is the real per-user persistence the task
    # required (access_token, refresh_token, expires_at).
    db = TestingSessionLocal()
    try:
        alice_row = (
            db.query(UserLeague)
            .filter(UserLeague.platform == PlatformType.YAHOO, UserLeague.league_id == "111")
            .first()
        )
        bob_row = (
            db.query(UserLeague)
            .filter(UserLeague.platform == PlatformType.YAHOO, UserLeague.league_id == "222")
            .first()
        )
        assert alice_row is not None and bob_row is not None
        assert alice_row.user_id != bob_row.user_id

        assert alice_row.yahoo_access_token == "alice-access-tok"
        assert alice_row.yahoo_refresh_token == "alice-refresh-tok"
        assert alice_row.yahoo_token_expires_at is not None
        assert alice_row.yahoo_token_expires_at > datetime.utcnow()

        assert bob_row.yahoo_access_token == "bob-access-tok"
        assert bob_row.yahoo_refresh_token == "bob-refresh-tok"

        # No cross-contamination between the two rows.
        assert alice_row.yahoo_access_token != bob_row.yahoo_access_token
    finally:
        db.close()


def test_yahoo_connect_reconnect_refreshes_stored_credentials(client, setup_database, monkeypatch):
    """Yahoo tokens expire in ~1hr (unlike ESPN's long-lived cookies), so
    reconnecting the same league must actually update the stored token
    rather than silently keep the stale one.
    """
    headers = register_and_login(client, "carol@example.com", "carol")
    monkeypatch.setattr(yahoo_service, "credentials_configured", True)

    tokens = iter([
        {"access_token": "first-tok", "refresh_token": "first-refresh", "expires_in": 3600},
        {"access_token": "second-tok", "refresh_token": "second-refresh", "expires_in": 3600},
    ])

    async def fake_authenticate(authorization_code, redirect_uri):
        return next(tokens)

    async def fake_get_user_leagues(access_token, season=2024):
        return yahoo_leagues_payload("333", "Carol's League")

    monkeypatch.setattr(yahoo_service, "authenticate", fake_authenticate)
    monkeypatch.setattr(yahoo_service, "get_user_leagues", fake_get_user_leagues)

    first = client.post(
        "/api/v1/leagues/yahoo/connect",
        json={"authorization_code": "carol-code-1", "redirect_uri": "http://localhost:3001/yahoo/callback"},
        headers=headers,
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/leagues/yahoo/connect",
        json={"authorization_code": "carol-code-2", "redirect_uri": "http://localhost:3001/yahoo/callback"},
        headers=headers,
    )
    assert second.status_code == 200

    db = TestingSessionLocal()
    try:
        rows = (
            db.query(UserLeague)
            .filter(UserLeague.platform == PlatformType.YAHOO, UserLeague.league_id == "333")
            .all()
        )
        # Reconnect updates the existing row rather than creating a duplicate.
        assert len(rows) == 1
        assert rows[0].yahoo_access_token == "second-tok"
        assert rows[0].yahoo_refresh_token == "second-refresh"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3. Expired/missing token handling is honest, not a silent/generic failure
# ---------------------------------------------------------------------------

def test_league_management_service_rejects_missing_yahoo_token(setup_database):
    db = TestingSessionLocal()
    try:
        service = LeagueManagementService(db)
        league = UserLeague(
            user_id=1, platform=PlatformType.YAHOO, league_id="1", league_key="423.l.1"
        )
        assert service._get_yahoo_token(league) is None
    finally:
        db.close()


def test_league_management_service_rejects_expired_yahoo_token(setup_database):
    db = TestingSessionLocal()
    try:
        service = LeagueManagementService(db)
        league = UserLeague(
            user_id=1,
            platform=PlatformType.YAHOO,
            league_id="1",
            league_key="423.l.1",
            yahoo_access_token="stale-token",
            yahoo_token_expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert service._get_yahoo_token(league) is None
    finally:
        db.close()


def test_league_management_service_accepts_valid_yahoo_token(setup_database):
    db = TestingSessionLocal()
    try:
        service = LeagueManagementService(db)
        league = UserLeague(
            user_id=1,
            platform=PlatformType.YAHOO,
            league_id="1",
            league_key="423.l.1",
            yahoo_access_token="fresh-token",
            yahoo_token_expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert service._get_yahoo_token(league) == "fresh-token"
    finally:
        db.close()
