from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class UserEntry(Base):
    """A pick'em entry the user actually placed (PrizePicks), logged on the
    Bets page and graded automatically from Sleeper's real stats
    (user_entries.py). `legs` is a JSON list of picks:

        {"player", "team", "market", "side": "More"|"Less", "line",
         "snapshot": {...what our engine said when logged...},
         "status": "pending"|"won"|"lost"|"push"|"void", "actual"}

    The snapshot (books-only and blended hit chance, projections) is what
    lets the record answer "does trusting the projections over the books
    pay?" later.
    """

    __tablename__ = "user_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String, nullable=False, default="prizepicks")
    entry_type = Column(String, nullable=False)          # "power" | "flex"
    stake = Column(Float, nullable=False)
    to_win = Column(Float, nullable=False)               # payout if every pick hits ("$10 to pay $30" -> 30)
    season = Column(Integer, nullable=False, index=True)
    week = Column(Integer, nullable=False, index=True)
    legs = Column(JSON, nullable=False)
    est_hit_prob = Column(Float, nullable=True)          # our P(all hit) when logged (books-only)
    status = Column(String, nullable=False, default="pending", index=True)  # pending|won|lost|partial|refunded
    payout = Column(Float, nullable=True)                # what it actually paid
    notes = Column(String, nullable=True)
    engine_version = Column(String, nullable=True)       # betting_model.ENGINE_VERSION when logged
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    graded_at = Column(DateTime(timezone=True), nullable=True)
