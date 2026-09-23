"""GET /waiver-wire/league-aware-recommendations/{league_id} reports the
caller's own real league -- it used to read a shared file and report every
league as ESPN, inventing a "Demo ESPN League" for any id but 1."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.api.v1.endpoints import waiver_wire
from app.db.base import Base
from app.main import app
from app.models.user import User
from app.models.user_league import PlatformType, UserLeague
from app.services.waiver_wire_service import WaiverWireService

engine = create_engine("sqlite:///./test_league_aware_waivers.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def client(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    owner = User(email="owner@test.com", username="owner", hashed_password="x", is_active=True)
    db.add(owner)
    db.commit()
    db.add(UserLeague(user_id=owner.id, platform=PlatformType.YAHOO, league_id="99", league_key="461.l.99",
                      league_name="Pro Bowl Fantasy", season=2026, scoring_format="PPR"))
    db.commit()
    user_id = owner.id
    db.close()

    def override_db():
        s = TestingSessionLocal()
        try:
            yield s
        finally:
            s.close()

    def override_user():
        s = TestingSessionLocal()
        try:
            return s.get(User, user_id)
        finally:
            s.close()

    async def no_roster(db, user, league_id):
        return None, None, None, None, None, None

    async def no_recs(self, **kwargs):
        return []

    monkeypatch.setattr(waiver_wire, "_fetch_connected_roster_and_settings", no_roster)
    monkeypatch.setattr(WaiverWireService, "get_live_trending_recommendations", no_recs)
    app.dependency_overrides[deps.get_db] = override_db
    app.dependency_overrides[deps.get_current_active_user] = override_user
    yield TestClient(app)
    app.dependency_overrides.pop(deps.get_db, None)
    app.dependency_overrides.pop(deps.get_current_active_user, None)


def test_reports_the_callers_real_league(client):
    league_id = TestingSessionLocal().query(UserLeague).one().id
    r = client.get(f"/api/v1/waiver-wire/league-aware-recommendations/{league_id}", params={"week": 3})
    assert r.status_code == 200
    info = r.json()["league_info"]
    assert info == {"id": league_id, "name": "Pro Bowl Fantasy", "platform": "YAHOO",
                    "scoring_format": "PPR", "season": 2026}


def test_unknown_league_is_404_not_demo_data(client):
    r = client.get("/api/v1/waiver-wire/league-aware-recommendations/12345", params={"week": 3})
    assert r.status_code == 404
