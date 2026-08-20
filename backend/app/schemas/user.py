from typing import Optional, List, Any
from pydantic import BaseModel, EmailStr, validator
from datetime import datetime


# User Registration
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    
    @validator('username')
    def username_alphanumeric(cls, v):
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username must contain only letters, numbers, hyphens, and underscores')
        if len(v) < 3 or len(v) > 20:
            raise ValueError('Username must be between 3 and 20 characters')
        return v
    
    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v


# User Login
class UserLogin(BaseModel):
    email: str  # Can be email or username
    password: str


# User Profile Update
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    timezone: Optional[str] = None
    avatar_url: Optional[str] = None
    preferred_scoring: Optional[str] = None
    favorite_teams: Optional[List[str]] = None
    notifications_enabled: Optional[bool] = None


# Password Change
class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    
    @validator('new_password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v


# Password Reset Request
class PasswordResetRequest(BaseModel):
    email: EmailStr


# Password Reset Confirm
class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
    
    @validator('new_password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v


# Email Verification
class EmailVerification(BaseModel):
    token: str


# User Response Schema
class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    is_premium: bool
    avatar_url: Optional[str]
    bio: Optional[str]
    timezone: str
    preferred_scoring: str
    favorite_teams: Optional[List[str]]
    notifications_enabled: bool
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True


# User Public Profile (limited info)
class UserPublic(BaseModel):
    id: int
    username: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    bio: Optional[str]
    is_premium: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# Authentication Token Response
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


# Token Refresh
class TokenRefresh(BaseModel):
    refresh_token: str


# User Statistics
class UserStats(BaseModel):
    total_leagues: int
    total_drafts: int
    completed_drafts: int
    member_since: datetime
    last_login: Optional[datetime]
    is_premium: bool


# League Addition
class LeagueAdd(BaseModel):
    platform: str  # sleeper, espn, yahoo
    league_id: str
    league_key: Optional[str] = None  # For Yahoo
    team_id: Optional[str] = None
    league_name: Optional[str] = None
    season: Optional[int] = 2024
    scoring_format: Optional[str] = None
    league_size: Optional[int] = None
    is_commissioner: Optional[bool] = False


# User League Create
class UserLeagueCreate(BaseModel):
    platform: str
    league_id: str
    league_key: Optional[str] = None
    team_id: Optional[str] = None
    league_name: Optional[str] = None
    season: int = 2024
    scoring_format: Optional[str] = None
    league_size: Optional[int] = None
    is_commissioner: bool = False
    is_active: bool = True
    enable_notifications: bool = True
    auto_draft_assistant: bool = True
    espn_swid: Optional[str] = None
    espn_s2: Optional[str] = None


# User League Response
class UserLeagueResponse(BaseModel):
    id: int
    platform: str
    league_id: str
    league_key: Optional[str]
    team_id: Optional[str]
    league_name: Optional[str]
    season: int
    scoring_format: Optional[str]
    league_size: Optional[int]
    is_commissioner: bool
    is_active: bool
    added_at: datetime
    last_synced: Optional[datetime]
    espn_swid: Optional[str] = None
    espn_s2: Optional[str] = None
    
    class Config:
        from_attributes = True