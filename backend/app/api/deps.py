from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core import security
from app.db.base import SessionLocal
from app.models.user import User

security_scheme = HTTPBearer()


def get_db() -> Generator:
    """Dependency to get database session"""
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def get_current_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme)
) -> User:
    """Get current authenticated user"""
    token = credentials.credentials
    
    # Verify token
    user_id = security.verify_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database, create if doesn't exist (for demo mode)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None and str(user_id) == "1":
        # Create demo user for authentication
        try:
            from app.core.security import get_password_hash
            user = User(
                id=1,
                email="demo@test.com",
                username="demo",
                full_name="Demo User", 
                hashed_password=get_password_hash("Password123"),
                is_active=True,
                is_verified=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        except Exception:
            # If database creation fails, use in-memory user object
            user = User(
                id=1,
                email="demo@test.com", 
                username="demo",
                full_name="Demo User",
                is_active=True,
                is_verified=True
            )
    elif user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user (same as get_current_user for now)"""
    return current_user


def get_current_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current verified user"""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not verified"
        )
    return current_user


def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current superuser"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough permissions"
        )
    return current_user


def get_optional_current_user(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None"""
    if credentials is None:
        return None
    
    try:
        token = credentials.credentials
        user_id = security.verify_token(token)
        if user_id is None:
            return None
        
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or not user.is_active:
            return None
        
        return user
    except Exception:
        return None