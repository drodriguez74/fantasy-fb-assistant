from datetime import datetime, timedelta
from typing import Any, Union, Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.core.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    """Create a JWT access token"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(subject: Union[str, Any]) -> str:
    """Create a JWT refresh token (longer expiry)"""
    expire = datetime.utcnow() + timedelta(days=30)  # 30 days
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash"""
    return pwd_context.hash(password)


def verify_token(token: str) -> Optional[str]:
    """Verify JWT token and return subject (user_id)"""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[ALGORITHM]
        )
        token_data = payload.get("sub")
        if token_data is None:
            return None
        return token_data
    except JWTError:
        return None


def create_password_reset_token(email: str) -> str:
    """Create a password reset token"""
    delta = timedelta(hours=1)  # 1 hour expiry
    now = datetime.utcnow()
    expires = now + delta
    encoded_jwt = jwt.encode(
        {"exp": expires, "nbf": now, "sub": email, "type": "password_reset"},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> Optional[str]:
    """Verify password reset token and return email"""
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if decoded_token.get("type") != "password_reset":
            return None
        return decoded_token["sub"]
    except JWTError:
        return None


def create_email_verification_token(email: str) -> str:
    """Create an email verification token"""
    delta = timedelta(hours=24)  # 24 hour expiry
    now = datetime.utcnow()
    expires = now + delta
    encoded_jwt = jwt.encode(
        {"exp": expires, "nbf": now, "sub": email, "type": "email_verification"},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return encoded_jwt


def verify_email_verification_token(token: str) -> Optional[str]:
    """Verify email verification token and return email"""
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if decoded_token.get("type") != "email_verification":
            return None
        return decoded_token["sub"]
    except JWTError:
        return None