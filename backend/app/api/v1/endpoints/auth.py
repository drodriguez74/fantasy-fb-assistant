from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_current_active_user
from app.core import security
from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.services.user_service import UserService
from app.schemas.user import (
    UserCreate, UserLogin, UserResponse, Token, TokenRefresh,
    PasswordResetRequest, PasswordResetConfirm, EmailVerification,
    PasswordChange
)
from app.services.email_service import send_verification_email, send_password_reset_email
from app.models.user import User

router = APIRouter()


def _registration_allowed(email: str) -> bool:
    allowed = (settings.REGISTRATION_ALLOWED_EMAILS or "").strip()
    if not allowed:
        return False
    if allowed == "*":
        return True
    return email.strip().lower() in {e.strip().lower() for e in allowed.split(",") if e.strip()}


@router.post("/register", response_model=UserResponse, dependencies=[Depends(rate_limit("register", 5, 3600))])
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user (only emails in REGISTRATION_ALLOWED_EMAILS)"""
    if not _registration_allowed(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed. Ask the site owner to add your email."
        )

    user_service = UserService(db)
    
    # Check if user already exists
    if user_service.get_user_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    if user_service.get_user_by_username(user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create user directly
    try:
        from app.core.security import get_password_hash
        
        hashed_password = get_password_hash(user_data.password)
        
        user = User(
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_password,
            full_name=user_data.full_name,
            is_active=True,
            is_verified=True  # Skip verification for demo
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        return user
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user account: {str(e)}"
        )


@router.post("/login", response_model=Token, dependencies=[Depends(rate_limit("login", 10, 60))])
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    """Authenticate user and return access token"""
    user_service = UserService(db)
    user = user_service.authenticate_user(user_credentials.email, user_credentials.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )
    refresh_token = security.create_refresh_token(subject=user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user
    }


@router.post("/refresh", response_model=Token, dependencies=[Depends(rate_limit("refresh", 30, 60))])
async def refresh_token(token_data: TokenRefresh, db: Session = Depends(get_db)):
    """Refresh access token using refresh token"""
    user_id = security.verify_refresh_token(token_data.refresh_token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user_service = UserService(db)
    user = user_service.get_user_by_id(int(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new tokens
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )
    new_refresh_token = security.create_refresh_token(subject=user.id)
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user
    }


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """Logout user (client should discard tokens)"""
    # In a more advanced implementation, you might:
    # - Add token to blacklist
    # - Store revoked tokens in Redis
    # - Clear session data
    
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information"""
    return current_user


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Change user password"""
    user_service = UserService(db)
    
    success = user_service.change_password(
        user_id=current_user.id,
        current_password=password_data.current_password,
        new_password=password_data.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    return {"message": "Password changed successfully"}


@router.post("/request-password-reset", dependencies=[Depends(rate_limit("password-reset", 5, 3600))])
async def request_password_reset(
    reset_data: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Request password reset email"""
    user_service = UserService(db)
    user = user_service.get_user_by_email(reset_data.email)
    
    if user:
        # Create reset token
        reset_token = security.create_password_reset_token(user.email)
        
        # Send password reset email
        background_tasks.add_task(send_password_reset_email, user.email, reset_token)

    # The same answer either way, so this can't be used to find accounts
    return {"message": "If an account with that email exists, a password reset email has been sent"}


@router.post("/reset-password", dependencies=[Depends(rate_limit("password-reset-confirm", 10, 3600))])
async def reset_password(
    reset_data: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    """Reset password using reset token"""
    email = security.verify_password_reset_token(reset_data.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )
    
    user_service = UserService(db)
    success = user_service.reset_password(email, reset_data.new_password)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"message": "Password reset successfully"}


@router.post("/verify-email")
async def verify_email(
    verification_data: EmailVerification,
    db: Session = Depends(get_db)
):
    """Verify email address using verification token"""
    email = security.verify_email_verification_token(verification_data.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    
    user_service = UserService(db)
    success = user_service.verify_email(email)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"message": "Email verified successfully"}


@router.post("/resend-verification", dependencies=[Depends(rate_limit("resend-verification", 5, 3600))])
async def resend_verification_email(
    email_data: PasswordResetRequest,  # Reuse schema since it just has email
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Resend email verification"""
    user_service = UserService(db)
    user = user_service.get_user_by_email(email_data.email)
    
    if user and not user.is_verified:
        # Create verification token
        verification_token = security.create_email_verification_token(user.email)
        
        # Send verification email
        background_tasks.add_task(send_verification_email, user.email, verification_token)

        return {"message": "Verification email sent"}
    
    return {"message": "If an unverified account with that email exists, a verification email has been sent"}