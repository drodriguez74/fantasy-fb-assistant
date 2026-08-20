import asyncio
from sqlalchemy.orm import Session
from app.db.base import SessionLocal, engine
from app.models import User, UserLeague, DraftSession, Player, BlogPost
from app.core.security import get_password_hash
from app.models.user_league import PlatformType
from app.models.player import Position
import json
from datetime import datetime


def init_db() -> None:
    """Initialize database with tables and initial data"""
    # Import all models to ensure they are registered
    from app.models import Base
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Create initial data
    create_initial_data()


def create_initial_data() -> None:
    """Create initial data for development"""
    db = SessionLocal()
    
    try:
        # Check if superuser already exists
        superuser = db.query(User).filter(User.email == "admin@fantasyfootball.com").first()
        if not superuser:
            # Create superuser
            superuser = User(
                email="admin@fantasyfootball.com",
                username="admin",
                hashed_password=get_password_hash("admin123"),
                full_name="System Administrator",
                is_active=True,
                is_verified=True,
                is_superuser=True,
                is_premium=True
            )
            db.add(superuser)
            print("✅ Created superuser: admin@fantasyfootball.com / admin123")
        
        # Create test user
        test_user = db.query(User).filter(User.email == "test@example.com").first()
        if not test_user:
            test_user = User(
                email="test@example.com",
                username="testuser",
                hashed_password=get_password_hash("password123"),
                full_name="Test User",
                is_active=True,
                is_verified=True,
                preferred_scoring="PPR",
                favorite_teams=["BUF", "KC", "SF"],
                notifications_enabled=True
            )
            db.add(test_user)
            print("✅ Created test user: test@example.com / password123")
        
        db.commit()
        
        # Add sample league for test user
        if test_user and not test_user.leagues:
            sample_league = UserLeague(
                user_id=test_user.id,
                platform=PlatformType.ESPN,
                league_id="123456",
                team_id="1",
                league_name="Test Championship League",
                season=2024,
                scoring_format="PPR",
                league_size=12,
                is_commissioner=False,
                enable_notifications=True,
                auto_draft_assistant=True
            )
            db.add(sample_league)
            print("✅ Created sample league for test user")
        
        # Add sample players
        sample_players = [
            {
                "name": "Josh Allen",
                "team": "BUF",
                "position": Position.QB,
                "projected_points": 24.5,
                "adp": 3.2,
                "bye_week": 12,
                "injury_status": "Healthy",
                "risk_level": "LOW"
            },
            {
                "name": "Christian McCaffrey",
                "team": "SF",
                "position": Position.RB,
                "projected_points": 22.1,
                "adp": 1.1,
                "bye_week": 9,
                "injury_status": "Healthy",
                "risk_level": "LOW"
            },
            {
                "name": "Tyreek Hill",
                "team": "MIA",
                "position": Position.WR,
                "projected_points": 18.7,
                "adp": 5.3,
                "bye_week": 6,
                "injury_status": "Healthy",
                "risk_level": "MEDIUM"
            },
            {
                "name": "Travis Kelce",
                "team": "KC",
                "position": Position.TE,
                "projected_points": 15.2,
                "adp": 12.4,
                "bye_week": 10,
                "injury_status": "Healthy",
                "risk_level": "LOW"
            }
        ]
        
        for player_data in sample_players:
            existing_player = db.query(Player).filter(Player.name == player_data["name"]).first()
            if not existing_player:
                player = Player(**player_data)
                db.add(player)
        
        print("✅ Created sample players")
        
        # Add sample blog post
        existing_post = db.query(BlogPost).filter(BlogPost.title.contains("Week 12 Waiver Wire")).first()
        if not existing_post:
            sample_post = BlogPost(
                title="Week 12 Waiver Wire: Multi-Perspective Analysis",
                slug="week-12-waiver-wire-analysis",
                content="""# Week 12 Waiver Wire Analysis

## Conservative Perspective
Focus on proven players with consistent usage patterns...

## Aggressive Perspective  
Target high-upside players with breakout potential...

## Data-Driven Perspective
Advanced metrics suggest these players are undervalued...

## Consensus Recommendation
Based on all perspectives, here are the top waiver wire targets...
""",
                summary="Multi-perspective analysis of Week 12 waiver wire targets with AI-generated consensus recommendations.",
                source_urls='["https://fantasypros.com", "https://espn.com/fantasy"]',
                perspectives_count=5,
                consensus_score=8,
                tags="waiver wire, week 12, ppr, analysis",
                category="waiver_wire",
                is_published=True,
                publish_date=datetime.utcnow(),
                created_by_ai=True,
                ai_model_used="gpt-4"
            )
            db.add(sample_post)
            print("✅ Created sample blog post")
        
        db.commit()
        print("🎉 Database initialization completed successfully!")
        
    except Exception as e:
        print(f"❌ Error initializing database: {str(e)}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("🚀 Initializing Fantasy Football Assistant database...")
    init_db()