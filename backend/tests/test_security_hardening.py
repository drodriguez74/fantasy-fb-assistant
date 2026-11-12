"""Account and cost protections: closed registration, token types, the
per-IP rate limit, password hashing, and auth on the trade routes."""
import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit, security
from app.core.config import settings
from app.main import app

USER = {"email": "hardening@example.com", "username": "hardening", "password": "Password123", "full_name": "H"}


@pytest.fixture
def client(override_db_dependency):
    return TestClient(app)


def _register(client, **over):
    return client.post("/api/v1/auth/register", json={**USER, **over})


def test_registration_is_closed_when_no_emails_are_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "REGISTRATION_ALLOWED_EMAILS", None)
    r = _register(client, email="closed@example.com", username="closed1")
    assert r.status_code == 403
    assert "closed" in r.json()["detail"].lower()


def test_registration_allows_only_listed_emails(client, monkeypatch):
    monkeypatch.setattr(settings, "REGISTRATION_ALLOWED_EMAILS", "friend@example.com, Other@Example.com")
    assert _register(client, email="stranger@example.com", username="stranger1").status_code == 403
    # Case and spacing in the setting don't matter.
    assert _register(client, email="other@example.com", username="other1").status_code == 200


def test_refresh_token_is_not_an_access_token(client):
    _register(client, email="tok@example.com", username="tokuser")
    tokens = client.post("/api/v1/auth/login", json={"email": "tok@example.com", "password": USER["password"]}).json()
    as_access = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert as_access.status_code == 401
    ok = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert ok.status_code == 200


def test_access_token_cannot_refresh_but_refresh_token_can(client):
    _register(client, email="ref@example.com", username="refuser")
    tokens = client.post("/api/v1/auth/login", json={"email": "ref@example.com", "password": USER["password"]}).json()
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200


def test_reset_and_verification_tokens_are_not_access_tokens():
    assert security.verify_token(security.create_password_reset_token("a@b.co")) is None
    assert security.verify_token(security.create_email_verification_token("a@b.co")) is None
    assert security.verify_token(security.create_access_token(7)) == "7"


def test_a_token_for_a_missing_user_is_refused(client):
    # User id 1 used to be created on the fly as a demo account.
    token = security.create_access_token(987654)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_login_is_rate_limited_per_ip(client):
    body = {"email": "nobody@example.com", "password": "Wrong12345"}
    codes = [client.post("/api/v1/auth/login", json=body).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
    # Another address is counted on its own.
    other = client.post("/api/v1/auth/login", json=body, headers={"X-Forwarded-For": "203.0.113.9"})
    assert other.status_code == 401


def test_rate_limit_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    body = {"email": "nobody@example.com", "password": "Wrong12345"}
    assert {client.post("/api/v1/auth/login", json=body).status_code for _ in range(15)} == {401}


def test_password_reset_answer_does_not_reveal_accounts(client):
    _register(client, email="known@example.com", username="knownuser")
    known = client.post("/api/v1/auth/request-password-reset", json={"email": "known@example.com"})
    unknown = client.post("/api/v1/auth/request-password-reset", json={"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_trade_routes_need_a_login(client):
    assert client.get("/api/v1/trade/player-search", params={"q": "allen"}).status_code in (401, 403)
    assert client.post("/api/v1/trade/analysis", json={"give": ["1"], "get": ["2"]}).status_code in (401, 403)


def _login(client, email, username):
    _register(client, email=email, username=username)
    token = client.post("/api/v1/auth/login", json={"email": email, "password": USER["password"]}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_only_the_board_owner_can_replace_the_shared_board(client, monkeypatch):
    headers = _login(client, "second@example.com", "seconduser")
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["id"] != 1
    monkeypatch.setattr(settings, "BOARD_UPLOAD_EMAILS", None)
    paste = client.post("/api/v1/betting/betr-board", json={"text": "nothing useful"}, headers=headers)
    assert paste.status_code == 403
    upload = client.post("/api/v1/betting/prizepicks-board", files={"file": ("b.json", b"{}", "application/json")}, headers=headers)
    assert upload.status_code == 403
    shots = client.post("/api/v1/betting/betr-screenshots", files=[("files", ("a.png", b"x", "image/png"))], headers=headers)
    assert shots.status_code == 403
    # Listed by email: allowed through to the parser (which rejects this junk paste).
    monkeypatch.setattr(settings, "BOARD_UPLOAD_EMAILS", "Second@Example.com")
    assert client.post("/api/v1/betting/betr-board", json={"text": "nothing useful"}, headers=headers).status_code == 400


def test_retired_routes_are_gone(client):
    for path in ("/api/v1/game-situations/health", "/api/v1/analytics/health", "/api/v1/advanced-analysis/health"):
        assert client.get(path).status_code == 404


def test_password_hashing_round_trip_and_legacy_hash():
    hashed = security.get_password_hash("Password123")
    assert hashed.startswith("$2")
    assert security.verify_password("Password123", hashed)
    assert not security.verify_password("password123", hashed)
    # A hash made by passlib 1.7.4 + bcrypt 4.0.1 (what production holds).
    legacy = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
    assert security.verify_password("secret", legacy)
    assert not security.verify_password("Secret", legacy)


def test_long_passwords_and_bad_hashes_do_not_raise():
    long_pw = "Aa1" + "x" * 200
    assert security.verify_password(long_pw, security.get_password_hash(long_pw))
    assert security.verify_password("anything", "not-a-hash") is False
    assert security.verify_password("anything", "") is False
