from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
import googleapiclient.discovery
import uuid
import json
import logging
import pickle
from datetime import datetime, timedelta, timezone

from ....core.config import settings
from ....db.database import get_db
from ....db.models import WebUser
from ....services.google_drive import GoogleDriveService
from ....core.session import generate_session_id, get_session_id, set_session_cookie, SESSION_EXPIRATION_DAYS

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter()

async def get_drive_service():
    """Dependency to get a fresh GoogleDriveService instance."""
    logger.debug("Creating new GoogleDriveService instance")
    service = GoogleDriveService()
    return service

@router.get("/google/login", summary="Initiate Google OAuth2 flow for Cleo")
async def google_login(
    request: Request,
    db: Session = Depends(get_db),
    drive_service: GoogleDriveService = Depends(get_drive_service)
):
    """
    Redirects the user to Google's consent screen.
    Creates or reuses session_id for multi-user support.
    """
    try:
        # Get or create session_id
        session_id = get_session_id(request)
        if not session_id:
            session_id = generate_session_id()
            # Set session cookie in response (will be set by callback after auth)
        
        # Create state with session_id for callback
        state_data = {
            "origin": "cleo",
            "session_id": session_id
        }
        encoded_state = json.dumps(state_data)
        
        logger.debug(f"Getting auth URL for session: {session_id}")
        # Get auth URL with state
        auth_url = await drive_service.get_auth_url(state=encoded_state)
        logger.debug(f"Got auth URL: {auth_url}")
        
        response = JSONResponse({"auth_url": auth_url})
        
        # Set session cookie if new session
        if not get_session_id(request):
            expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_EXPIRATION_DAYS)
            set_session_cookie(response, session_id, expires_at)
        
        return response
    except Exception as e:
        logger.error(f"Error getting auth URL: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/google/callback", summary="Handle Google OAuth2 callback")
async def google_callback(
    request: Request,
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
    db: Session = Depends(get_db),
    drive_service: GoogleDriveService = Depends(get_drive_service)
):
    """
    Handles the callback from Google, exchanges code for tokens.
    Creates or updates WebUser in database with refresh_token.
    """
    # Get the frontend URL from settings
    frontend_url = settings.FRONTEND_URL or "http://localhost:3000"
    
    # Handle OAuth errors (user denied access, etc.)
    if error:
        logger.warning(f"Google OAuth error: {error}")
        error_message = {
            "access_denied": "Authentication was cancelled. Please try again when you're ready.",
            "invalid_request": "Authentication request was invalid. Please try again.",
        }.get(error, f"Authentication failed: {error}. Please try again.")
        
        # Redirect to frontend with error message
        return RedirectResponse(url=f"{frontend_url}/?error=auth_denied&message={error_message}")
    
    # Check if code is missing
    if not code:
        logger.error("Missing 'code' parameter in OAuth callback")
        return RedirectResponse(url=f"{frontend_url}/?error=auth_failed&message=Missing authentication code. Please try again.")
    
    try:
        # Parse state to get session_id
        session_id = None
        if state:
            try:
                state_data = json.loads(state)
                session_id = state_data.get("session_id")
            except Exception as e:
                logger.warning(f"Could not parse state: {e}")
        
        # Fallback: get from cookie
        if not session_id:
            session_id = get_session_id(request)
            if not session_id:
                session_id = generate_session_id()
        
        # Exchange code for credentials
        credentials = drive_service.get_credentials_from_code(code)
        
        if not credentials.refresh_token:
            logger.error("No refresh token received from Google")
            return RedirectResponse(
                url=f"{frontend_url}/?error=auth_failed&message=No refresh token received. Please try again."
            )
        
        # Get user email from Google (REQUIRED - email is unique identifier)
        email = None
        try:
            service = googleapiclient.discovery.build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            email = user_info.get('email')
        except Exception as e:
            logger.error(f"Could not fetch user email: {e}", exc_info=True)
        
        if not email:
            logger.error("No email received from Google - email is required")
            return RedirectResponse(
                url=f"{frontend_url}/?error=auth_failed&message=Failed to retrieve email from Google. Please try again."
            )
        
        # Create or update WebUser in database
        # Lookup by email first (email is the unique identifier)
        user = db.query(WebUser).filter(WebUser.email == email).first()
        
        session_expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_EXPIRATION_DAYS)
        
        if not user:
            # Create new user (email is unique, so this is a new user)
            user = WebUser(
                email=email,
                session_id=session_id,
                google_refresh_token=credentials.refresh_token,
                last_login_at=datetime.now(timezone.utc),
                session_expires_at=session_expires_at
            )
            db.add(user)
            logger.info(f"Created new user with email: {email}, session_id: {session_id}")
        else:
            # Update existing user (same email, new session)
            user.session_id = session_id
            user.google_refresh_token = credentials.refresh_token
            user.last_login_at = datetime.now(timezone.utc)
            user.session_expires_at = session_expires_at
            logger.info(f"Updated user {user.id} (email: {email}) with new session {session_id}")
        
        db.commit()
        db.refresh(user)
        
        # Create redirect response
        redirect_response = RedirectResponse(url=f"{frontend_url}/")
        
        # Set session cookie
        set_session_cookie(redirect_response, session_id, session_expires_at)
        
        logger.info(f"Successfully authenticated user {user.id} ({email}) with session {session_id}")
        return redirect_response
        
    except Exception as e:
        logger.error(f"Error during Google OAuth callback: {e}", exc_info=True)
        return RedirectResponse(
            url=f"{frontend_url}/?error=auth_failed&message=Failed to authenticate. Please try again."
        )

