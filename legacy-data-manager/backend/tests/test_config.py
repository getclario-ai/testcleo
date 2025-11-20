import pytest
from pathlib import Path
import sys

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from app.core.config import settings

def test_project_settings():
    """Test project settings"""
    assert settings.PROJECT_NAME == "Clario"
    assert settings.API_V1_STR == "/api/v1"
    assert settings.VERSION == "1.0.0"
    assert settings.DESCRIPTION == "Document and Data Management Platform"

def test_google_drive_settings():
    """Test Google Drive settings"""
    assert settings.GOOGLE_DRIVE_CREDENTIALS_FILE is not None
    assert settings.GOOGLE_DRIVE_TOKEN_FILE is not None
    assert settings.GOOGLE_DRIVE_SCOPES is not None
    assert isinstance(settings.GOOGLE_DRIVE_SCOPES, list)
    assert len(settings.GOOGLE_DRIVE_SCOPES) > 0
    assert all(scope.startswith("https://www.googleapis.com/auth/drive") for scope in settings.GOOGLE_DRIVE_SCOPES)

def test_file_paths():
    """Test file paths"""
    assert Path(settings.GOOGLE_DRIVE_CREDENTIALS_FILE).parent.exists()
    assert Path(settings.GOOGLE_DRIVE_TOKEN_FILE).parent.exists() 