from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class WatchAlert(Base):
    """"Alert me if it becomes a bet" on a watch-list line (watch_alerts.py).
    Checked on every board build: when the same pick (player or game, market,
    side) is priced as a real bet -- EV >= 3% with every check agreeing -- the
    user gets an in-app notification and the alert is marked triggered.
    Expires at kickoff."""

    __tablename__ = "watch_alerts"
    __table_args__ = (
        UniqueConstraint("user_id", "season", "week", "kind", "subject", "market", "side", name="uq_watch_alert"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    season = Column(Integer, nullable=False)
    week = Column(Integer, nullable=False)
    kind = Column(String, nullable=False)          # "player_prop" | "game" | "cfb_game"
    subject = Column(String, nullable=False)       # player name, or game label "SF @ SEA"
    market = Column(String, nullable=False)
    side = Column(String, nullable=False)
    line = Column(Float, nullable=True)            # line when set (a moved line still counts)
    target_price = Column(Integer, nullable=True)  # worst price that clears the bar when set
    p_win = Column(Float, nullable=True)           # win chance when set
    book = Column(String, nullable=True)
    price = Column(Integer, nullable=True)         # price when set
    kickoff = Column(DateTime(timezone=True), nullable=True)
    engine_version = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active", index=True)  # active | triggered | expired
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    triggered_line = Column(Float, nullable=True)
    triggered_book = Column(String, nullable=True)
    triggered_price = Column(Integer, nullable=True)
    triggered_units = Column(Float, nullable=True)
