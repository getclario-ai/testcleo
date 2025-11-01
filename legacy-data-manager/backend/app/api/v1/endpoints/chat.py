from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from ....services.chat_service import ChatService
from ....services.google_drive import GoogleDriveService
from ....core.auth import get_current_user
import logging
import traceback

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Pydantic Models ---
class ChatMessage(BaseModel):
    message: str

class CommandPayload(BaseModel):
    """Schema for the /command endpoint body."""
    command: str
    
def get_chat_service(drive_service: GoogleDriveService = Depends(get_current_user)) -> ChatService:
    """Dependency to get a ChatService instance with the current user's drive service."""
    return ChatService(drive_service)

@router.post("/messages")
async def process_message(
    chat_message: ChatMessage,
    chat_service: ChatService = Depends(get_chat_service)
):
    """Process a chat message and return a response."""
    try:
        response = await chat_service.process_message(chat_message.message)
        return response
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/command")
async def handle_command(
    command_payload: CommandPayload,
    chat_service: ChatService = Depends(get_chat_service),
    drive_service: GoogleDriveService = Depends(get_current_user)
):
    """Handle chat commands."""
    try:
        logger.info(f"Received command: {command_payload.command}")
        
        # Check authentication status (get_current_user already validates, but check explicitly for clarity)
        auth_status = await drive_service.is_authenticated()
        logger.info(f"Authentication status: {auth_status}")
        
        if not auth_status:
            return {
                "type": "error",
                "message": "Not authenticated with Google Drive. Please authenticate first."
            }
        
        # Get the command string from the validated payload
        cmd = command_payload.command
        logger.info(f"Processing command: {cmd}")
        
        # Process the command
        response = await chat_service.process_command(cmd)
        logger.info(f"Command response: {response}")
        
        return response
    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e)) 