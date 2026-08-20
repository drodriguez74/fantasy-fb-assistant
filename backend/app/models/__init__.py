# Import all models to ensure they are registered with SQLAlchemy
from app.db.base import Base
from app.models.user import User
from app.models.user_league import UserLeague
from app.models.draft_session import DraftSession
from app.models.player import Player
from app.models.blog_post import BlogPost
from app.models.game_situation import GameSituation, DefensiveRanking, VenueData, WeatherHistory, SituationalTrend

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
    "GameSituation", "DefensiveRanking", "VenueData", "WeatherHistory", "SituationalTrend"
]