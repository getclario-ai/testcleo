from fastapi import APIRouter, Depends, HTTPException, Request, Query
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

from ....core.config import settings
from ....db.database import get_db
from ....services.google_drive import GoogleDriveService

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
async def google_login(drive_service: GoogleDriveService = Depends(get_drive_service)):
    """
    Redirects the user to Google's consent screen.
    """
    try:
        # Create state with origin=cleo
        state_data = {
            "origin": "cleo",
            "session_id": str(uuid.uuid4())
        }
        encoded_state = json.dumps(state_data)
        
        logger.debug("Getting auth URL")
        # Get auth URL with state
        auth_url = await drive_service.get_auth_url(state=encoded_state)
        logger.debug(f"Got auth URL: {auth_url}")
        return {"auth_url": auth_url}
    except Exception as e:
        logger.error(f"Error getting auth URL: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/google/callback", summary="Handle Google OAuth2 callback")
async def google_callback(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
    drive_service: GoogleDriveService = Depends(get_drive_service)
):
    """
    Handles the callback from Google, exchanges code for tokens.
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
        # Exchange code for credentials
        credentials = drive_service.get_credentials_from_code(code)
        
        # Store credentials in token file
        with open('token.pickle', 'wb') as token:
            pickle.dump(credentials, token)
        
        logger.info("Successfully authenticated with Google Drive")
        
        # Redirect to the frontend dashboard
        return RedirectResponse(url=f"{frontend_url}/")
        
    except Exception as e:
        logger.error(f"Error during Google OAuth callback: {e}", exc_info=True)
        # In case of error, redirect to frontend with error parameter
        return RedirectResponse(url=f"{frontend_url}/?error=auth_failed&message=Failed to authenticate. Please try again.")

@router.get("/google/status", summary="Check Google Auth status")
async def google_status(drive_service: GoogleDriveService = Depends(get_drive_service)):
    """
    Checks if authenticated with Google Drive.
    """
    try:
        is_authenticated = await drive_service.is_authenticated()
        return {
            "isAuthenticated": is_authenticated,
            "userType": "cleo",
            "detail": "Successfully checked authentication status"
        }
    except Exception as e:
        logger.error(f"Error checking auth status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Add /status endpoint later if needed 