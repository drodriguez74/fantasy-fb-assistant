"""
Tests for the league connect/persist flows (ESPN team_id capture, Sleeper
connect). These monkeypatch the platform services so the tests don't depend
on live network calls to ESPN/Sleeper.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.base import Base
from app.api.deps import get_db
from app.services import espn_service_enhanced as espn_module
from app.services import sleeper_service as sleeper_module

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_leagues_connect.db"
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


def _register_and_login(client, suffix):
    user_data = {
        "email": f"leaguetest{suffix}@example.com",
        "username": f"leaguetest{suffix}",
        "password": "TestPassword123",
        "full_name": "League Test User",
    }
    r = client.post("/api/v1/auth/register", json=user_data)
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_espn_connect_persists_team_id(client, setup_database, monkeypatch):
    """Regression test: ESPN connect used to never capture team_id, leaving
    it permanently null and blocking roster/matchup analysis. Passing
    team_id through the connect request should now persist it."""

    async def fake_connect_league(league_id, season=2024, swid=None, espn_s2=None):
        return {
            "connected": True,
            "access_level": "public",
            "league_info": {
                "league_name": "Test ESPN League",
                "team_count": 10,
                "scoring_type": "PPR",
                "current_week": 1,
            },
        }

    monkeypatch.setattr(espn_module.espn_service_enhanced, "connect_league", fake_connect_league)

    headers = _register_and_login(client, "espn")

    r = client.post(
        "/api/v1/leagues/espn/connect",
        json={"league_id": "12345", "season": 2025, "team_id": "7"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["league"]["team_id"] == "7"

    r = client.get("/api/v1/leagues/", headers=headers)
    assert r.status_code == 200, r.text
    leagues = r.json()
    assert len(leagues) == 1
    assert leagues[0]["team_id"] == "7"
    assert leagues[0]["platform"] == "ESPN"


def test_espn_teams_endpoint_lists_teams(client, setup_database, monkeypatch):
    async def fake_get_league_teams(league_id, season=2024, swid=None, espn_s2=None):
        return [
            {"team_id": 1, "team_name": "Team One", "owner": "Alice"},
            {"team_id": 2, "team_name": "Team Two", "owner": "Bob"},
        ]

    monkeypatch.setattr(espn_module.espn_service_enhanced, "get_league_teams", fake_get_league_teams)

    r = client.get("/api/v1/leagues/espn/teams", params={"league_id": "12345", "season": 2025})
    assert r.status_code == 200, r.text
    teams = r.json()["teams"]
    assert teams == [
        {"team_id": "1", "team_name": "Team One", "owner": "Alice"},
        {"team_id": "2", "team_name": "Team Two", "owner": "Bob"},
    ]


def test_sleeper_connect_persists_league_and_resolves_team_id(client, setup_database, monkeypatch):
    """Regression test: there was previously no Sleeper connect/persist flow
    at all. This exercises the new endpoint end to end, including resolving
    team_id from a username."""

    async def fake_get_league_info(league_id):
        return {
            "league_id": league_id,
            "name": "Test Sleeper League",
            "season": "2025",
            "total_rosters": 12,
            "scoring_settings": {"rec": 1.0},
        }

    async def fake_get_user_by_username(username):
        assert username == "founder"
        return {"user_id": "u1", "display_name": "founder"}

    async def fake_get_league_rosters(league_id):
        return [
            {"roster_id": 3, "owner_id": "u1"},
            {"roster_id": 4, "owner_id": "u2"},
        ]

    monkeypatch.setattr(sleeper_module.sleeper_service, "get_league_info", fake_get_league_info)
    monkeypatch.setattr(sleeper_module.sleeper_service, "get_user_by_username", fake_get_user_by_username)
    monkeypatch.setattr(sleeper_module.sleeper_service, "get_league_rosters", fake_get_league_rosters)

    headers = _register_and_login(client, "sleeper")

    r = client.post(
        "/api/v1/leagues/sleeper/connect",
        json={"league_id": "999888777", "username": "founder"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["league"]["platform"] == "SLEEPER"
    assert body["league"]["team_id"] == "3"
    assert body["league"]["scoring_format"] == "PPR"

    r = client.get("/api/v1/leagues/", headers=headers)
    assert r.status_code == 200, r.text
    leagues = r.json()
    assert len(leagues) == 1
    assert leagues[0]["platform"] == "SLEEPER"
    assert leagues[0]["team_id"] == "3"
    assert leagues[0]["is_active"] is True


def test_sleeper_connect_rejects_unknown_league(client, setup_database, monkeypatch):
    async def fake_get_league_info(league_id):
        return {"error": "Request failed: 404"}

    monkeypatch.setattr(sleeper_module.sleeper_service, "get_league_info", fake_get_league_info)

    headers = _register_and_login(client, "sleeperbad")

    r = client.post(
        "/api/v1/leagues/sleeper/connect",
        json={"league_id": "doesnotexist"},
        headers=headers,
    )
    assert r.status_code == 400
