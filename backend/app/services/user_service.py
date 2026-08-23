from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.models.user_league import UserLeague, PlatformType
from app.models.draft_session import DraftSession


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return self.db.query(User).filter(User.email == email).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self.db.query(User).filter(User.username == username).first()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        return self.db.query(User).filter(User.id == user_id).first()

    def create_user(self, 
                   email: str, 
                   username: str, 
                   password: str, 
                   full_name: str = None) -> User:
        """Create a new user"""
        hashed_password = get_password_hash(password)
        
        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            full_name=full_name,
            is_active=True,
            is_verified=False  # Require email verification
        )
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email/username and password"""
        # Try to find user by email first, then by username
        user = self.get_user_by_email(email)
        if not user:
            user = self.get_user_by_username(email)  # email param can be username
        if not user:
            return None
        
        # Check account lockout
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            return None
        
        if not verify_password(password, user.hashed_password):
            # Increment failed attempts
            user.failed_login_attempts += 1
            
            # Lock account after 5 failed attempts
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            
            self.db.commit()
            return None
        
        # Successful login - reset failed attempts and update login info
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = datetime.now(timezone.utc)
        user.login_count += 1
        self.db.commit()
        
        return user

    def update_user_profile(self, 
                           user_id: int, 
                           profile_data: Dict[str, Any]) -> Optional[User]:
        """Update user profile information"""
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        
        # Update allowed fields
        allowed_fields = [
            'full_name', 'bio', 'timezone', 'avatar_url',
            'preferred_scoring', 'favorite_teams', 'notifications_enabled'
        ]
        
        for field, value in profile_data.items():
            if field in allowed_fields and hasattr(user, field):
                setattr(user, field, value)
        
        user.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(user)
        return user

    def change_password(self, user_id: int, 
                       current_password: str, 
                       new_password: str) -> bool:
        """Change user password"""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        
        if not verify_password(current_password, user.hashed_password):
            return False
        
        user.hashed_password = get_password_hash(new_password)
        user.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    def reset_password(self, email: str, new_password: str) -> bool:
        """Reset user password (used with reset token)"""
        user = self.get_user_by_email(email)
        if not user:
            return False
        
        user.hashed_password = get_password_hash(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    def verify_email(self, email: str) -> bool:
        """Verify user email address"""
        user = self.get_user_by_email(email)
        if not user:
            return False
        
        user.is_verified = True
        user.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate user account"""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        
        user.is_active = False
        user.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    # League management methods
    def add_user_league(self, 
                       user_id: int,
                       platform: str,
                       league_id: str,
                       league_data: Dict[str, Any]) -> Optional[UserLeague]:
        """Add a league to user's profile"""
        try:
            platform_enum = PlatformType(platform.lower())
        except ValueError:
            return None
        
        # Check if league already exists
        existing = self.db.query(UserLeague).filter(
            UserLeague.user_id == user_id,
            UserLeague.platform == platform_enum,
            UserLeague.league_id == league_id
        ).first()

        if existing:
            # A reconnect needs to actually refresh the stored row -- e.g.
            # corrected ESPN cookies, a team_id that wasn't captured on the
            # first attempt, a league that rolled over to a new season --
            # rather than silently no-op and return stale data, which used
            # to happen for every platform except Yahoo (whose short-lived
            # access tokens forced a narrower fix here first). Only
            # overwrite a field when the caller supplied a real (non-None)
            # value -- some call sites (e.g. ESPN connect before the user
            # has picked their team from GET /espn/teams) always pass
            # `team_id` as a dict key even when it's None, and a reconnect
            # in that state must not blank out a team_id a previous, more
            # complete connect call already set.
            updatable_fields = (
                'league_name', 'league_key', 'season', 'scoring_format',
                'league_size', 'team_id', 'is_commissioner',
                'espn_swid', 'espn_s2',
                'yahoo_access_token', 'yahoo_refresh_token', 'yahoo_token_expires_at',
            )
            for field in updatable_fields:
                if league_data.get(field) is not None:
                    setattr(existing, field, league_data[field])
            self.db.commit()
            self.db.refresh(existing)
            return existing

        user_league = UserLeague(
            user_id=user_id,
            platform=platform_enum,
            league_id=league_id,
            league_key=league_data.get('league_key'),
            team_id=league_data.get('team_id'),
            league_name=league_data.get('league_name'),
            season=league_data.get('season', 2024),
            scoring_format=league_data.get('scoring_format'),
            league_size=league_data.get('league_size'),
            is_commissioner=league_data.get('is_commissioner', False),
            espn_swid=league_data.get('espn_swid'),
            espn_s2=league_data.get('espn_s2'),
            yahoo_access_token=league_data.get('yahoo_access_token'),
            yahoo_refresh_token=league_data.get('yahoo_refresh_token'),
            yahoo_token_expires_at=league_data.get('yahoo_token_expires_at')
        )

        self.db.add(user_league)
        self.db.commit()
        self.db.refresh(user_league)
        return user_league

    def get_user_league(self, user_id: int, league_id: int) -> Optional[UserLeague]:
        """Get a single league by its UserLeague row id, scoped to the owning user"""
        return self.db.query(UserLeague).filter(
            UserLeague.user_id == user_id,
            UserLeague.id == league_id
        ).first()

    def get_user_league_by_platform_id(self, user_id: int, platform: str, league_id: str) -> Optional[UserLeague]:
        """Get a user's league by platform + the platform's own external
        league_id string, as opposed to get_user_league (which looks up by
        this table's own row id). Used by callers -- e.g. starting a live
        draft session -- that only have the external id the platform uses,
        not the internal UserLeague row id.
        """
        try:
            platform_enum = PlatformType(platform.lower())
        except ValueError:
            return None

        return self.db.query(UserLeague).filter(
            UserLeague.user_id == user_id,
            UserLeague.platform == platform_enum,
            UserLeague.league_id == str(league_id),
            UserLeague.is_active == True
        ).first()

    def get_user_leagues(self, user_id: int) -> List[UserLeague]:
        """Get all leagues for a user"""
        return self.db.query(UserLeague).filter(
            UserLeague.user_id == user_id,
            UserLeague.is_active == True
        ).all()

    def remove_user_league(self, user_id: int, league_id: int) -> bool:
        """Remove a league from user's profile"""
        user_league = self.db.query(UserLeague).filter(
            UserLeague.user_id == user_id,
            UserLeague.id == league_id
        ).first()
        
        if not user_league:
            return False
        
        user_league.is_active = False
        self.db.commit()
        return True

    # Draft session management
    def create_draft_session(self, 
                           user_id: int,
                           session_data: Dict[str, Any]) -> DraftSession:
        """Create a new draft session"""
        draft_session = DraftSession(
            user_id=user_id,
            session_id=session_data['session_id'],
            platform=session_data['platform'],
            league_id=session_data['league_id'],
            user_team_id=session_data.get('user_team_id'),
            draft_settings=session_data.get('draft_settings', {})
        )
        
        self.db.add(draft_session)
        self.db.commit()
        self.db.refresh(draft_session)
        return draft_session

    def update_draft_session(self, 
                           session_id: str,
                           update_data: Dict[str, Any]) -> Optional[DraftSession]:
        """Update draft session data"""
        session = self.db.query(DraftSession).filter(
            DraftSession.session_id == session_id
        ).first()
        
        if not session:
            return None
        
        for field, value in update_data.items():
            if hasattr(session, field):
                setattr(session, field, value)
        
        session.last_activity = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_user_draft_sessions(self, user_id: int, limit: int = 10) -> List[DraftSession]:
        """Get user's recent draft sessions"""
        return self.db.query(DraftSession).filter(
            DraftSession.user_id == user_id
        ).order_by(DraftSession.started_at.desc()).limit(limit).all()

    def get_draft_session_by_session_id(self, session_id: str) -> Optional[DraftSession]:
        """Get a single draft session by its (string) session_id, regardless of owner.

        Callers that need to scope this to the requesting user (e.g. the
        GET /users/me/drafts/{session_id} endpoint) must check
        `session.user_id` themselves after calling this.
        """
        return self.db.query(DraftSession).filter(
            DraftSession.session_id == session_id
        ).first()

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get user statistics"""
        user = self.get_user_by_id(user_id)
        if not user:
            return {}
        
        total_leagues = self.db.query(UserLeague).filter(
            UserLeague.user_id == user_id,
            UserLeague.is_active == True
        ).count()
        
        total_drafts = self.db.query(DraftSession).filter(
            DraftSession.user_id == user_id
        ).count()
        
        completed_drafts = self.db.query(DraftSession).filter(
            DraftSession.user_id == user_id,
            DraftSession.is_completed == True
        ).count()
        
        return {
            'total_leagues': total_leagues,
            'total_drafts': total_drafts,
            'completed_drafts': completed_drafts,
            'member_since': user.created_at,
            'last_login': user.last_login
        }