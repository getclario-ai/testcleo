# Multi-User Support - Implementation Plan

## Decisions Made

1. **Credential Storage**: Store only `refresh_token` (simpler, secure)
2. **Session Management**: JWT tokens (stateless, scalable)
3. **Cache Persistence**: In-memory only (lost on restart, simpler)
4. **Encryption**: Rely on database security (no encryption library needed)
5. **Migration**: Force re-authentication (no import of existing token.pickle)

## Architecture Overview

### Flow Diagram
```
User → Frontend → Backend
      ↓
  GET /auth/google/login
      ↓
  Generate JWT with session_id
      ↓
  Redirect to Google OAuth
      ↓
  Google redirects with code
      ↓
  POST /auth/google/callback
      ↓
  Exchange code for credentials
      ↓
  Store refresh_token in DB (WebUser)
      ↓
  Generate JWT with user_id
      ↓
  Set JWT in cookie
      ↓
  Future requests include JWT
      ↓
  get_current_user decodes JWT
      ↓
  Load user's refresh_token from DB
      ↓
  Return GoogleDriveService with user_id
```

## Implementation Steps

### Step 1: Add JWT Dependencies

**File**: `legacy-data-manager/backend/requirements.txt`

Add:
```
python-jose[cryptography]
passlib[bcrypt]  # Optional, for future password hashing if needed
```

Or for lighter weight:
```
PyJWT
cryptography  # For signing JWT
```

### Step 2: Create WebUser Database Model

**File**: `legacy-data-manager/backend/app/db/models.py`

```python
class WebUser(Base):
    __tablename__ = "web_users"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)  # Unique session UUID
    email = Column(String, nullable=True)  # Google email (for display)
    
    # Google Drive credentials
    google_refresh_token = Column(String)  # Refresh token only
    token_expires_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
```

### Step 3: JWT Session Management

**File**: `legacy-data-manager/backend/app/core/jwt_session.py` (NEW)

```python
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Request, Response, HTTPException, status
from ..core.config import settings

# JWT Configuration
JWT_SECRET_KEY = settings.JWT_SECRET_KEY  # Add to config
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 30  # 30 days

def create_session_token(user_id: int, session_id: str) -> str:
    """Create JWT token for user session."""
    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_session_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None

def get_jwt_from_request(request: Request) -> Optional[str]:
    """Get JWT token from cookie or Authorization header."""
    # Try cookie first
    token = request.cookies.get("session_token")
    if token:
        return token
    
    # Fallback to Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    
    return None

def set_session_cookie(response: Response, token: str):
    """Set JWT token as HTTP-only cookie."""
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,  # Prevent JS access
        secure=True,  # HTTPS only in production
        samesite="lax",  # CSRF protection
        max_age=JWT_EXPIRATION_HOURS * 3600  # 30 days in seconds
    )
```

### Step 4: Update Config

**File**: `legacy-data-manager/backend/app/core/config.py`

Add:
```python
JWT_SECRET_KEY: str  # Required - generate strong secret key
```

### Step 5: Update GoogleDriveService

**File**: `legacy-data-manager/backend/app/services/google_drive.py`

**Key Changes:**
- Add `user_id` parameter to `__init__()`
- Remove file-based `load_credentials()` and `save_credentials()`
- Add `load_credentials_from_db()` method
- Add `save_refresh_token_to_db()` method

```python
class GoogleDriveService:
    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
        self.credentials = None
        self.service = None
        self.refresh_token = None  # Store refresh token separately
        
    async def load_credentials_from_db(self, db: Session) -> Optional[Credentials]:
        """Load credentials from database for this user."""
        if not self.user_id:
            return None
            
        from ..db.models import WebUser
        user = db.query(WebUser).filter(WebUser.id == self.user_id).first()
        
        if not user or not user.google_refresh_token:
            return None
        
        # Recreate Credentials object from refresh_token
        credentials = Credentials(
            token=None,  # Will be refreshed
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET
        )
        
        # Refresh token if expired
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self.save_refresh_token_to_db(db, credentials.refresh_token)
            except Exception as e:
                logger.error(f"Failed to refresh credentials: {e}")
                return None
        
        self.credentials = credentials
        self.refresh_token = user.google_refresh_token
        return credentials
    
    async def save_refresh_token_to_db(
        self, 
        db: Session, 
        refresh_token: str,
        session_id: str,
        email: Optional[str] = None
    ):
        """Save refresh token to database."""
        from ..db.models import WebUser
        
        # Find or create user
        user = db.query(WebUser).filter(WebUser.session_id == session_id).first()
        
        if not user:
            user = WebUser(session_id=session_id, email=email)
            db.add(user)
        else:
            user.email = email or user.email
        
        user.google_refresh_token = refresh_token
        user.last_login_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        
        # Update self.user_id for future use
        self.user_id = user.id
```

