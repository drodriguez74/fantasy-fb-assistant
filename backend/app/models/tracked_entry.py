from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class TrackedEntry(Base):
    """A PrizePicks ticket the app itself suggested (tracked_entries.py):
    a 2-pick pair, a 3-6 pick Power/Flex entry, or the "Most likely to win"
    safest pair. Frozen the first time it was shown (one row per season,
    week and ticket signature) and graded with PrizePicks' rules, so the
    suggestions have an auditable record like the board's single picks.

    `legs` is a JSON list of {player, team, game, market, side, line,
    odds_type, p_win, status, actual}. `payouts` is the payout table it was
    priced with ({hits: multiplier}); None when the ticket holds a goblin or
    demon, whose payouts aren't known in advance -- those grade hit/miss only.
    """

    __tablename__ = "tracked_entries"
    __table_args__ = (UniqueConstraint("season", "week", "signature", name="uq_tracked_entry"),)

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, nullable=False, index=True)
    week = Column(Integer, nullable=False, index=True)
    signature = Column(String, nullable=False)
    source = Column(String, nullable=False)              # "pair" | "entry" | "safest_pair"
    entry_type = Column(String, nullable=False)          # "power" | "flex"
    size = Column(Integer, nullable=False)
    legs = Column(JSON, nullable=False)
    p_all = Column(Float, nullable=True)                 # predicted P(every pick hits)
    ev = Column(Float, nullable=True)                    # predicted EV per unit staked; None if payouts unknown
    payouts = Column(JSON, nullable=True)
    has_specials = Column(Boolean, nullable=False, default=False)  # goblin/demon legs (payout unknown)
    engine_version = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="pending", index=True)  # pending|won|lost|partial|refunded
    payout_mult = Column(Float, nullable=True)           # what 1 unit returned (None when payouts unknown)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    graded_at = Column(DateTime(timezone=True), nullable=True)
