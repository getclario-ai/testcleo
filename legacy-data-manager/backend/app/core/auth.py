from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from ..services.google_drive import GoogleDriveService
from ..db.database import get_db
from ..db.models import WebUser
from ..core.session import get_session_id, is_session_expired
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> GoogleDriveService:
    """
    FastAPI dependency that validates the user's session and returns a GoogleDriveService instance.
    Uses database-backed sessions.
    """
    # Get session_id from cookie
    session_id = get_session_id(request)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - no session found",
        )
    
    # Look up user by session_id
    user = db.query(WebUser).filter(WebUser.session_id == session_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - invalid session",
        )
    
    # Check if session is expired
    if is_session_expired(user.session_expires_at):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired - please login again",
        )
    
    # Check if user has refresh token
    if not user.google_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - no Google Drive credentials",
        )
    
    # Create GoogleDriveService with user_id
    drive_service = GoogleDriveService(user_id=user.id)
    
    # Load credentials from database
    credentials = drive_service.load_credentials_from_db(db, user.google_refresh_token)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to load credentials",
        )
    
    return drive_service 