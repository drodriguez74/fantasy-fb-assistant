"""
Pytest configuration and shared fixtures
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.api.deps import get_db
from app.main import app

# Test database URL
TEST_DATABASE_URL = "sqlite:///./test_fantasy_football.db"

@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine"""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def test_db_session(test_engine):
    """Create test database session"""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    yield session
    session.close()

@pytest.fixture
def override_db_dependency(test_db_session):
    """Override database dependency for testing"""
    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()

@pytest.fixture(autouse=True)
def all_books_playable(monkeypatch):
    """Tests price every book as playable unless they set BETTING_MY_BOOKS
    themselves (the app's default is the founder's Florida book)."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "BETTING_MY_BOOKS", None, raising=False)
