from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from app.db.base import Base

# Constants for venue types (using strings instead of enums for now)
VENUE_TYPES = {
    'DOME': "DOME",
    'OUTDOOR': "OUTDOOR", 
    'RETRACTABLE': "RETRACTABLE"
}

WEATHER_CONDITIONS = {
    'CLEAR': "CLEAR",
    'PARTLY_CLOUDY': "PARTLY_CLOUDY",
    'OVERCAST': "OVERCAST",
    'RAIN': "RAIN",
    'SNOW': "SNOW",
    'WIND': "WIND",
    'EXTREME_WEATHER': "EXTREME_WEATHER"
}

GAME_SCRIPTS = {
    'LEADING': "LEADING",
    'TRAILING': "TRAILING",
    'CLOSE': "CLOSE",
    'BLOWOUT_WIN': "BLOWOUT_WIN",
    'BLOWOUT_LOSS': "BLOWOUT_LOSS"
}

class GameSituation(Base):
    """
    Comprehensive game situation data for enhanced analysis
    """
    __tablename__ = "game_situations"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    game_id = Column(String, nullable=False)  # NFL game ID
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    
    # Game context
    is_home_game = Column(Boolean, nullable=False)
    opponent_team = Column(String, nullable=False)
    venue_name = Column(String)
    venue_type = Column(String)  # DOME, OUTDOOR, RETRACTABLE
    
    # Weather data
    temperature = Column(Float)  # Fahrenheit
    humidity = Column(Float)     # Percentage
    wind_speed = Column(Float)   # MPH
    weather_condition = Column(String)  # CLEAR, RAIN, SNOW, etc.
    precipitation = Column(Float)  # Inches
    
    # Game script analysis
    game_script = Column(String)  # LEADING, TRAILING, CLOSE, etc.
    time_of_possession = Column(Float)  # Team's time of possession in minutes
    team_score = Column(Integer)
    opponent_score = Column(Integer)
    point_differential = Column(Integer)  # Team score - opponent score
    
    # Opponent strength metrics
    opponent_def_rank_vs_position = Column(Integer)  # 1-32 ranking
    opponent_def_yards_allowed = Column(Float)
    opponent_def_points_allowed = Column(Float)
    opponent_def_takeaways = Column(Integer)
    
    # Game pace and flow
    total_plays = Column(Integer)
    pace_of_play = Column(Float)  # Plays per minute
    red_zone_visits = Column(Integer)
    third_down_conversions = Column(Integer)
    total_third_downs = Column(Integer)
    
    # Prime time and special situations
    is_prime_time = Column(Boolean, default=False)
    is_division_rival = Column(Boolean, default=False)
    is_playoff_game = Column(Boolean, default=False)
    days_rest = Column(Integer)
    
    # Player performance in this situation
    fantasy_points = Column(Float)
    targets = Column(Integer)
    carries = Column(Integer)
    snaps_played = Column(Integer)
    snap_percentage = Column(Float)
    
    # Advanced situational metrics
    target_share = Column(Float)
    air_yards_share = Column(Float)
    red_zone_targets = Column(Integer)
    goal_line_carries = Column(Integer)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships - temporarily remove back_populates to fix immediate issue
    player = relationship("Player")

class DefensiveRanking(Base):
    """
    Track defensive rankings and metrics for opponent analysis
    """
    __tablename__ = "defensive_rankings"

    id = Column(Integer, primary_key=True, index=True)
    team = Column(String, nullable=False)
    season = Column(Integer, nullable=False)
    week = Column(Integer, nullable=False)
    
    # Overall defensive rankings
    overall_def_rank = Column(Integer)
    points_allowed_rank = Column(Integer)
    yards_allowed_rank = Column(Integer)
    
    # Position-specific rankings
    qb_fantasy_rank = Column(Integer)
    rb_fantasy_rank = Column(Integer)
    wr_fantasy_rank = Column(Integer)
    te_fantasy_rank = Column(Integer)
    
    # Detailed defensive metrics
    pass_def_rank = Column(Integer)
    rush_def_rank = Column(Integer)
    red_zone_def_rank = Column(Integer)
    third_down_def_rank = Column(Integer)
    
    # Fantasy points allowed by position
    qb_points_allowed = Column(Float)
    rb_points_allowed = Column(Float)
    wr_points_allowed = Column(Float)
    te_points_allowed = Column(Float)
    
    # Advanced metrics
    pressure_rate = Column(Float)
    blitz_rate = Column(Float)
    man_coverage_rate = Column(Float)
    zone_coverage_rate = Column(Float)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class VenueData(Base):
    """
    Stadium/venue information for situational analysis
    """
    __tablename__ = "venue_data"

    id = Column(Integer, primary_key=True, index=True)
    venue_name = Column(String, nullable=False, unique=True)
    team = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String)
    
    # Venue characteristics
    venue_type = Column(String, nullable=False)  # DOME, OUTDOOR, RETRACTABLE
    capacity = Column(Integer)
    elevation = Column(Float)  # Feet above sea level
    
    # Climate factors
    avg_temperature = Column(Float)
    avg_humidity = Column(Float)
    avg_wind_speed = Column(Float)
    
    # Playing surface
    surface_type = Column(String)  # Grass, turf, etc.
    
    # Venue-specific fantasy impact
    is_offense_friendly = Column(Boolean, default=True)
    historical_scoring_factor = Column(Float, default=1.0)  # Multiplier vs league average
    
    # Dome/weather protection
    has_retractable_roof = Column(Boolean, default=False)
    typical_weather_impact = Column(String)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class WeatherHistory(Base):
    """
    Historical weather data for game analysis
    """
    __tablename__ = "weather_history"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(String, nullable=False)
    venue_name = Column(String, nullable=False)
    game_date = Column(DateTime, nullable=False)
    
    # Weather measurements
    temperature = Column(Float)
    humidity = Column(Float)
    wind_speed = Column(Float)
    wind_direction = Column(String)
    weather_condition = Column(String)  # CLEAR, RAIN, SNOW, etc.
    precipitation = Column(Float)
    visibility = Column(Float)  # Miles
    
    # Impact assessment
    weather_severity_score = Column(Float)  # 1-10 scale
    expected_fantasy_impact = Column(Float)  # -1 to 1 multiplier

    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SituationalTrend(Base):
    """
    Track player performance trends in specific situations
    """
    __tablename__ = "situational_trends"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    
    # Situation type
    situation_type = Column(String, nullable=False)  # "home_away", "weather", "game_script", etc.
    situation_value = Column(String, nullable=False)  # "HOME", "RAIN", "TRAILING", etc.
    
    # Performance metrics in this situation
    games_played = Column(Integer, default=0)
    avg_fantasy_points = Column(Float, default=0.0)
    total_fantasy_points = Column(Float, default=0.0)
    std_deviation = Column(Float, default=0.0)
    
    # Opportunity metrics
    avg_targets = Column(Float, default=0.0)
    avg_carries = Column(Float, default=0.0)
    avg_snap_percentage = Column(Float, default=0.0)
    
    # Success metrics
    games_over_projection = Column(Integer, default=0)
    boom_games = Column(Integer, default=0)  # Games over 20 points
    bust_games = Column(Integer, default=0)  # Games under 5 points
    
    # Trend indicators
    recent_performance = Column(Float, default=0.0)  # Last 5 games average
    trend_direction = Column(String)  # "UP", "DOWN", "STABLE"
    
    # Statistical confidence
    sample_size_confidence = Column(Float, default=0.0)  # 0-1 scale
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    player = relationship("Player")