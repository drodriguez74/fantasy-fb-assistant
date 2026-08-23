"""
Waiver Wire Models

Database models for waiver wire recommendations, player evaluations, and weekly analysis.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.db.base import Base


class RecommendationType(enum.Enum):
    ADD = "add"
    DROP = "drop"
    STASH = "stash"
    AVOID = "avoid"


class Priority(enum.Enum):
    URGENT = "urgent"      # Must pick up immediately (injury replacement, breakout)
    HIGH = "high"          # Strong recommendation 
    MEDIUM = "medium"      # Solid option
    LOW = "low"           # Speculative add
    WATCH = "watch"       # Monitor for future weeks


class WaiverWireRecommendation(Base):
    """Individual waiver wire recommendations for players"""
    __tablename__ = "waiver_wire_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    
    # Recommendation details
    recommendation_type = Column(Enum(RecommendationType), nullable=False)
    priority = Column(Enum(Priority), nullable=False)
    confidence_score = Column(Float, nullable=False)  # 0.0 to 1.0
    
    # Analysis
    reason = Column(Text, nullable=False)
    projected_points = Column(Float)
    ownership_percentage = Column(Float)
    trend_direction = Column(String(10))  # up, down, stable
    
    # Context
    injury_related = Column(Boolean, default=False)
    matchup_driven = Column(Boolean, default=False)
    target_share_increase = Column(Boolean, default=False)
    volume_increase = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    player = relationship("Player", back_populates="waiver_recommendations")


class WaiverWireTrend(Base):
    """Track trending players and movement patterns"""
    __tablename__ = "waiver_wire_trends"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    
    # Trend metrics
    ownership_change = Column(Float, nullable=False)  # Weekly change in ownership %
    pickup_rate = Column(Float, nullable=False)       # % of leagues that picked up
    drop_rate = Column(Float, nullable=False)         # % of leagues that dropped
    
    # Performance context
    recent_performance = Column(Float)  # Last 3 weeks avg
    upcoming_matchup_rating = Column(Float)  # Next 3 weeks difficulty (1-10)
    
    # Signals
    target_share_trend = Column(Float)
    snap_count_trend = Column(Float)
    red_zone_trend = Column(Float)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    player = relationship("Player", back_populates="waiver_trends")


class PlayerEvaluation(Base):
    """Weekly player evaluations for waiver wire analysis"""
    __tablename__ = "player_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    
    # Core metrics
    projected_points = Column(Float, nullable=False)
    floor_projection = Column(Float, nullable=False)
    ceiling_projection = Column(Float, nullable=False)
    
    # Opportunity metrics
    target_share = Column(Float)
    snap_percentage = Column(Float)
    red_zone_opportunities = Column(Integer)
    goal_line_carries = Column(Integer)
    
    # Matchup analysis
    matchup_rating = Column(Float)  # 1-10 scale (10 = best matchup)
    opposing_defense_rank = Column(Integer)
    home_away = Column(String(4))  # "home" or "away"
    
    # Situation
    injury_report_status = Column(String(20))
    weather_concerns = Column(Boolean, default=False)
    game_script_favorable = Column(Boolean, default=False)
    
    # Trends (last 3 weeks)
    performance_trend = Column(Float)  # Points per game trend
    usage_trend = Column(Float)        # Target/carry trend
    efficiency_trend = Column(Float)   # Y/target, Y/carry trend
    
    # AI insights
    breakout_probability = Column(Float, default=0.0)
    bust_probability = Column(Float, default=0.0)
    consistency_score = Column(Float, default=0.0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    player = relationship("Player", back_populates="evaluations")


class WaiverWireAlert(Base):
    """Time-sensitive alerts for waiver wire activity"""
    __tablename__ = "waiver_wire_alerts"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    
    # Alert details
    alert_type = Column(String(50), nullable=False)  # "injury_replacement", "breakout", "matchup", etc.
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    urgency = Column(Enum(Priority), nullable=False)
    
    # Timing
    expires_at = Column(DateTime)  # When alert becomes irrelevant
    is_active = Column(Boolean, default=True)
    
    # Context
    trigger_event = Column(String(100))  # What caused the alert
    ownership_threshold = Column(Float)   # Don't alert if owned > this %
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime)
    
    # Relationships
    player = relationship("Player", back_populates="waiver_alerts")


# The reverse (Player -> these models) relationships are wired in
# app/models/__init__.py, following this codebase's convention of attaching
# cross-model relationship()s there after all models are imported (see the
# comment at the top of that file). Player.waiver_recommendations,
# Player.waiver_trends, Player.evaluations, and Player.waiver_alerts are all
# defined there with back_populates="player" matching the relationships above.