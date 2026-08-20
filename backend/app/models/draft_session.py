from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, JSON, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


class DraftSession(Base):
    __tablename__ = "draft_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Session identifiers
    session_id = Column(String, unique=True, nullable=False, index=True)
    platform = Column(String, nullable=False)  # sleeper, espn, yahoo
    league_id = Column(String, nullable=False)
    user_team_id = Column(String)
    
    # Draft configuration
    draft_settings = Column(JSON)  # Scoring format, league size, etc.
    
    # Session status
    is_active = Column(Boolean, default=True)
    is_completed = Column(Boolean, default=False)
    
    # Draft results
    user_roster = Column(JSON)  # List of drafted players
    draft_grade = Column(String)  # A, B, C, D, F
    final_analysis = Column(Text)  # AI-generated post-draft analysis
    
    # Performance metrics
    recommendations_used = Column(Integer, default=0)
    ai_accuracy_score = Column(Integer)  # How well AI predictions performed
    
    # Timestamps
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    last_activity = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships (will be set up after all models are imported)