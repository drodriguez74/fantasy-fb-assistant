from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from app.db.base import Base
from datetime import datetime
import enum
from sqlalchemy import Enum

class PerformanceType(enum.Enum):
    WEEKLY = "WEEKLY"
    SEASON = "SEASON"
    CAREER = "CAREER"

class GameLocation(enum.Enum):
    HOME = "home"
    AWAY = "away"
    NEUTRAL = "neutral"

class PlayerHistoricalPerformance(Base):
    """Historical performance data for individual players"""
    __tablename__ = "player_historical_performance"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)
    week = Column(Integer, nullable=True, index=True)  # NULL for season-long stats
    game_date = Column(DateTime, nullable=True)
    
    # Game context
    opponent_team = Column(String(10), nullable=True)
    game_location = Column(Enum(GameLocation), nullable=True)
    weather_conditions = Column(String(100), nullable=True)
    game_script = Column(String(50), nullable=True)  # "blowout_win", "close_game", etc.
    
    # Fantasy scoring
    fantasy_points_ppr = Column(Float, nullable=True)
    fantasy_points_half_ppr = Column(Float, nullable=True)
    fantasy_points_standard = Column(Float, nullable=True)
    
    # Basic stats (JSON for flexibility across positions)
    passing_stats = Column(JSON, nullable=True)  # yards, tds, ints, completions, attempts
    rushing_stats = Column(JSON, nullable=True)  # yards, tds, attempts, fumbles
    receiving_stats = Column(JSON, nullable=True)  # yards, tds, receptions, targets
    defensive_stats = Column(JSON, nullable=True)  # sacks, ints, tackles, etc.
    kicking_stats = Column(JSON, nullable=True)  # fg_made, fg_attempted, xp_made, etc.
    
    # Advanced metrics
    snap_count = Column(Integer, nullable=True)
    snap_percentage = Column(Float, nullable=True)
    target_share = Column(Float, nullable=True)
    air_yards = Column(Float, nullable=True)
    red_zone_targets = Column(Integer, nullable=True)
    end_zone_targets = Column(Integer, nullable=True)
    
    # Game flow metrics
    touches_when_ahead = Column(Integer, nullable=True)
    touches_when_behind = Column(Integer, nullable=True)
    fourth_quarter_usage = Column(Float, nullable=True)
    
    # Efficiency metrics
    yards_per_touch = Column(Float, nullable=True)
    yards_after_contact = Column(Float, nullable=True)
    drop_rate = Column(Float, nullable=True)
    
    # Injury/health context
    injury_designation = Column(String(20), nullable=True)
    games_missed_prior = Column(Integer, nullable=True)
    
    # Performance context
    performance_type = Column(Enum(PerformanceType, name='performancetype'), nullable=False, default=PerformanceType.WEEKLY)
    is_playoffs = Column(Boolean, default=False)
    
    # Metadata
    data_source = Column(String(50), nullable=True)  # "sleeper", "yahoo", "manual", etc.
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    player = relationship("Player", back_populates="historical_performances")

class PlayerSeasonSummary(Base):
    """Season-level summary statistics and metrics"""
    __tablename__ = "player_season_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)
    
    # Games played
    games_played = Column(Integer, nullable=False)
    games_started = Column(Integer, nullable=True)
    
    # Fantasy totals
    total_fantasy_points_ppr = Column(Float, nullable=True)
    total_fantasy_points_half_ppr = Column(Float, nullable=True)
    total_fantasy_points_standard = Column(Float, nullable=True)
    
    # Per-game averages
    avg_fantasy_points_ppr = Column(Float, nullable=True)
    avg_fantasy_points_half_ppr = Column(Float, nullable=True)
    avg_fantasy_points_standard = Column(Float, nullable=True)
    
    # Consistency metrics
    weekly_ceiling = Column(Float, nullable=True)  # Best single-week performance
    weekly_floor = Column(Float, nullable=True)    # Worst single-week performance
    consistency_score = Column(Float, nullable=True)  # Coefficient of variation
    boom_weeks = Column(Integer, nullable=True)    # Weeks above 80th percentile
    bust_weeks = Column(Integer, nullable=True)    # Weeks below 20th percentile
    
    # Trend analysis
    first_half_avg = Column(Float, nullable=True)  # Weeks 1-8 average
    second_half_avg = Column(Float, nullable=True) # Weeks 9-17 average
    trend_direction = Column(String(20), nullable=True)  # "improving", "declining", "stable"
    
    # Matchup performance
    vs_top_defenses_avg = Column(Float, nullable=True)  # vs top 10 defenses
    vs_bottom_defenses_avg = Column(Float, nullable=True)  # vs bottom 10 defenses
    home_game_avg = Column(Float, nullable=True)
    away_game_avg = Column(Float, nullable=True)
    
    # Health metrics
    injury_weeks_missed = Column(Integer, nullable=True)
    injury_weeks_limited = Column(Integer, nullable=True)
    health_grade = Column(String(2), nullable=True)  # A-F grade
    
    # Advanced season metrics
    breakout_score = Column(Float, nullable=True)  # Improvement over previous season
    sustainability_score = Column(Float, nullable=True)  # Likelihood to repeat performance
    
    # Rankings
    position_finish = Column(Integer, nullable=True)  # End-of-season position rank
    position_finish_half_season = Column(Integer, nullable=True)  # Mid-season rank
    adp_vs_finish = Column(Float, nullable=True)  # ADP difference from actual finish
    
    # Metadata
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    player = relationship("Player", back_populates="season_summaries")