### Step 6: Update Auth Endpoints

**File**: `legacy-data-manager/backend/app/api/v1/endpoints/auth.py`

**Key Changes:**
- `google_login`: Generate session_id, include in state
- `google_callback`: Create/update WebUser, generate JWT, set cookie
- `google_status`: Decode JWT, check user in DB

```python
@router.get("/google/login")
async def google_login(
    request: Request,
    db: Session = Depends(get_db)
):
    """Initiate Google OAuth2 flow with session management."""
    try:
        # Generate or get existing session_id
        session_id = request.cookies.get("session_id") or str(uuid.uuid4())
        
        # Create state with session_id
        state_data = {
            "origin": "cleo",
            "session_id": session_id
        }
        encoded_state = json.dumps(state_data)
        
        # Get auth URL
        drive_service = GoogleDriveService()
        auth_url = await drive_service.get_auth_url(state=encoded_state)
        
        # Create response with session_id cookie (if new)
        response = JSONResponse({"auth_url": auth_url})
        if not request.cookies.get("session_id"):
            response.set_cookie(
                key="session_id",
                value=session_id,
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=86400 * 30  # 30 days
            )
        
        return response
    except Exception as e:
        logger.error(f"Error getting auth URL: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/google/callback")
async def google_callback(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db)
):
    """Handle Google OAuth callback and create user session."""
    frontend_url = settings.FRONTEND_URL or "http://localhost:3000"
    
    # Handle OAuth errors
    if error:
        logger.warning(f"Google OAuth error: {error}")
        error_message = {
            "access_denied": "Authentication was cancelled. Please try again.",
            "invalid_request": "Authentication request was invalid. Please try again.",
        }.get(error, f"Authentication failed: {error}.")
        return RedirectResponse(
            url=f"{frontend_url}/?error=auth_denied&message={error_message}"
        )
    
    if not code:
        logger.error("Missing 'code' parameter")
        return RedirectResponse(
            url=f"{frontend_url}/?error=auth_failed&message=Missing authentication code."
        )
    
    try:
        # Parse state to get session_id
        session_id = None
        if state:
            try:
                state_data = json.loads(state)
                session_id = state_data.get("session_id")
            except:
                pass
        
        # Fallback: get from cookie
        if not session_id:
            session_id = request.cookies.get("session_id") or str(uuid.uuid4())
        
        # Exchange code for credentials
        drive_service = GoogleDriveService()
        credentials = drive_service.get_credentials_from_code(code)
        
        # Get user email from Google (optional)
        email = None
        try:
            # Build service to get user info
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            email = user_info.get('email')
        except Exception as e:
            logger.warning(f"Could not fetch user email: {e}")
        
        # Save refresh_token to database
        from ..db.models import WebUser
        user = db.query(WebUser).filter(WebUser.session_id == session_id).first()
        
        if not user:
            user = WebUser(
                session_id=session_id,
                email=email,
                google_refresh_token=credentials.refresh_token
            )
            db.add(user)
        else:
            user.google_refresh_token = credentials.refresh_token
            user.email = email or user.email
            user.last_login_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        # Generate JWT token
        from ..core.jwt_session import create_session_token, set_session_cookie
        jwt_token = create_session_token(user.id, session_id)
        
        # Create redirect response
        redirect_response = RedirectResponse(url=f"{frontend_url}/")
        
        # Set cookies
        set_session_cookie(redirect_response, jwt_token)
        redirect_response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=86400 * 30
        )
        
        logger.info(f"Successfully authenticated user {user.id} ({email})")
        return redirect_response
        
    except Exception as e:
        logger.error(f"Error during OAuth callback: {e}", exc_info=True)
        return RedirectResponse(
            url=f"{frontend_url}/?error=auth_failed&message=Failed to authenticate."
        )
```

