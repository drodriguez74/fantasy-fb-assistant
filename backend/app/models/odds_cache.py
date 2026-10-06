from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


class OddsCache(Base):
    """Persisted Odds API responses, keyed by request ("games",
    "props:<event_id>", "credits"). The Odds API bills per request, and
    the backend restarts often (Render free tier sleeps when idle), so an
    in-memory cache alone would refetch a full slate of props (~70
    credits) on every cold start. See odds_service.py."""

    __tablename__ = "odds_cache"

    key = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)  # JSON
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
