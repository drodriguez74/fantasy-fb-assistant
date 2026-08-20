#!/usr/bin/env python3

# Simple script to create a test user directly in the database

import sys
import os
sys.path.append('/Users/darwinrodriguez/projects/fantasy-football-assistant/backend')

from app.core.security import get_password_hash
from app.models.user import User
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create database connection
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_test_user():
    db = SessionLocal()
    
    try:
        # Check if user exists
        existing_user = db.query(User).filter(User.email == "demo@test.com").first()
        if existing_user:
            print(f"User already exists: {existing_user.email}")
            return
        
        # Create new user
        hashed_password = get_password_hash("Password123")
        
        user = User(
            email="demo@test.com",
            username="demo",
            hashed_password=hashed_password,
            full_name="Demo User",
            is_active=True,
            is_verified=True
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        print(f"Created user: {user.email} / Password123")
        print(f"User ID: {user.id}")
        
    except Exception as e:
        print(f"Error creating user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_test_user()