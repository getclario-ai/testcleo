from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional, List, Union
from functools import lru_cache
import json

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
    
    # CORS - pydantic-settings expects JSON string for List fields
    # For Render: Set as JSON string: ["https://testcleo.netlify.app"]
    # OR comma-separated: https://testcleo.netlify.app
    # Default includes localhost for development and Netlify for production
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://testcleo.netlify.app",
        "https://www.testcleo.netlify.app"  # Netlify can serve both www and non-www
    ]
    
    @field_validator('BACKEND_CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins from JSON string or list"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If not JSON, treat as comma-separated string
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
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
    
    # Debug/Logging Configuration
    # Can be set via environment variable: DEBUG=True uvicorn ...
    # Or via LOG_LEVEL environment variable: LOG_LEVEL=DEBUG uvicorn ...
    DEBUG: bool = False  # Set to True to enable debug logging
    LOG_LEVEL: Optional[str] = None  # Alternative: LOG_LEVEL=DEBUG (overrides DEBUG if set)
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        env_file_encoding = 'utf-8' # Specify encoding

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings() 