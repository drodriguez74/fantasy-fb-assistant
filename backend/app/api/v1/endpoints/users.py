from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_active_user, get_current_verified_user
from app.services.user_service import UserService
from app.schemas.user import (
    UserUpdate, UserResponse, UserStats, LeagueAdd, UserLeagueResponse,
    UserPublic
)
from app.schemas.draft_session import (
    DraftSessionListResponse, DraftSessionSummary, DraftSessionDetail
)
from app.models.user import User

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: User = Depends(get_current_active_user)):
    """Get current user's profile"""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_my_profile(
    profile_data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile"""
    user_service = UserService(db)
    
    # Convert Pydantic model to dict, excluding None values
    update_data = profile_data.dict(exclude_unset=True)
    
    user = user_service.update_user_profile(
        user_id=current_user.id,
        profile_data=update_data
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


@router.get("/me/stats", response_model=UserStats)
async def get_my_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get current user's statistics"""
    user_service = UserService(db)
    
    stats = user_service.get_user_stats(current_user.id)
    
    return stats


@router.delete("/me")
async def deactivate_my_account(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Deactivate current user's account"""
    user_service = UserService(db)
    
    success = user_service.deactivate_user(current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate account"
        )
    
    return {"message": "Account deactivated successfully"}


# League Management
@router.post("/me/leagues", response_model=UserLeagueResponse)
async def add_league(
    league_data: LeagueAdd,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """Add a fantasy league to user's profile"""
    user_service = UserService(db)
    
    # Prepare league data
    league_info = {
        'league_key': league_data.league_key,
        'team_id': league_data.team_id,
        'league_name': league_data.league_name,
        'season': league_data.season,
        'scoring_format': league_data.scoring_format,
        'league_size': league_data.league_size,
        'is_commissioner': league_data.is_commissioner
    }
    
    user_league = user_service.add_user_league(
        user_id=current_user.id,
        platform=league_data.platform,
        league_id=league_data.league_id,
        league_data=league_info
    )
    
    if not user_league:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid platform or league already exists"
        )
    
    return user_league


@router.get("/me/leagues", response_model=List[UserLeagueResponse])
async def get_my_leagues(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all leagues for current user"""
    user_service = UserService(db)
    
    leagues = user_service.get_user_leagues(current_user.id)
    
    return leagues


@router.delete("/me/leagues/{league_id}")
async def remove_league(
    league_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Remove a league from user's profile"""
    user_service = UserService(db)
    
    success = user_service.remove_user_league(
        user_id=current_user.id,
        league_id=league_id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="League not found"
        )
    
    return {"message": "League removed successfully"}


# Draft History
@router.get("/me/drafts", response_model=DraftSessionListResponse)
async def get_my_draft_sessions(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    limit: int = 10
):
    """Get user's recent draft sessions"""
    user_service = UserService(db)

    draft_sessions = user_service.get_user_draft_sessions(
        user_id=current_user.id,
        limit=limit
    )

    return {
        "draft_sessions": draft_sessions,
        "total": len(draft_sessions)
    }


@router.get("/me/drafts/{session_id}", response_model=DraftSessionDetail)
async def get_my_draft_session_detail(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get full detail (including full roster and analysis text) for one past draft session"""
    user_service = UserService(db)

    session = user_service.get_draft_session_by_session_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft session not found"
        )

    # 404 (not 403) on a session that exists but isn't this user's, to avoid
    # leaking whether a given session_id exists at all.
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft session not found"
        )

    return session


# Public Profile (for sharing/social features)
@router.get("/{username}/public", response_model=UserPublic)
async def get_user_public_profile(username: str, db: Session = Depends(get_db)):
    """Get public profile for a user by username"""
    user_service = UserService(db)
    
    user = user_service.get_user_by_username(username)
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


# Admin endpoints (for future use)
@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user by ID (own profile, or any profile if the caller is a superuser)"""
    if current_user.id != user_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this profile"
        )
    
    user_service = UserService(db)
    user = user_service.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user