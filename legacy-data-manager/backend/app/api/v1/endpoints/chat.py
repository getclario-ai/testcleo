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