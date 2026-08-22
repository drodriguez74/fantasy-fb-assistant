from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum
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
    
    # User role and status
    is_commissioner = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Settings
    enable_notifications = Column(Boolean, default=True)
    auto_draft_assistant = Column(Boolean, default=True)
    
    # ESPN-specific authentication (for private leagues)
    espn_swid = Column(String)  # ESPN SWID cookie
    espn_s2 = Column(String)    # ESPN espn_s2 cookie

    # Yahoo-specific authentication (OAuth2 -- unlike ESPN's long-lived
    # cookies, Yahoo access tokens expire quickly, so we persist the refresh
    # token too and track expiry explicitly rather than assuming validity)
    yahoo_access_token = Column(String)
    yahoo_refresh_token = Column(String)
    yahoo_token_expires_at = Column(DateTime(timezone=True))

    # Timestamps
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    last_synced = Column(DateTime(timezone=True))
    
    # Relationships (will be set up after all models are imported)
    
    # Composite unique constraint
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )