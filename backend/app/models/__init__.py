# Import all models to ensure they are registered with SQLAlchemy. A model
# class not imported here is invisible to Base.metadata, which means Alembic
# autogenerate sees its table as "not part of the app" and will generate a
# migration to DROP it even though the table is live and in use (this bit us:
# waiver_wire/historical_performance/league_scoring/nfl_schedule tables were
# all missing from here despite being actively queried elsewhere).
from app.db.base import Base
from app.models.user import User
from app.models.user_league import UserLeague
from app.models.draft_session import DraftSession
from app.models.player import Player
from app.models.blog_post import BlogPost
from app.models.game_situation import GameSituation, DefensiveRanking, VenueData, WeatherHistory, SituationalTrend
from app.models.waiver_wire import WaiverWireRecommendation, WaiverWireTrend, PlayerEvaluation, WaiverWireAlert
from app.models.historical_performance import (
    PlayerHistoricalPerformance, PlayerSeasonSummary, MatchupHistory, PlayerTrend, FantasyLeagueHistory
)
from app.models.league_scoring import LeagueScoring, ScoringPreset, PlayerScoringCalculation
from app.models.nfl_schedule import NFLGame, NFLTeam, DefensiveMatchupRanking, TeamMatchupStrength

# Set up relationships after all models are imported
from sqlalchemy.orm import relationship

# Add relationships to User model
User.leagues = relationship("UserLeague", back_populates="user", cascade="all, delete-orphan")
User.draft_sessions = relationship("DraftSession", back_populates="user", cascade="all, delete-orphan")

# Add relationships to UserLeague model
UserLeague.user = relationship("User", back_populates="leagues")

# Add relationships to DraftSession model
DraftSession.user = relationship("User", back_populates="draft_sessions")

__all__ = [
    "Base", "User", "UserLeague", "DraftSession", "Player", "BlogPost",
    "GameSituation", "DefensiveRanking", "VenueData", "WeatherHistory", "SituationalTrend",
    "WaiverWireRecommendation", "WaiverWireTrend", "PlayerEvaluation", "WaiverWireAlert",
    "PlayerHistoricalPerformance", "PlayerSeasonSummary", "MatchupHistory", "PlayerTrend", "FantasyLeagueHistory",
    "LeagueScoring", "ScoringPreset", "PlayerScoringCalculation",
    "NFLGame", "NFLTeam", "DefensiveMatchupRanking", "TeamMatchupStrength",
]