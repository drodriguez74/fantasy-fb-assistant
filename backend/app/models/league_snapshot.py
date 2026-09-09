from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base


class LeagueSnapshot(Base):
    """A cached JSON payload for one expensive per-league read.

    Endpoints that hit slow live ESPN/Yahoo APIs (This Week, roster
    analysis, standings) persist their last-computed response here so the
    next page load can render instantly from the DB while a background task
    refreshes the row. See app.services.snapshot_cache for the
    stale-while-revalidate logic.

    One row per (user_league_id, kind). `payload` is the endpoint's normal
    response body serialized as JSON text (same rationale as
    UserLeague.roster_positions/scoring_rules -- read as a whole, never
    queried by inner field).
    """

    __tablename__ = "league_snapshots"
    __table_args__ = (
        UniqueConstraint("user_league_id", "kind", name="uq_league_snapshot_league_kind"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_league_id = Column(
        Integer, ForeignKey("user_leagues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String, nullable=False)  # "this_week" | "roster_analysis" | "standings"
    payload = Column(Text, nullable=False)  # JSON

    computed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
