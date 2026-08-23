from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum


class Position(enum.Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DEF = "DEF"


class InjuryStatus(enum.Enum):
    HEALTHY = "Healthy"
    QUESTIONABLE = "Questionable" 
    DOUBTFUL = "Doubtful"
    OUT = "Out"
    IR = "IR"
    PUP = "PUP"
    SUSPENDED = "Suspended"


class RiskLevel(enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    first_name = Column(String)
    last_name = Column(String)
    team = Column(String, nullable=False, index=True)
    position = Column(Enum(Position, name='player_position'), nullable=False)
    
    # External IDs
    espn_id = Column(String, unique=True, index=True)
    yahoo_id = Column(String, unique=True, index=True)
    sleeper_id = Column(String, unique=True, index=True)
    
    # Basic Info
    age = Column(Integer)
    height = Column(String)  # e.g., "6'0"
    weight = Column(Integer)
    college = Column(String)
    years_exp = Column(Integer)
    jersey_number = Column(Integer)
    
    # Fantasy Metrics
    projected_points = Column(Float)
    projected_points_half_ppr = Column(Float)
    projected_points_standard = Column(Float)
    adp = Column(Float)  # Average Draft Position
    adp_trend = Column(Float)  # Weekly ADP change
    ownership_percentage = Column(Float)
    
    # Advanced Analytics
    target_share = Column(Float)  # For WR/TE
    air_yards_share = Column(Float)  # For WR/TE  
    red_zone_targets = Column(Integer)  # For WR/TE
    carries_share = Column(Float)  # For RB
    snap_count_percentage = Column(Float)
    
    # Performance Metrics (current season)
    games_played = Column(Integer)
    games_started = Column(Integer)
    fantasy_points_ppr = Column(Float)
    fantasy_points_half_ppr = Column(Float)
    fantasy_points_standard = Column(Float)
    
    # Position-specific stats (stored as JSON for flexibility)
    season_stats = Column(JSON)  # Current season stats
    last_game_stats = Column(JSON)  # Most recent game
    
    # Team & Schedule Info
    bye_week = Column(Integer)
    depth_chart_order = Column(Integer)
    strength_of_schedule = Column(Float)  # Remaining SOS
    
    # Injury & Status
    injury_status = Column(Enum(InjuryStatus, name='injury_status'), default=InjuryStatus.HEALTHY)
    injury_body_part = Column(String)
    injury_notes = Column(Text)
    injury_updated_at = Column(DateTime(timezone=True))
    practice_status = Column(String)  # Full, Limited, DNP
    
    # Trending & News
    trending_direction = Column(String)  # UP, DOWN, STABLE
    trending_count = Column(Integer)  # Add/drop count
    news_updated_at = Column(DateTime(timezone=True))
    latest_news = Column(Text)
    
    # AI & Analysis
    ai_analysis = Column(Text)
    risk_level = Column(Enum(RiskLevel, name='risk_level'), default=RiskLevel.MEDIUM)
    ceiling_score = Column(Float)  # Best case scenario points
    floor_score = Column(Float)   # Worst case scenario points
    consistency_rating = Column(Float)  # 1-10 consistency score
    
    # Rankings
    position_rank = Column(Integer)  # Overall position rank
    tier = Column(Integer)  # Draft tier (1-8)
    expert_consensus_rank = Column(Integer)
    
    # Flags
    is_rookie = Column(Boolean, default=False)
    is_handcuff = Column(Boolean, default=False)  # Backup to star player
    handcuff_to_player_id = Column(String)  # ID of player this is a handcuff for
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # historical_performances, season_summaries, trends, waiver_recommendations,
    # waiver_trends, evaluations, and waiver_alerts are wired onto this class
    # in app/models/__init__.py (after all models are imported), per this
    # codebase's convention of attaching cross-model relationship()s there
    # rather than inline -- see the comment at the top of that file. Each is
    # back_populates-paired with a `player = relationship("Player", ...)` on
    # the corresponding model in waiver_wire.py / historical_performance.py.

    # game_situations / situational_trends (GameSituation / SituationalTrend,
    # defined in app/models/game_situation.py) are NOT wired the same way yet.
    # That file's `player = relationship("Player")` on both classes has no
    # back_populates, so pairing it from this side needs a matching one-line
    # change in game_situation.py too (out of scope for this pass) to avoid
    # SQLAlchemy's overlapping-relationship warning. Not a circular-import or
    # mapper-configuration failure -- just needs that one coordinated edit.