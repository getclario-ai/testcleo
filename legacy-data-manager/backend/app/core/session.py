"""
Session management utilities for database-backed sessions.
"""
from fastapi import Request, Response
from typing import Optional
from datetime import datetime, timedelta, timezone
import uuid

# Session configuration
SESSION_COOKIE_NAME = "session_id"
SESSION_EXPIRATION_DAYS = 30


def generate_session_id() -> str:
    """Generate a unique session ID (UUID)."""
    return str(uuid.uuid4())


def get_session_id(request: Request) -> Optional[str]:
    """Get session ID from cookie."""
    return request.cookies.get(SESSION_COOKIE_NAME)


def set_session_cookie(response: Response, session_id: str, expires_at: Optional[datetime] = None):
    """
    Set session cookie in response.
    
    Args:
        response: FastAPI Response object
        session_id: Session ID to set
        expires_at: When session expires (if None, uses SESSION_EXPIRATION_DAYS)
                   Must be timezone-aware UTC datetime
    """
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_EXPIRATION_DAYS)
    else:
        # Ensure expires_at is timezone-aware UTC
        if expires_at.tzinfo is None:
            # If naive datetime, assume it's UTC
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        elif expires_at.tzinfo != timezone.utc:
            # Convert to UTC if different timezone
            expires_at = expires_at.astimezone(timezone.utc)
    
    max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    
    # Determine if we're in production (HTTPS) or development (HTTP)
    # Check if frontend URL is HTTPS to determine secure setting
    from ..core.config import settings
    is_secure = settings.FRONTEND_URL.startswith("https://") if hasattr(settings, 'FRONTEND_URL') else False
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,  # Prevent JavaScript access (security)
        secure=is_secure,  # HTTPS only in production (False for localhost)
        samesite="lax",  # CSRF protection
        max_age=max_age,
        expires=expires_at
    )


def delete_session_cookie(response: Response):
    """Delete session cookie (for logout)."""
    # Determine if we're in production (HTTPS) or development (HTTP)
    from ..core.config import settings
    is_secure = settings.FRONTEND_URL.startswith("https://") if hasattr(settings, 'FRONTEND_URL') else False
    
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=is_secure,
        samesite="lax"
    )


def is_session_expired(expires_at: Optional[datetime]) -> bool:
    """Check if session has expired."""
    if expires_at is None:
        return True
    # Handle both timezone-aware and naive datetimes
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        # If naive, assume UTC
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    elif expires_at.tzinfo != timezone.utc:
        # Convert to UTC for comparison
        expires_at = expires_at.astimezone(timezone.utc)
    return now > expires_at

