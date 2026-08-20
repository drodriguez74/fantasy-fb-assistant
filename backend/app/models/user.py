from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    
    # Profile information
    avatar_url = Column(String)
    bio = Column(Text)
    timezone = Column(String, default="UTC")
    
    # Fantasy preferences
    preferred_scoring = Column(String, default="PPR")  # PPR, Half-PPR, Standard
    favorite_teams = Column(JSON)  # List of NFL team abbreviations
    notifications_enabled = Column(Boolean, default=True)
    
    # Authentication tracking
    last_login = Column(DateTime(timezone=True))
    login_count = Column(Integer, default=0)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships (will be set up after all models are imported)