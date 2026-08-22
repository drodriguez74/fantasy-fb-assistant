from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum


class PlatformType(enum.Enum):
    SLEEPER = "sleeper"
    ESPN = "espn"
    YAHOO = "yahoo"
    NFL = "nfl"
    CBS = "cbs"


class UserLeague(Base):
    __tablename__ = "user_leagues"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # League identifiers
    platform = Column(Enum(PlatformType), nullable=False)
    league_id = Column(String, nullable=False)  # Platform-specific league ID
    league_key = Column(String)  # Yahoo uses league_key format
    team_id = Column(String)  # User's team ID in the league
    
    # League details
    league_name = Column(String)
    season = Column(Integer, default=2024)
    scoring_format = Column(String)  # PPR, Half-PPR, Standard
    league_size = Column(Integer)

    # Real, granular roster-slot and scoring settings for this league, as
    # extracted by sleeper_service.parse_league_settings /
    # espn_service_enhanced.get_scoring_and_roster_settings -- the draft
    # assistant's roster-needs and value-scoring logic reads these instead
    # of the generic QB1/RB2/WR2/TE1/K1/DEF1/Standard-scoring shape it used
    # to apply to every league (see draft_assistant_service.py's
    # FALLBACK_ROSTER_REQUIREMENTS for what that fallback still looks like
    # when these are null). Stored as a JSON string rather than a
    # normalized table: the shape is read as a whole by the draft
    # assistant, not queried by individual field, and its keys differ by
    # platform (ESPN's real slot labels vs Sleeper's). Schema is additive
    # here; actually populating these at connect-time (leagues.py's
    # /espn/connect, /sleeper equivalents) is a separate follow-up not
    # done in this pass -- the live draft assistant derives this data
    # fresh from the platform on every session instead of depending on it
    # being persisted first.
    roster_positions = Column(Text)  # JSON: {"starters": {...}, "bench": N, "roster_size": N}
    points_per_reception = Column(Float)  # real per-reception scoring value (0.0 / 0.5 / 1.0 / custom)
    
    # User role and status
    is_commissioner = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Settings
    enable_notifications = Column(Boolean, default=True)
    auto_draft_assistant = Column(Boolean, default=True)
    
    # ESPN-specific authentication (for private leagues)
    espn_swid = Column(String)  # ESPN SWID cookie
    espn_s2 = Column(String)    # ESPN espn_s2 cookie
    
    # Timestamps
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    last_synced = Column(DateTime(timezone=True))
    
    # Relationships (will be set up after all models are imported)
    
    # Composite unique constraint
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )