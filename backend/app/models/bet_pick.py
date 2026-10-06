from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class BetPick(Base):
    """One priced line from the weekly betting board, frozen at the price
    we first saw it (see betting_tracking.py), then graded against real
    results (bet_grading.py).

    Every priced line is stored, not just recommendations (`recommended`
    = units > 0): the 0-unit rows are what let us check whether the win
    probabilities are calibrated, separately from whether the bets won.
    One row per (season, week, kind, subject, market). A row first seen as
    "no bet" is upgraded if it later becomes a recommendation; a
    recommendation is never overwritten, so the record reflects the price
    and units we actually showed.
    """

    __tablename__ = "bet_picks"
    __table_args__ = (
        UniqueConstraint("season", "week", "kind", "subject", "market", name="uq_bet_pick_line"),
    )

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, nullable=False, index=True)
    week = Column(Integer, nullable=False, index=True)
    kind = Column(String, nullable=False)        # "player_prop" | "game"
    subject = Column(String, nullable=False)     # player name, or game label "SF @ SEA"
    team = Column(String, nullable=True)         # player's NFL team (ESPN abbreviation)
    game = Column(String, nullable=False)        # "AWAY @ HOME"
    home = Column(String, nullable=True)
    away = Column(String, nullable=True)
    kickoff = Column(DateTime(timezone=True), nullable=True)
    market = Column(String, nullable=False)
    side = Column(String, nullable=False)
    line = Column(Float, nullable=True)
    book = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    units = Column(Float, nullable=False, default=0.0)
    confidence = Column(String, nullable=False, default="none")
    recommended = Column(Boolean, nullable=False, default=False, index=True)
    ev = Column(Float, nullable=False)
    p_win = Column(Float, nullable=False)
    p_push = Column(Float, nullable=False, default=0.0)
    model_prob = Column(Float, nullable=True)
    market_prob = Column(Float, nullable=True)
    projection = Column(Float, nullable=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    status = Column(String, nullable=False, default="pending", index=True)  # pending|won|lost|push|void
    actual = Column(Float, nullable=True)        # real stat / margin / total it was graded on
    profit_units = Column(Float, nullable=True)  # units won (+) or lost (-); 0 for push/void/no-bet
    graded_at = Column(DateTime(timezone=True), nullable=True)
