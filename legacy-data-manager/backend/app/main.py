from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints import drive, chat, slack, auth, cache, activity
from app.core.config import settings
from app.core.activity_tracking import ActivityTrackingMiddleware
from app.db.database import engine, Base
from app.services.google_drive import GoogleDriveService
from app.services.chat_service import ChatService
import logging

# Import all models to ensure they're registered with Base.metadata
# This must happen BEFORE Base.metadata.create_all()
from app.db.models import (
    SlackUser,
    WebUser,
    SlackLinkingAudit,
    UserActivity  # User activity tracking model
)

# Create database tables (if they don't exist)
# All models must be imported above for this to work
Base.metadata.create_all(bind=engine) # Uncommented to create tables for SQLite

# Configure logging - supports both DEBUG env var and LOG_LEVEL env var
# Usage: DEBUG=True uvicorn ... OR LOG_LEVEL=DEBUG uvicorn ...
if settings.LOG_LEVEL:
    # LOG_LEVEL env var takes precedence (e.g., LOG_LEVEL=DEBUG)
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
elif settings.DEBUG:
    log_level = logging.DEBUG
else:
    log_level = logging.INFO

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
if log_level == logging.DEBUG:
    logger.info("Debug mode enabled - verbose logging active")

# Initialize services
drive_service = GoogleDriveService()
chat_service = ChatService(drive_service)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API for managing and analyzing legacy data",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set CORS middleware - using BACKEND_CORS_ORIGINS from config
cors_origins = settings.BACKEND_CORS_ORIGINS
# Handle "*" case for development
if cors_origins == ["*"]:
    allow_origins = ["*"]
    allow_credentials = False  # Can't use credentials with wildcard
else:
    allow_origins = cors_origins
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Add activity tracking middleware (after CORS, before routes)
app.add_middleware(ActivityTrackingMiddleware)

# Include routers
app.include_router(drive.router, prefix=settings.API_V1_STR + "/drive", tags=["drive"])
app.include_router(chat.router, prefix=settings.API_V1_STR + "/chat", tags=["chat"])
app.include_router(slack.router, prefix=settings.API_V1_STR + "/slack", tags=["slack"])
app.include_router(auth.router, prefix=settings.API_V1_STR + "/auth", tags=["auth"])
app.include_router(cache.router, prefix=settings.API_V1_STR + "/cache", tags=["cache"])
app.include_router(activity.router, prefix=settings.API_V1_STR + "/activity", tags=["activity"])

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"} 