class MatchupHistory(Base):
    """Historical matchup data between teams and positions"""
    __tablename__ = "matchup_histories"
    
    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, nullable=False, index=True)
    week = Column(Integer, nullable=False, index=True)
    
    # Teams
    team_a = Column(String(10), nullable=False, index=True)
    team_b = Column(String(10), nullable=False, index=True)
    
    # Game details
    game_date = Column(DateTime, nullable=False)
    final_score_a = Column(Integer, nullable=True)
    final_score_b = Column(Integer, nullable=True)
    total_points = Column(Integer, nullable=True)
    game_script = Column(String(50), nullable=True)  # "blowout", "close", "back_and_forth"
    
    # Fantasy impact by position
    qb_fantasy_allowed_a = Column(Float, nullable=True)  # Fantasy points allowed to QBs by team A
    qb_fantasy_allowed_b = Column(Float, nullable=True)
    rb_fantasy_allowed_a = Column(Float, nullable=True)
    rb_fantasy_allowed_b = Column(Float, nullable=True)
    wr_fantasy_allowed_a = Column(Float, nullable=True)
    wr_fantasy_allowed_b = Column(Float, nullable=True)
    te_fantasy_allowed_a = Column(Float, nullable=True)
    te_fantasy_allowed_b = Column(Float, nullable=True)
    
    # Game environment
    weather = Column(String(100), nullable=True)
    temperature = Column(Integer, nullable=True)
    wind_speed = Column(Integer, nullable=True)
    precipitation = Column(String(50), nullable=True)
    dome_game = Column(Boolean, default=False)
    
    # Metadata
    data_source = Column(String(50), nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

class PlayerTrend(Base):
    """Player performance trends and patterns"""
    __tablename__ = "player_trends"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    
    # Trend period
    trend_start_date = Column(DateTime, nullable=False)
    trend_end_date = Column(DateTime, nullable=False)
    trend_type = Column(String(50), nullable=False)  # "season", "4_week", "8_week", "career"
    
    # Performance metrics
    trend_direction = Column(String(20), nullable=False)  # "up", "down", "stable"
    trend_strength = Column(Float, nullable=True)  # -1 to 1 scale
    performance_change = Column(Float, nullable=True)  # % change in fantasy points
    
    # Trend factors
    usage_trend = Column(Float, nullable=True)  # Change in touches/targets
    efficiency_trend = Column(Float, nullable=True)  # Change in yards per touch
    touchdown_trend = Column(Float, nullable=True)  # Change in TD rate
    health_trend = Column(String(20), nullable=True)  # "improving", "declining", "stable"
    
    # Contextual factors
    team_situation_change = Column(Text, nullable=True)  # Coaching, QB, etc. changes
    competition_change = Column(Text, nullable=True)  # Depth chart changes
    schedule_strength_change = Column(Float, nullable=True)  # SOS change
    
    # Predictive metrics
    sustainability_score = Column(Float, nullable=True)  # How likely trend continues
    regression_likelihood = Column(Float, nullable=True)  # Likelihood of mean reversion
    breakout_probability = Column(Float, nullable=True)  # Chance of continued improvement
    
    # Metadata
    confidence_level = Column(Float, nullable=True)  # 0-1 confidence in trend analysis
    sample_size = Column(Integer, nullable=True)  # Number of games in trend
    
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    player = relationship("Player", back_populates="trends")

class FantasyLeagueHistory(Base):
    """Historical league and team performance data"""
    __tablename__ = "fantasy_league_histories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)
    
    # League info
    league_platform = Column(String(20), nullable=False)
    league_external_id = Column(String(100), nullable=False)
    league_name = Column(String(200), nullable=True)
    league_size = Column(Integer, nullable=True)
    scoring_format = Column(String(20), nullable=True)
    
    # Season performance
    regular_season_wins = Column(Integer, nullable=True)
    regular_season_losses = Column(Integer, nullable=True)
    playoff_finish = Column(Integer, nullable=True)  # 1st, 2nd, 3rd, etc.
    total_points_for = Column(Float, nullable=True)
    total_points_against = Column(Float, nullable=True)
    
    # League rankings
    regular_season_rank = Column(Integer, nullable=True)
    points_for_rank = Column(Integer, nullable=True)
    efficiency_rank = Column(Integer, nullable=True)  # Points per game vs optimal lineup
    
    # Draft performance
    draft_grade = Column(String(2), nullable=True)  # A-F
    draft_value_generated = Column(Float, nullable=True)  # ADP vs actual performance
    best_draft_pick = Column(String(100), nullable=True)  # Player name
    worst_draft_pick = Column(String(100), nullable=True)  # Player name
    
    # Season management
    waiver_moves = Column(Integer, nullable=True)
    trades_made = Column(Integer, nullable=True)
    optimal_lineup_percentage = Column(Float, nullable=True)  # % of possible points scored
    
    # Key stats
    highest_weekly_score = Column(Float, nullable=True)
    lowest_weekly_score = Column(Float, nullable=True)
    most_bench_points = Column(Float, nullable=True)  # Worst bench management week
    
    # Metadata
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

# The reverse (Player -> these models) relationships are wired in
# app/models/__init__.py, following this codebase's convention of attaching
# cross-model relationship()s there after all models are imported (see the
# comment at the top of that file). Player.historical_performances,
# Player.season_summaries, and Player.trends are all defined there with
# back_populates="player" matching the relationships above.