### Step 7: Update get_current_user

**File**: `legacy-data-manager/backend/app/core/auth.py`

```python
from fastapi import Depends, HTTPException, status, Request
from ..db.database import get_db
from ..services.google_drive import GoogleDriveService
from ..core.jwt_session import get_jwt_from_request, decode_session_token
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> GoogleDriveService:
    """
    FastAPI dependency that validates JWT and returns GoogleDriveService instance.
    """
    # Get JWT token from request
    token = get_jwt_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Decode JWT
    payload = decode_session_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    # Create GoogleDriveService with user_id
    drive_service = GoogleDriveService(user_id=user_id)
    
    # Load credentials from database
    credentials = await drive_service.load_credentials_from_db(db)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No credentials found for user",
        )
    
    return drive_service
```

### Step 8: Update ScanCacheService

**File**: `legacy-data-manager/backend/app/services/scan_cache_service.py`

```python
class ScanCacheService:
    def __init__(self, user_id: Optional[int] = None):
        """Initialize cache service for a specific user."""
        self.user_id = user_id
        self.cache = {
            'drive': {
                'last_scan': None,
                'data': None
            },
            'directories': {}
        }
        self.cache_ttl = timedelta(minutes=60)
    
    def _get_cache_key(self, target_id: str) -> str:
        """Generate cache key including user_id."""
        if self.user_id:
            return f"user_{self.user_id}_{target_id}"
        return f"global_{target_id}"
    
    # Rest of methods remain the same, but now scoped to user_id
```

### Step 9: Update drive.py Cache Dependency

**File**: `legacy-data-manager/backend/app/api/v1/endpoints/drive.py`

```python
# Remove singleton
# scan_cache = ScanCacheService()  # DELETE THIS

def get_scan_cache_service(
    drive_service: GoogleDriveService = Depends(get_current_user)
) -> ScanCacheService:
    """Get per-user cache service."""
    # Extract user_id from GoogleDriveService
    user_id = drive_service.user_id if hasattr(drive_service, 'user_id') else None
    return ScanCacheService(user_id=user_id)

# Update all endpoints to use:
# scan_cache: ScanCacheService = Depends(get_scan_cache_service)
```

### Step 10: Add Logout Endpoint

**File**: `legacy-data-manager/backend/app/api/v1/endpoints/auth.py`

```python
@router.post("/google/logout")
async def google_logout(response: Response):
    """Logout user by clearing session cookies."""
    response.delete_cookie(key="session_token")
    response.delete_cookie(key="session_id")
    return {"message": "Logged out successfully"}
```

## Testing Checklist

### Unit Tests
- [ ] JWT token creation and validation
- [ ] GoogleDriveService.load_credentials_from_db()
- [ ] GoogleDriveService.save_refresh_token_to_db()
- [ ] ScanCacheService per-user isolation

### Integration Tests
- [ ] Full OAuth flow with JWT
- [ ] Multiple concurrent users
- [ ] Token expiration handling
- [ ] Cache isolation between users

### Manual Tests
- [ ] Two different browsers = two different users
- [ ] Session persists across page reloads
- [ ] Logout clears session
- [ ] Re-authentication creates new session

## Migration Notes

1. **No data migration needed** - users will re-authenticate
2. **Old token.pickle** - Can be deleted or ignored
3. **Database migration** - Run `Base.metadata.create_all()` to create `web_users` table
4. **JWT_SECRET_KEY** - Must be set in environment variables (generate strong key)

## Breaking Changes

- ✅ **API endpoints unchanged** - Same URLs, same responses
- ⚠️ **All users must re-authenticate** - JWT required for all authenticated endpoints
- ⚠️ **Old sessions invalid** - Users need to login again

## Rollback Plan

1. Keep old `auth.py` branch
2. Revert `get_current_user` to file-based token
3. Revert `GoogleDriveService` to file-based methods
4. Database migration is additive (new table), won't break old code

