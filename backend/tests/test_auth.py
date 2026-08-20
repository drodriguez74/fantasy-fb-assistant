"""
Tests for authentication endpoints
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.base import Base
from app.api.deps import get_db
from app.services.user_service import UserService

# Test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
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
    # Scoped to each test (not a bare module-level assignment) so the override
    # is removed afterwards. Without teardown, this permanently redirected the
    # shared `app`'s get_db to this file's SQLite engine for every test that
    # ran later in the same pytest session — including other test files —
    # which broke once setup_database (below) dropped its tables.
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture
def setup_database():
    # Function-scoped (not module-scoped) so each test starts from a clean,
    # empty database. Module scope let earlier tests' users (e.g. the shared
    # test_user_data fixture) leak into later tests in the same file, making
    # test_duplicate_registration fail/pass depending on test execution order.
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def test_user_data():
    return {
        "email": "test@example.com",
        "username": "testuser",
        "password": "TestPassword123",
        "full_name": "Test User"
    }

def test_user_registration(client, setup_database, test_user_data):
    """Test user registration endpoint"""
    response = client.post("/api/v1/auth/register", json=test_user_data)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user_data["email"]
    assert data["username"] == test_user_data["username"]
    assert "id" in data

def test_user_login(client, setup_database, test_user_data):
    """Test user login endpoint"""
    # First register user
    client.post("/api/v1/auth/register", json=test_user_data)
    
    # Then try to login
    login_data = {
        "email": test_user_data["email"],
        "password": test_user_data["password"]
    }
    response = client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_duplicate_registration(client, setup_database, test_user_data):
    """Test that duplicate registration fails"""
    # Register user first time
    response1 = client.post("/api/v1/auth/register", json=test_user_data)
    assert response1.status_code == 200
    
    # Try to register same email again
    response2 = client.post("/api/v1/auth/register", json=test_user_data)
    assert response2.status_code == 400
    assert "already registered" in response2.json()["detail"].lower()

def test_invalid_login(client, setup_database):
    """Test login with invalid credentials"""
    login_data = {
        "email": "nonexistent@example.com",
        "password": "wrongpassword"
    }
    response = client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 401

def test_get_current_user(client, setup_database, test_user_data):
    """Test getting current user info"""
    # Register and login
    client.post("/api/v1/auth/register", json=test_user_data)
    login_response = client.post("/api/v1/auth/login", json={
        "email": test_user_data["email"],
        "password": test_user_data["password"]
    })
    token = login_response.json()["access_token"]
    
    # Get current user
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user_data["email"]