@router.get("/google/status", summary="Check Google Auth status")
async def google_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Checks if authenticated with Google Drive using session.
    """
    try:
        from ....core.auth import get_current_user
        from ....core.session import get_session_id
        
        # Debug: Check session cookie
        session_id = get_session_id(request)
        logger.debug(f"Status check - session_id from cookie: {session_id}")
        logger.debug(f"Status check - all cookies: {request.cookies}")
        
        try:
            # Try to get current user (validates session)
            drive_service = await get_current_user(request, db)
            logger.debug(f"Status check - got drive_service with user_id: {drive_service.user_id if hasattr(drive_service, 'user_id') else 'None'}")
            
            is_authenticated = await drive_service.is_authenticated()
            logger.debug(f"Status check - is_authenticated: {is_authenticated}")
            
            # Get user info
            user = db.query(WebUser).filter(WebUser.id == drive_service.user_id).first()
            email = user.email if user else None
            
            logger.info(f"Status check - returning authenticated: {is_authenticated}, email: {email}")
            return {
                "isAuthenticated": is_authenticated,
                "userType": "cleo",
                "email": email,
                "detail": "Successfully checked authentication status"
            }
        except HTTPException as e:
            # Not authenticated
            logger.debug(f"Status check - HTTPException: {e.status_code} - {e.detail}")
            return {
                "isAuthenticated": False,
                "userType": "cleo",
                "email": None,
                "detail": f"Not authenticated: {e.detail}"
            }
    except Exception as e:
        logger.error(f"Error checking auth status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/google/logout", summary="Logout user")
async def google_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Logout user by clearing session.
    Invalidates the session in database and deletes the session cookie.
    """
    try:
        from ....core.session import get_session_id, delete_session_cookie
        from ....db.models import WebUser
        
        session_id = get_session_id(request)
        
        if session_id:
            # Invalidate session in database (immediately expire)
            user = db.query(WebUser).filter(WebUser.session_id == session_id).first()
            if user:
                # Immediately expire the session
                user.session_expires_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"Logged out user {user.id} (email: {user.email}) with session {session_id}")
            else:
                logger.warning(f"Logout called for session {session_id} but user not found")
        else:
            logger.warning("Logout called but no session_id in cookie")
        
        # Delete session cookie from browser
        delete_session_cookie(response)
        
        logger.info("Logout successful - session cookie deleted")
        return {"message": "Logged out successfully"}
    except Exception as e:
        logger.error(f"Error during logout: {e}", exc_info=True)
        # Still try to delete cookie even if DB update fails
        try:
            delete_session_cookie(response)
        except:
            pass
        return {"message": "Logout completed"}  # Don't fail if there's an error 