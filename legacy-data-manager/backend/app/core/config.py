from pydantic_settings import BaseSettings
from typing import Optional, List
from functools import lru_cache

class Settings(BaseSettings):
    PROJECT_NAME: str = "Legacy Data Manager"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Frontend URL
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Database Configuration
    # Use DATABASE_URL for connection (works for SQLite or PostgreSQL)
    DATABASE_URL: str 
    
    # Make PostgreSQL specific fields optional for flexibility
    POSTGRES_SERVER: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]  # Adjust in production
    
    # Google Drive Settings
    GOOGLE_DRIVE_CREDENTIALS_FILE: str = "credentials.json" # Or adjust based on your setup
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback" # Adjust if needed
    
    # Hugging Face Settings
    HUGGINGFACE_API_TOKEN: str = ""
    
    # Slack Configuration
    SLACK_CLIENT_ID: Optional[str] = None # Often optional unless doing user installs
    SLACK_CLIENT_SECRET: Optional[str] = None # Often optional unless doing user installs
    SLACK_SIGNING_SECRET: str
    SLACK_BOT_TOKEN: str
    SLACK_APP_TOKEN: Optional[str] = None # Optional depending on Slack connection mode
    SLACK_NOTIFICATION_CHANNEL: str = "legacydata" # Channel for scan notifications
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        env_file_encoding = 'utf-8' # Specify encoding

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings() 