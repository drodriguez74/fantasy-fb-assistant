"""
Tests for Yahoo Phase 2: wiring the Live Draft Assistant to Yahoo's real
Fantasy API, mirroring the ESPN live-draft fix (045a5c7) and the
roster/scoring-settings fix (b05bee1) applied to Yahoo.

Covers:
  - yahoo_service.get_league_settings() reshapes a realistic Yahoo
    league/settings response (roster_positions + stat_modifiers, in the
    same numeric-keyed dict shape yahoo_service's existing methods already
    parse Yahoo's JSON responses into) into the canonical
    {starters, bench, roster_size, points_per_reception, source} shape,
    including W/R/T flex folding into "FLEX" and NOT folding a superflex
    Q/W/R/T slot into RB/WR/TE.
  - draft_assistant_service._get_yahoo_draft_state reshapes realistic
    Yahoo league_info/draft_results/available_players responses into the
    same draft-state contract _get_sleeper_draft_state/_get_espn_draft_state
    already establish (status, current_pick, available_players w/
    full_name+ownership, league_settings, ...).
  - Missing/expired Yahoo access tokens fail a poll honestly and
    specifically (the token-refresh-during-polling decision documented in
    _get_yahoo_draft_state's docstring), without ever calling Yahoo.
  - A real 401 from Yahoo mid-poll is translated to the same clear
    reconnect message, not a generic failure.
  - live_draft.py's POST /start-session, platform=yahoo: requires auth,
    honestly 400s when the user has no connected Yahoo UserLeague row for
    that league_id, honestly 400s when the stored token is expired, and
    (on a valid connection) threads the real access_token + league_key
    through to draft_assistant_service without ever trusting the request
    body for credentials.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.api.deps import get_db
from app.models.user_league import UserLeague, PlatformType
from app.services.yahoo_service import yahoo_service
from app.services.draft_assistant_service import draft_assistant, DraftPlatform

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_yahoo_live_draft.db"
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


@pytest.fixture(autouse=True)
def clear_active_drafts():
    # draft_assistant is a module-level singleton (active_drafts dict);
    # don't let sessions from one test leak into another.
    draft_assistant.active_drafts.clear()
    yield
    draft_assistant.active_drafts.clear()


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


# ---------------------------------------------------------------------------
# Realistic Yahoo response fixtures
#
# Field names/nesting here match yahoo_service.py's *existing* parsing code
# for get_user_leagues/get_league_info/get_league_teams/get_available_players
# /get_draft_results (numeric-string-keyed dicts each wrapping a single
# named key, e.g. {"0": {"roster_position": {...}}, "1": {...}}) -- the same
# convention Yahoo's real JSON Fantasy API uses and this file's other
# methods already parse this way. roster_positions/stat_modifiers field
# names (position, count, name, display_name, value) match the real Yahoo
# Fantasy API field set as exposed by yfpy's Settings/RosterPosition/
# StatModifiers/Stat model classes (Yahoo's own developer docs are no
# longer reachable to cite directly).
# ---------------------------------------------------------------------------

def _roster_position(position, count):
    return {"roster_position": {"position": position, "count": str(count)}}


def _stat(name, display_name, value):
    return {"stat": {"name": name, "display_name": display_name, "value": value}}


def ppr_settings_response():
    """A realistic full-PPR, 1-FLEX (W/R/T) Yahoo league settings response."""
    return {
        "fantasy_content": {
            "league": {
                "settings": {
                    "roster_positions": {
                        "0": _roster_position("QB", 1),
                        "1": _roster_position("WR", 2),
                        "2": _roster_position("RB", 2),
                        "3": _roster_position("TE", 1),
                        "4": _roster_position("W/R/T", 1),
                        "5": _roster_position("K", 1),
                        "6": _roster_position("DEF", 1),
                        "7": _roster_position("BN", 6),
                        "8": _roster_position("IR", 1),
                    },
                    "stat_modifiers": {
                        "stats": {
                            "0": _stat("Passing Yards", "Pass Yds", "0.04"),
                            "1": _stat("Receptions", "Rec", "1"),
                            "2": _stat("Rushing Yards", "Rush Yds", "0.1"),
                        }
                    },
                }
            }
        }
    }


def superflex_settings_response():
    """A superflex (Q/W/R/T) league on standard (0 PPR) scoring."""
    return {
        "fantasy_content": {
            "league": {
                "settings": {
                    "roster_positions": {
                        "0": _roster_position("QB", 1),
                        "1": _roster_position("WR", 2),
                        "2": _roster_position("RB", 2),
                        "3": _roster_position("TE", 1),
                        "4": _roster_position("Q/W/R/T", 1),
                        "5": _roster_position("BN", 5),
                    },
                    "stat_modifiers": {
                        "stats": {
                            "0": _stat("Passing Yards", "Pass Yds", "0.04"),
                        }
                    },
                }
            }
        }
    }


def league_info_response(draft_status="drafting", num_teams=10):
    return {
        "fantasy_content": {
            "league": {
                "league_key": "423.l.999",
                "league_id": "999",
                "name": "Test Yahoo League",
                "num_teams": num_teams,
                "current_week": "1",
                "start_week": "1",
                "end_week": "17",
                "scoring_type": "head",
                "league_type": "private",
                "draft_status": draft_status,
            }
        }
    }


def draft_results_response(num_picks=3):
    picks = {}
    for i in range(num_picks):
        picks[str(i)] = {
            "draft_result": {
                "pick": i + 1,
                "round": 1,
                "team_key": f"423.l.999.t.{(i % 10) + 1}",
                "player_key": f"423.p.{1000 + i}",
            }
        }
    return {"fantasy_content": {"league": {"draft_results": picks}}}


def available_players_response():
    return {
        "fantasy_content": {
            "league": {
                "players": {
                    "0": {
                        "player": {
                            "player_key": "423.p.5000",
                            "player_id": "5000",
                            "name": {"full": "Test Player One"},
                            "editorial_team_abbr": "KC",
                            "percent_owned": {"value": "42.5"},
                            "status": None,
                        }
                    },
                    "1": {
                        "player": {
                            "player_key": "423.p.5001",
                            "player_id": "5001",
                            "name": {"full": "Test Player Two"},
                            "editorial_team_abbr": "SF",
                            "percent_owned": {"value": "10.0"},
                            "status": None,
                        }
                    },
                }
            }
        }
    }


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.headers = {"content-type": "application/json"}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                f"Client error '{self.status_code} Unauthorized' for url",
                request=httpx.Request("GET", "https://example.com"),
                response=httpx.Response(self.status_code, request=httpx.Request("GET", "https://example.com")),
            )

    def json(self):
        return self._payload


# ---------------------------------------------------------------------------
# 1. yahoo_service.get_league_settings() -- real response reshape
# ---------------------------------------------------------------------------

def test_get_league_settings_full_ppr_folds_flex(monkeypatch):
    async def fake_get(self, url, headers=None, params=None):
        assert "settings" in url
        return _FakeResponse(ppr_settings_response())

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    import asyncio
    result = asyncio.run(yahoo_service.get_league_settings("tok", "423.l.999"))

    assert "error" not in result
    assert result["source"] == "yahoo"
    assert result["points_per_reception"] == 1.0
    assert result["bench"] == 6
    # The W/R/T flex slot must fold into "FLEX" (not survive as its own
    # literal "W/R/T" key), same vocabulary _effective_position_requirements
    # already knows how to distribute across RB/WR/TE.
    assert result["starters"]["FLEX"] == 1
    assert "W/R/T" not in result["starters"]
    assert result["starters"]["QB"] == 1
    assert result["starters"]["WR"] == 2
    assert result["starters"]["RB"] == 2
    assert result["starters"]["TE"] == 1
    assert result["starters"]["K"] == 1
    assert result["starters"]["DEF"] == 1
    # IR is real but not a starting-lineup need.
    assert "IR" not in result["starters"]
    # roster_size counts every real slot including IR (mirrors Sleeper's
    # parse_league_settings using the raw array length).
    assert result["roster_size"] == 1 + 2 + 2 + 1 + 1 + 1 + 1 + 6 + 1


def test_get_league_settings_superflex_not_folded_into_flex(monkeypatch):
    async def fake_get(self, url, headers=None, params=None):
        return _FakeResponse(superflex_settings_response())

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    import asyncio
    result = asyncio.run(yahoo_service.get_league_settings("tok", "423.l.999"))

    assert "error" not in result
    # Standard scoring: no "Receptions" stat_modifier present at all.
    assert result["points_per_reception"] == 0.0
    # A superflex slot (includes QB) must NOT be folded into RB/WR/TE's
    # "FLEX" -- that would understate real QB need.
    assert "FLEX" not in result["starters"]
    assert result["starters"]["Q/W/R/T"] == 1
    assert result["starters"]["QB"] == 1


def test_get_league_settings_requires_token():
    import asyncio
    result = asyncio.run(yahoo_service.get_league_settings(None, "423.l.999"))
    assert result == {"error": "Not authenticated"}


# ---------------------------------------------------------------------------
# 2. draft_assistant_service._get_yahoo_draft_state -- full reshape
# ---------------------------------------------------------------------------

def test_get_yahoo_draft_state_reshapes_real_data(monkeypatch):
    """The core of this phase: given realistic Yahoo API responses,
    _get_yahoo_draft_state must produce the same contract
    _get_sleeper_draft_state/_get_espn_draft_state already establish.
    """
    monkeypatch.setattr(
        yahoo_service, "get_league_info",
        AsyncMock(return_value={
            "league_key": "423.l.999", "league_id": "999", "name": "Test Yahoo League",
            "num_teams": 10, "draft_status": "drafting",
        }),
    )
    monkeypatch.setattr(
        yahoo_service, "get_draft_results",
        AsyncMock(return_value=[
            {"pick": 1, "round": 1, "team_key": "423.l.999.t.1", "player_key": "423.p.1"},
            {"pick": 2, "round": 1, "team_key": "423.l.999.t.2", "player_key": "423.p.2"},
        ]),
    )
    monkeypatch.setattr(
        yahoo_service, "get_available_players",
        AsyncMock(return_value=[
            {"player_key": "423.p.5000", "player_id": "5000", "name": "Test Player One",
             "position": "WR", "team": "KC", "ownership_percentage": "42.5", "status": None},
            {"player_key": "423.p.5001", "player_id": "5001", "name": "Test Player Two",
             "position": "RB", "team": "SF", "ownership_percentage": "10.0", "status": None},
        ]),
    )
    monkeypatch.setattr(
        yahoo_service, "get_league_settings",
        AsyncMock(return_value={
            "starters": {"QB": 1, "WR": 2, "RB": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1},
            "bench": 6, "roster_size": 15, "points_per_reception": 1.0, "source": "yahoo",
        }),
    )

    import asyncio
    state = asyncio.run(draft_assistant._get_yahoo_draft_state(
        "423.l.999", {"access_token": "real-tok"}
    ))

    assert "error" not in state
    assert state["status"] == "drafting"
    assert state["current_pick"] == 3  # len(picks) + 1
    assert state["total_picks"] == 10 * 15  # team_count * roster_size
    assert len(state["available_players"]) == 2
    # Reshape: Yahoo's "name"/"ownership_percentage" -> shared
    # "full_name"/"ownership", same reshape pattern as the ESPN fix.
    names = {p["full_name"] for p in state["available_players"]}
    assert names == {"Test Player One", "Test Player Two"}
    for p in state["available_players"]:
        assert "ownership" in p
    assert state["league_settings"]["points_per_reception"] == 1.0
    assert state["league_settings"]["starters"]["FLEX"] == 1
    assert state["trending_players"] == []
    assert state["draft_info"]["draft_status"] == "drafting"


def test_get_yahoo_draft_state_draft_complete(monkeypatch):
    monkeypatch.setattr(
        yahoo_service, "get_league_info",
        AsyncMock(return_value={"num_teams": 10, "draft_status": "postdraft"}),
    )
    monkeypatch.setattr(yahoo_service, "get_draft_results", AsyncMock(return_value=[]))
    monkeypatch.setattr(yahoo_service, "get_available_players", AsyncMock(return_value=[]))
    monkeypatch.setattr(yahoo_service, "get_league_settings", AsyncMock(return_value={"error": "unavailable"}))

    import asyncio
    state = asyncio.run(draft_assistant._get_yahoo_draft_state(
        "423.l.999", {"access_token": "real-tok"}
    ))

    assert state["status"] == "complete"
    # Failed settings call falls back to None, not a fabricated shape --
    # draft_assistant_service._get_league_settings handles None via
    # FALLBACK_ROSTER_REQUIREMENTS.
    assert state["league_settings"] is None
    # roster_size fallback of 16 when no real settings are available.
    assert state["total_picks"] == 10 * 16


# ---------------------------------------------------------------------------
# 3. Honest failure on missing/expired token -- the token-refresh decision
# ---------------------------------------------------------------------------

def test_get_yahoo_draft_state_no_token_never_calls_yahoo(monkeypatch):
    calls = []
    monkeypatch.setattr(yahoo_service, "get_league_info", AsyncMock(side_effect=lambda *a, **kw: calls.append(1)))

    import asyncio
    state = asyncio.run(draft_assistant._get_yahoo_draft_state("423.l.999", {}))

    assert "error" in state
    assert "connect your yahoo account" in state["error"].lower()
    assert calls == []  # never even attempted a network call


def test_get_yahoo_draft_state_expired_token_never_calls_yahoo(monkeypatch):
    calls = []
    monkeypatch.setattr(yahoo_service, "get_league_info", AsyncMock(side_effect=lambda *a, **kw: calls.append(1)))

    import asyncio
    state = asyncio.run(draft_assistant._get_yahoo_draft_state(
        "423.l.999",
        {"access_token": "stale-tok", "expires_at": datetime.utcnow() - timedelta(hours=1)},
    ))

    assert "error" in state
    assert "expired" in state["error"].lower()
    assert "reconnect" in state["error"].lower()
    assert calls == []


def test_get_yahoo_draft_state_valid_expiry_proceeds(monkeypatch):
    """A token with a real future expires_at must NOT be rejected -- only
    an actually-past expiry (or a real 401) should short-circuit."""
    monkeypatch.setattr(
        yahoo_service, "get_league_info",
        AsyncMock(return_value={"num_teams": 10, "draft_status": "predraft"}),
    )
    monkeypatch.setattr(yahoo_service, "get_draft_results", AsyncMock(return_value=[]))
    monkeypatch.setattr(yahoo_service, "get_available_players", AsyncMock(return_value=[]))
    monkeypatch.setattr(yahoo_service, "get_league_settings", AsyncMock(return_value={"error": "n/a"}))

    import asyncio
    state = asyncio.run(draft_assistant._get_yahoo_draft_state(
        "423.l.999",
        {"access_token": "fresh-tok", "expires_at": datetime.utcnow() + timedelta(hours=1)},
    ))

    assert "error" not in state


def test_get_yahoo_draft_state_401_mid_poll_gets_reconnect_message(monkeypatch):
    """No expires_at was tracked (or the token was revoked/outlived a
    slightly-wrong expiry) -- a genuine 401 from Yahoo must still produce
    the same clear reconnect message, not the raw HTTP error text, and not
    fabricated/stale data.
    """
    monkeypatch.setattr(
        yahoo_service, "get_league_info",
        AsyncMock(return_value={"error": "Failed to get league info: Client error '401 Unauthorized' for url"}),
    )

    import asyncio
    state = asyncio.run(draft_assistant._get_yahoo_draft_state(
        "423.l.999", {"access_token": "revoked-tok"}
    ))

    assert "error" in state
    assert "expired" in state["error"].lower()
    assert "reconnect" in state["error"].lower()
    # The raw Yahoo error text must not leak through once recognized as auth.
    assert "401" not in state["error"]


def test_get_yahoo_draft_state_non_auth_error_passes_through(monkeypatch):
    """A non-auth error (bad league_key, Yahoo outage) must be surfaced
    as-is, not overwritten with the auth-specific message."""
    monkeypatch.setattr(
        yahoo_service, "get_league_info",
        AsyncMock(return_value={"error": "Failed to get league info: league not found"}),
    )

    import asyncio
    state = asyncio.run(draft_assistant._get_yahoo_draft_state(
        "423.l.999", {"access_token": "real-tok"}
    ))

    assert "error" in state
    assert "league not found" in state["error"]
    assert "reconnect" not in state["error"].lower()


# ---------------------------------------------------------------------------
# 4. live_draft.py POST /start-session, platform=yahoo
# ---------------------------------------------------------------------------

def test_start_session_yahoo_requires_auth(client, setup_database):
    response = client.post(
        "/api/v1/draft/live-draft/start-session",
        json={"league_id": "999", "platform": "yahoo"},
    )
    assert response.status_code in (401, 403)


def test_start_session_yahoo_no_connected_league_is_honest_error(client, setup_database):
    """The exact scope-required check: an authenticated user with no Yahoo
    UserLeague row for this league_id must get a clear, specific error --
    not a generic 500, not a silently-empty session."""
    headers = register_and_login(client, "nodahoo@example.com", "nodahoo")

    response = client.post(
        "/api/v1/draft/live-draft/start-session",
        json={"league_id": "999", "platform": "yahoo"},
        headers=headers,
    )
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "no yahoo league connected" in detail
    assert "connect your yahoo account" in detail


def test_start_session_yahoo_expired_token_is_honest_error(client, setup_database):
    headers = register_and_login(client, "staleyahoo@example.com", "staleyahoo")

    db = TestingSessionLocal()
    try:
        # Look up the just-registered user's id via the users table directly
        # would require importing User; simpler to fetch via /auth/me.
        me = client.get("/api/v1/auth/me", headers=headers).json()
        user_id = me["id"]

        league = UserLeague(
            user_id=user_id,
            platform=PlatformType.YAHOO,
            league_id="999",
            league_key="423.l.999",
            yahoo_access_token="stale-tok",
            yahoo_token_expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.add(league)
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/v1/draft/live-draft/start-session",
        json={"league_id": "999", "platform": "yahoo"},
        headers=headers,
    )
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "expired" in detail
    assert "reconnect" in detail


def test_start_session_yahoo_valid_connection_threads_real_credentials(client, setup_database, monkeypatch):
    """The full path: a real connected Yahoo league with a valid token
    starts a session, and the session is driven by the real
    access_token/league_key pulled from the DB row -- never anything the
    client could pass in the request body.
    """
    headers = register_and_login(client, "realyahoo@example.com", "realyahoo")

    db = TestingSessionLocal()
    try:
        me = client.get("/api/v1/auth/me", headers=headers).json()
        user_id = me["id"]

        league = UserLeague(
            user_id=user_id,
            platform=PlatformType.YAHOO,
            league_id="999",
            league_key="423.l.999",
            league_name="Real Yahoo League",
            season=2025,
            scoring_format="PPR",
            league_size=10,
            yahoo_access_token="valid-access-tok",
            yahoo_token_expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.add(league)
        db.commit()
    finally:
        db.close()

    seen_tokens = []

    async def fake_get_league_info(access_token, league_key):
        seen_tokens.append(access_token)
        assert league_key == "423.l.999"  # real league_key, not the bare "999" id
        return {"num_teams": 10, "draft_status": "predraft"}

    monkeypatch.setattr(yahoo_service, "get_league_info", fake_get_league_info)
    monkeypatch.setattr(yahoo_service, "get_draft_results", AsyncMock(return_value=[]))
    monkeypatch.setattr(yahoo_service, "get_available_players", AsyncMock(return_value=[]))
    monkeypatch.setattr(yahoo_service, "get_league_settings", AsyncMock(return_value={"error": "n/a"}))

    response = client.post(
        "/api/v1/draft/live-draft/start-session",
        json={"league_id": "999", "platform": "yahoo"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "active"
    assert body["platform"] == "yahoo"
    # The real access token from the DB row was used on every call -- never
    # a request-body-trusted value (the request body carried no token at
    # all). start_draft_session fetches the initial state and then
    # immediately generates initial_recommendations (which refreshes the
    # state again), so real_get_league_info is legitimately called twice,
    # both times with the same real per-user token.
    assert seen_tokens
    assert set(seen_tokens) == {"valid-access-tok"}
