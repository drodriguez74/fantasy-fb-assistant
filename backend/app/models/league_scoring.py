"""
League Scoring Configuration Models

Handles custom scoring settings, bonuses, and league-specific rules.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from app.db.base import Base
from datetime import datetime
from sqlalchemy import DateTime, Enum
import enum


class ScoringType(enum.Enum):
    PPR = "PPR"
    HALF_PPR = "Half_PPR"
    STANDARD = "Standard"
    CUSTOM = "Custom"


class LeagueScoring(Base):
    """Comprehensive league scoring configuration"""
    __tablename__ = "league_scoring"

    id = Column(Integer, primary_key=True, index=True)
    user_league_id = Column(Integer, ForeignKey("user_leagues.id"), nullable=False, unique=True)
    
    # Basic scoring type
    scoring_type = Column(Enum(ScoringType), nullable=False, default=ScoringType.PPR)
    
    # Passing scoring
    passing_yards_per_point = Column(Float, default=25.0)  # 1 point per 25 yards
    passing_td_points = Column(Float, default=4.0)
    passing_int_points = Column(Float, default=-1.0)
    passing_2pt_points = Column(Float, default=2.0)
    
    # Passing bonuses
    passing_300_yard_bonus = Column(Float, default=0.0)
    passing_400_yard_bonus = Column(Float, default=0.0)
    passing_40_yard_td_bonus = Column(Float, default=0.0)
    
    # Rushing scoring
    rushing_yards_per_point = Column(Float, default=10.0)  # 1 point per 10 yards
    rushing_td_points = Column(Float, default=6.0)
    rushing_2pt_points = Column(Float, default=2.0)
    
    # Rushing bonuses
    rushing_100_yard_bonus = Column(Float, default=0.0)
    rushing_200_yard_bonus = Column(Float, default=0.0)
    rushing_40_yard_td_bonus = Column(Float, default=0.0)
    
    # Receiving scoring
    receiving_yards_per_point = Column(Float, default=10.0)  # 1 point per 10 yards
    receiving_td_points = Column(Float, default=6.0)
    receiving_2pt_points = Column(Float, default=2.0)
    reception_points = Column(Float, default=1.0)  # PPR value
    
    # Receiving bonuses
    receiving_100_yard_bonus = Column(Float, default=0.0)
    receiving_200_yard_bonus = Column(Float, default=0.0)
    receiving_40_yard_td_bonus = Column(Float, default=0.0)
    
    # Kicking scoring
    fg_0_39_points = Column(Float, default=3.0)
    fg_40_49_points = Column(Float, default=4.0)
    fg_50_plus_points = Column(Float, default=5.0)
    fg_miss_points = Column(Float, default=0.0)
    extra_point_points = Column(Float, default=1.0)
    extra_point_miss_points = Column(Float, default=0.0)
    
    # Defense/Special Teams scoring
    def_sack_points = Column(Float, default=1.0)
    def_int_points = Column(Float, default=2.0)
    def_fumble_rec_points = Column(Float, default=2.0)
    def_td_points = Column(Float, default=6.0)
    def_safety_points = Column(Float, default=2.0)
    def_block_kick_points = Column(Float, default=2.0)
    
    # Defense points allowed scoring
    def_0_points_allowed = Column(Float, default=10.0)
    def_1_6_points_allowed = Column(Float, default=7.0)
    def_7_13_points_allowed = Column(Float, default=4.0)
    def_14_20_points_allowed = Column(Float, default=1.0)
    def_21_27_points_allowed = Column(Float, default=0.0)
    def_28_34_points_allowed = Column(Float, default=-1.0)
    def_35_plus_points_allowed = Column(Float, default=-4.0)
    
    # Penalty scoring
    fumble_lost_points = Column(Float, default=-2.0)
    
    # Advanced scoring options
    target_points = Column(Float, default=0.0)  # Points per target
    carry_points = Column(Float, default=0.0)   # Points per carry
    completion_points = Column(Float, default=0.0)  # Points per completion
    incompletion_points = Column(Float, default=0.0)  # Penalty per incompletion
    
    # Custom rules
    custom_scoring_rules = Column(JSON)  # For league-specific custom rules
    notes = Column(Text)  # Additional scoring notes
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user_league = relationship("UserLeague")


class ScoringPreset(Base):
    """Predefined scoring presets for quick setup"""
    __tablename__ = "scoring_presets"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text)
    scoring_type = Column(Enum(ScoringType), nullable=False)
    
    # Store all scoring settings as JSON for easy application
    scoring_settings = Column(JSON, nullable=False)
    
    # Preset metadata
    is_default = Column(Boolean, default=False)
    popularity_rank = Column(Integer, default=0)
    created_by_platform = Column(String)  # sleeper, espn, yahoo, etc.
    
    created_at = Column(DateTime, default=datetime.utcnow)


class PlayerScoringCalculation(Base):
    """Calculated fantasy points for players based on different scoring systems"""
    __tablename__ = "player_scoring_calculations"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    league_scoring_id = Column(Integer, ForeignKey("league_scoring.id"), nullable=False)
    
    # Time period
    season = Column(Integer, nullable=False)
    week = Column(Integer, nullable=True)  # NULL for season totals
    
    # Raw stats (from historical performance)
    raw_stats = Column(JSON)  # Store original stats
    
    # Calculated fantasy points
    calculated_points = Column(Float, nullable=False)
    points_breakdown = Column(JSON)  # Detailed breakdown of how points were calculated
    
    # Comparison to standard scoring
    ppr_difference = Column(Float)  # Difference from PPR scoring
    standard_difference = Column(Float)  # Difference from Standard scoring
    
    # Metadata
    calculation_date = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    player = relationship("Player")
    league_scoring = relationship("LeagueScoring")


# Update UserLeague model to include scoring relationship
# Add this to user_league.py:
"""
Add to UserLeague class:
    scoring_config = relationship("LeagueScoring", back_populates="user_league", uselist=False)
"""