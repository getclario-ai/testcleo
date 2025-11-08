from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from ....services.slack_service import SlackService
from ....services.chat_service import ChatService
from ....services.google_drive import GoogleDriveService
from ....db.database import get_db
from fastapi.responses import JSONResponse
import logging
import json
import hmac
import hashlib
import urllib.parse
from ....core.config import settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter()

def get_slack_service(db: Session = Depends(get_db)) -> SlackService:
    """
    Get SlackService instance.
    Note: This creates a SlackService without a user-specific drive_service.
    The drive_service will be created per-command based on the Slack user_id.
    """
    try:
        # Create a temporary unauthenticated drive_service for initialization
        # This will be replaced with user-specific drive_service in command handlers
        drive_service = GoogleDriveService()
        chat_service = ChatService(drive_service=drive_service)
        return SlackService(chat_service=chat_service, db=db)
    except Exception as e:
        logger.error(f"Error initializing Slack service: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error initializing dependent services: {str(e)}")

async def verify_slack_signature(request: Request, body_str: str = None) -> bool:
    """
    Verify that the request came from Slack using HMAC signature.
    
    Args:
        request: FastAPI Request object
        body_str: Optional pre-read body string. If None, will read from request.
                  For GET requests, should be query string.
    
    Returns:
        bool: True if signature is valid, False otherwise
    """
    try:
        # Get Slack signature and timestamp
        slack_signature = request.headers.get("X-Slack-Signature", "")
        slack_timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        
        logger.debug(f"Verifying Slack signature:")
        logger.debug(f"Received signature: {slack_signature}")
        logger.debug(f"Received timestamp: {slack_timestamp}")
        
        if not slack_signature or not slack_timestamp:
            logger.error("Missing Slack signature or timestamp")
            return False
        
        # Use provided body_str or read from request
        if body_str is None:
            # For GET requests, use query parameters
            if request.method == "GET":
                body_str = "&".join(f"{k}={v}" for k, v in sorted(request.query_params.items()))
            else:
                # For POST requests, read body (only if not provided)
                body = await request.body()
                body_str = body.decode('utf-8') if body else ""
        
        logger.debug(f"Request body/query string: {body_str}")
        
        # Create base string
        base_string = f"v0:{slack_timestamp}:{body_str}"
        logger.debug(f"Base string for signature: {base_string}")
        
        # Calculate signature
        my_signature = 'v0=' + hmac.new(
            settings.SLACK_SIGNING_SECRET.encode(),
            base_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        logger.debug(f"Calculated signature: {my_signature}")
        logger.debug(f"Received signature: {slack_signature}")
        
        # Compare signatures
        is_valid = hmac.compare_digest(my_signature, slack_signature)
        logger.debug(f"Signature verification result: {is_valid}")
        
        return is_valid
    except Exception as e:
        logger.error(f"Error verifying Slack signature: {str(e)}", exc_info=True)
        return False

@router.post("/events")
async def handle_slack_events(request: Request, slack_service: SlackService = Depends(get_slack_service)):
    """Handle incoming Slack events"""
    try:
        # Get the raw body
        body = await request.body()
        if not body:
            logger.error("Empty request body")
            raise HTTPException(status_code=400, detail="Empty request body")
            
        body_str = body.decode('utf-8')
        logger.debug(f"Received raw body: {body_str}")
        
        # Parse the JSON payload
        payload = json.loads(body_str)
        logger.debug(f"Parsed payload: {payload}")
        
        # Handle URL verification challenge
        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge")
            logger.info(f"Handling Slack URL verification challenge. Challenge value: {challenge}")
            return {"challenge": challenge}
            
        # Verify the request came from Slack (pass body_str to avoid double-read)
        if not await verify_slack_signature(request, body_str):
            logger.error("Invalid Slack signature")
            raise HTTPException(status_code=401, detail="Invalid Slack signature")
        
        # Handle different event types
        event_type = payload.get("type")
        logger.debug(f"Processing event type: {event_type}")
        
        if event_type == "event_callback":
            event = payload.get("event", {})
            event_type = event.get("type")
            logger.debug(f"Processing event callback type: {event_type}")
            
            if event_type == "app_mention":
                await slack_service.handle_mention(event)
                return {"ok": True}
                
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Error handling Slack event: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal server error: {str(e)}"}
        )

@router.post("/commands")
@router.get("/commands")
async def handle_slack_commands(request: Request, slack_service: SlackService = Depends(get_slack_service)):
    """Handle incoming Slack slash commands"""
    try:
        # Log all headers for debugging
        logger.debug(f"Request headers: {dict(request.headers)}")
        
        # Get the raw body for signature verification
        body = await request.body()
        body_str = body.decode('utf-8') if body else ""
        logger.debug(f"Raw request body: {body_str}")
        
        # For GET requests, construct body_str from query parameters for signature verification
        if request.method == "GET":
            body_str = "&".join(f"{k}={v}" for k, v in sorted(request.query_params.items()))
        
        # Parse the form data
        if request.method == "POST":
            # Parse form data from body_str (already read)
            form_dict = dict(urllib.parse.parse_qsl(body_str))
        else:  # GET request
            form_dict = dict(request.query_params)
        
        logger.debug(f"Received {request.method} request with data: {form_dict}")
        
        # Verify the request came from Slack (pass body_str to avoid double-read)
        if not await verify_slack_signature(request, body_str):
            logger.error("Invalid Slack signature")
            # Log the signature verification details
            slack_signature = request.headers.get("X-Slack-Signature", "")
            slack_timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
            logger.error(f"Slack signature: {slack_signature}")
            logger.error(f"Slack timestamp: {slack_timestamp}")
            raise HTTPException(status_code=401, detail="Invalid Slack signature")
        
        # Check if this is an auth command
        if form_dict.get("text", "").strip().lower() == "auth":
            user_id = form_dict.get("user_id")
            channel_id = form_dict.get("channel_id")
            if not user_id:
                return {
                    "response_type": "ephemeral",
                    "text": "Could not determine your Slack user ID. Please try again."
                }
            
            # Get the auth URL
            auth_url = f"{request.base_url}api/v1/slack/auth/url?slack_user_id={user_id}&email={user_id}@slack.com"
            await slack_service.send_message(
                channel_id,
                f"Please authenticate with Google Drive by visiting this URL: {auth_url}"
            )
            return {
                "response_type": "ephemeral",
                "text": "I've sent you an authentication link. Please check your direct messages."
            }
        
        # Process other commands
        response = await slack_service.handle_slash_command(form_dict)
        return response
        
    except Exception as e:
        logger.error(f"Error handling Slack command: {str(e)}", exc_info=True)
        return {
            "response_type": "ephemeral",
            "text": f"Sorry, I encountered an error processing your command: {str(e)}"
        } 