"""
Integration tests for the mock-draft save/retrieve round trip:

  POST /api/v1/draft/mock-draft-results
  GET  /api/v1/users/me/drafts
  GET  /api/v1/users/me/drafts/{session_id}

These exercise the full FastAPI + isolated SQLite DB stack (not just the pure
grading function), and specifically check that GET /users/me/drafts and its
new /{session_id} sibling return well-formed JSON (no leaked ORM internals
like `_sa_instance_state`, and datetime/JSON columns serialize cleanly).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.base import Base
from app.api.deps import get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_mock_draft.db"
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


@pytest.fixture
def auth_headers(client, setup_database):
    user_data = {
        "email": "mockdrafter@example.com",
        "username": "mockdrafter",
        "password": "TestPassword123",
        "full_name": "Mock Drafter",
    }
    client.post("/api/v1/auth/register", json=user_data)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def sample_request_body():
    return {
        "draft_settings": {
            "scoring_format": "PPR",
            "team_count": 12,
            "draft_position": 6,
            "total_rounds": 3,
        },
        "user_roster": [
            {
                "sleeper_id": "1001",
                "full_name": "Star Quarterback",
                "position": "QB",
                "team": "AAA",
                "round": 1,
                "pick": 6,
                "search_rank": 5,
                "adp": 6.2,
                "projected_points": 320.5,
            },
            {
                "sleeper_id": "1002",
                "full_name": "Reach Runningback",
                "position": "RB",
                "team": "BBB",
                "round": 2,
                "pick": 18,
                "search_rank": 80,
            },
            {
                "sleeper_id": "1003",
                "full_name": "No Data Wideout",
                "position": "WR",
                "team": "CCC",
                "round": 3,
                "pick": 30,
            },
        ],
    }


def test_mock_draft_results_round_trip(client, auth_headers):
    # 1. POST the completed mock draft.
    post_response = client.post(
        "/api/v1/draft/mock-draft-results",
        json=sample_request_body(),
        headers=auth_headers,
    )
    assert post_response.status_code == 200, post_response.text
    post_data = post_response.json()

    assert post_data["session_id"].startswith("mock-")
    assert post_data["draft_grade"] in ("A", "B", "C", "D", "F")
    assert isinstance(post_data["composition_score"], (int, float))
    assert "QB" in post_data["position_breakdown"]
    assert len(post_data["value_analysis"]) == 3
    assert isinstance(post_data["final_analysis"], str) and post_data["final_analysis"]
    assert post_data["completed_at"]  # non-empty ISO datetime string

    session_id = post_data["session_id"]

    # 2. GET the list of draft sessions -- must be well-formed JSON with no
    # leaked ORM internals, and must include the session we just created.
    list_response = client.get("/api/v1/users/me/drafts", headers=auth_headers)
    assert list_response.status_code == 200, list_response.text
    list_data = list_response.json()

    assert list_data["total"] == 1
    assert len(list_data["draft_sessions"]) == 1
    summary = list_data["draft_sessions"][0]

    assert summary["session_id"] == session_id
    assert summary["platform"] == "mock"
    assert summary["is_completed"] is True
    assert summary["is_active"] is False
    assert summary["draft_grade"] == post_data["draft_grade"]
    assert "_sa_instance_state" not in summary
    assert summary["draft_settings"]["scoring_format"] == "PPR"
    # started_at/completed_at must have serialized to real ISO datetime strings
    assert isinstance(summary["started_at"], str)
    assert isinstance(summary["completed_at"], str)

    # 3. GET the single-session detail -- must include the full roster and
    # final_analysis text that the list response intentionally omits.
    detail_response = client.get(f"/api/v1/users/me/drafts/{session_id}", headers=auth_headers)
    assert detail_response.status_code == 200, detail_response.text
    detail_data = detail_response.json()

    assert "_sa_instance_state" not in detail_data
    assert detail_data["session_id"] == session_id
    assert detail_data["final_analysis"] == post_data["final_analysis"]
    assert len(detail_data["user_roster"]) == 3
    assert detail_data["user_roster"][0]["full_name"] == "Star Quarterback"
    assert detail_data["draft_grade"] == post_data["draft_grade"]


def test_get_draft_session_detail_not_found(client, auth_headers):
    response = client.get("/api/v1/users/me/drafts/mock-does-not-exist", headers=auth_headers)
    assert response.status_code == 404


def test_get_draft_session_detail_not_owned_by_requester(client, auth_headers):
    # Create a session as the first user.
    post_response = client.post(
        "/api/v1/draft/mock-draft-results",
        json=sample_request_body(),
        headers=auth_headers,
    )
    session_id = post_response.json()["session_id"]

    # A second user must not be able to fetch it -- 404, not 403, so as not
    # to leak whether the session_id exists at all.
    other_user_data = {
        "email": "someoneelse@example.com",
        "username": "someoneelse",
        "password": "TestPassword123",
        "full_name": "Someone Else",
    }
    client.post("/api/v1/auth/register", json=other_user_data)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": other_user_data["email"], "password": other_user_data["password"]},
    )
    other_token = login_response.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = client.get(f"/api/v1/users/me/drafts/{session_id}", headers=other_headers)
    assert response.status_code == 404


def test_mock_draft_results_requires_auth(client, setup_database):
    response = client.post("/api/v1/draft/mock-draft-results", json=sample_request_body())
    assert response.status_code in (401, 403)
