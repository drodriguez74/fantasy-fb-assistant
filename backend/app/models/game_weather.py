from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class GameWeather(Base):
    """The pregame weather forecast for an NFL game (game_weather.py),
    refreshed on board builds until kickoff and then frozen -- what was
    knowable before the game. Logged so "wind unders" can be tested honestly:
    the 2015-24 signal used game-time wind, which nobody can bet on."""

    __tablename__ = "game_weather"
    __table_args__ = (UniqueConstraint("season", "week", "game", name="uq_game_weather"),)

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, nullable=False, index=True)
    week = Column(Integer, nullable=False, index=True)
    game = Column(String, nullable=False)              # "AWAY @ HOME" (ESPN abbreviations)
    kickoff = Column(DateTime(timezone=True), nullable=True)
    indoor = Column(Boolean, nullable=True)
    wind_mph = Column(Float, nullable=True)            # forecast 10 m wind at the kickoff hour
    gust_mph = Column(Float, nullable=True)
    temp_f = Column(Float, nullable=True)
    precip_prob = Column(Float, nullable=True)         # %
    condition = Column(String, nullable=True)          # ESPN's text, e.g. "Rain"
    source = Column(String, nullable=True)             # "open-meteo" | "indoor"
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
