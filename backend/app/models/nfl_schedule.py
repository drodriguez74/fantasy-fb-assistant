"""
NFL Schedule and Team Data Models

Tracks current season schedules, team stats, and matchup data for
fantasy recommendations.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, JSON, Enum
from sqlalchemy.orm import relationship
from app.db.base import Base
from datetime import datetime
import enum


class GameStatus(enum.Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS" 
    COMPLETED = "COMPLETED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"


class NFLGame(Base):
    """NFL game schedule and results"""
    __tablename__ = "nfl_games"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Game identification
    season = Column(Integer, nullable=False, default=2024)
    week = Column(Integer, nullable=False)
    game_id = Column(String, unique=True, index=True)  # External API game ID
    
    # Teams
    home_team = Column(String, nullable=False, index=True)  # Team abbreviation
    away_team = Column(String, nullable=False, index=True)  # Team abbreviation
    
    # Game details
    game_date = Column(DateTime, nullable=False)
    status = Column(Enum(GameStatus), default=GameStatus.SCHEDULED)
    venue = Column(String)
    
    # Results (if completed)
    home_score = Column(Integer)
    away_score = Column(Integer)
    
    # Fantasy relevant data
    weather_conditions = Column(JSON)  # temp, wind, precipitation
    vegas_line = Column(Float)  # Point spread
    over_under = Column(Float)  # Total points
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NFLTeam(Base):
    """NFL team information and current season stats"""
    __tablename__ = "nfl_teams"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Team identification
    abbreviation = Column(String, unique=True, nullable=False, index=True)  # KC, BUF, etc.
    name = Column(String, nullable=False)  # Kansas City Chiefs
    city = Column(String, nullable=False)  # Kansas City
    
    # Division/Conference
    division = Column(String, nullable=False)  # AFC West
    conference = Column(String, nullable=False)  # AFC
    
    # Current season offensive stats
    season = Column(Integer, default=2024)
    points_per_game = Column(Float)
    yards_per_game = Column(Float)
    passing_yards_per_game = Column(Float)
    rushing_yards_per_game = Column(Float)
    turnovers_per_game = Column(Float)
    
    # Defensive stats
    points_allowed_per_game = Column(Float)
    yards_allowed_per_game = Column(Float)
    passing_yards_allowed_per_game = Column(Float)
    rushing_yards_allowed_per_game = Column(Float)
    takeaways_per_game = Column(Float)
    sacks_per_game = Column(Float)
    
    # Updated tracking
    last_updated = Column(DateTime, default=datetime.utcnow)


class DefensiveMatchupRanking(Base):
    """Weekly defensive rankings vs specific positions"""
    __tablename__ = "defensive_matchup_rankings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Time context
    season = Column(Integer, nullable=False, default=2024)
    week = Column(Integer, nullable=False, index=True)
    
    # Team and position
    team_abbreviation = Column(String, nullable=False, index=True)
    position = Column(String, nullable=False, index=True)  # QB, RB, WR, TE, K, DEF
    
    # Rankings and allowances
    rank_vs_position = Column(Integer, nullable=False)  # 1-32 ranking
    fantasy_points_allowed_avg = Column(Float)  # Season average allowed
    fantasy_points_allowed_last_4 = Column(Float)  # Recent trend
    
    # Advanced metrics
    target_share_allowed = Column(Float)  # For WR/TE
    red_zone_attempts_allowed = Column(Float)  # For RB/WR/TE
    pressure_rate = Column(Float)  # For QB
    
    # Matchup rating
    matchup_rating = Column(Float)  # 1-10 scale (10 = best matchup)
    confidence_score = Column(Float)  # How confident we are in this rating
    
    # Notes
    key_factors = Column(JSON)  # List of factors affecting this matchup
    
    # Metadata
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TeamMatchupStrength(Base):
    """Team offensive strength vs different defensive schemes"""
    __tablename__ = "team_matchup_strength"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Time and team context
    season = Column(Integer, nullable=False, default=2024)
    team_abbreviation = Column(String, nullable=False, index=True)
    
    # Offensive strength by position
    qb_production_rank = Column(Integer)  # 1-32 QB production
    rb_production_rank = Column(Integer)  # 1-32 RB production
    wr_production_rank = Column(Integer)  # 1-32 WR production
    te_production_rank = Column(Integer)  # 1-32 TE production
    
    # Situational strengths
    red_zone_efficiency = Column(Float)  # TD rate in red zone
    third_down_conversion = Column(Float)  # 3rd down conversion rate
    pace_of_play = Column(Float)  # Plays per game
    
    # Advanced metrics
    passing_attack_efficiency = Column(Float)  # EPA per pass
    rushing_attack_efficiency = Column(Float)  # EPA per rush
    
    # Updated tracking
    last_updated = Column(DateTime, default=datetime.utcnow)