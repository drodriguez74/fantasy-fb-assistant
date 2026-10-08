"""Pregame weather forecasts: the kickoff-hour pick, and freezing at kickoff (SQLite, no network)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.game_weather import GameWeather
from app.services import game_weather as gw


def test_nearest_hour_picks_the_kickoff_hour():
    hourly = {"time": ["2026-10-11T16:00", "2026-10-11T17:00", "2026-10-11T18:00"],
              "wind_speed_10m": [8.0, 14.0, 20.0], "wind_gusts_10m": [12.0, 22.0, 30.0],
              "temperature_2m": [60, 61, 62], "precipitation_probability": [10, 20, 30]}
    h = gw.nearest_hour(hourly, datetime(2026, 10, 11, 17, 5, tzinfo=timezone.utc))
    assert h == {"wind_mph": 14.0, "gust_mph": 22.0, "temp_f": 61, "precip_prob": 20}
    assert gw.nearest_hour(hourly, datetime(2026, 10, 12, 17, tzinfo=timezone.utc)) is None  # outside the window


@pytest.fixture
def db(test_engine, monkeypatch):
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(gw, "SessionLocal", Session)
    yield Session
    with Session() as s:
        s.query(GameWeather).delete()
        s.commit()


def test_forecast_freezes_at_kickoff(db):
    kickoff = datetime.now(timezone.utc) + timedelta(hours=5)
    gw.save(2099, 5, "CHI @ GB", {"kickoff": kickoff, "indoor": False, "wind_mph": 9.0, "source": "open-meteo"})
    gw.save(2099, 5, "CHI @ GB", {"kickoff": kickoff, "indoor": False, "wind_mph": 16.0, "source": "open-meteo"})
    gw.save(2099, 5, "CHI @ GB", {"kickoff": kickoff, "wind_mph": 30.0}, now=kickoff + timedelta(minutes=5))
    with db() as s:
        assert s.query(GameWeather).one().wind_mph == 16.0   # the last pregame forecast
