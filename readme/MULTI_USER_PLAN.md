# Multi-User Support Implementation Plan

## Current Architecture Analysis

### Token Storage
- **Current**: Single `token.pickle` file on filesystem (shared across all users)
- **Location**: `legacy-data-manager/backend/token.pickle`
- **Issue**: Each new login overwrites previous user's token

### Session Management
- **Current**: NO session management
- **Issue**: No way to identify which user is making requests
- **Frontend**: Uses `localStorage` + `credentials: 'include'` (cookies)

### Cache Service
- **Current**: `ScanCacheService` is a singleton (shared cache)
- **Issue**: All users share the same cache (security/privacy concern)

### Database Models
- **Existing**: `SlackUser` model (for Slack users only)
- **Missing**: Web user model for browser-based authentication

## Implementation Plan

### Phase 1: Database Schema & Models

#### 1.1 Create WebUser Model
**File**: `legacy-data-manager/backend/app/db/models.py`

```python
class WebUser(Base):
    __tablename__ = "web_users"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)  # Unique session identifier
    email = Column(String, nullable=True)  # Google email (optional, for display)
    
    # Google Drive credentials (encrypted)
    google_credentials_encrypted = Column(String)  # JSON-encoded, encrypted credentials
    refresh_token = Column(String)  # Separate refresh token for easy access
    token_expires_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
```

**Decisions needed:**
- Should we store full credentials encrypted, or just refresh_token?
- Should we use encryption library or rely on database-level encryption?

#### 1.2 Database Migration
- Create migration script to:
  - Create `web_users` table
  - Migrate existing `token.pickle` to a default user (if any)
  - Set up indexes

### Phase 2: Session Management

#### 2.1 Session Identification Strategy
**Options:**
- **Option A**: FastAPI Session Middleware (recommended)
  - Uses encrypted cookies
  - Session ID generated and stored in cookie
  - Requires `itsdangerous` or `python-jose` for signing
  
- **Option B**: JWT Tokens
  - Stateless authentication
  - User ID encoded in token
  - Requires token refresh mechanism
  
- **Option C**: Simple Cookie-based Session ID
  - Generate UUID session ID on first request
  - Store in cookie
  - Map to user in database

**Recommendation**: **Option A** (FastAPI Session) - easier to manage, built-in support

#### 2.2 Implementation
**File**: `legacy-data-manager/backend/app/core/session.py` (NEW)

```python
from fastapi import Request
from itsdangerous import URLSafeTimedSerializer
from typing import Optional
import uuid

# Generate secret key for session signing
SESSION_SECRET = settings.SESSION_SECRET  # Add to config

def get_session_id(request: Request) -> str:
    """Get or create session ID from cookie."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        # Generate new session ID
        session_id = str(uuid.uuid4())
    return session_id

def set_session_cookie(response, session_id: str):
    """Set session cookie in response."""
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,  # Prevent JS access (security)
        secure=True,  # HTTPS only in production
        samesite="lax",  # CSRF protection
        max_age=86400 * 30  # 30 days
    )
```

### Phase 3: Token Storage Refactoring

#### 3.1 Update GoogleDriveService
**File**: `legacy-data-manager/backend/app/services/google_drive.py`

**Changes:**
- Remove file-based `load_credentials()` and `save_credentials()`
- Add `load_credentials_for_user(user_id: str)` - loads from database
- Add `save_credentials_for_user(user_id: str, credentials)` - saves to database
- Update `__init__()` to accept optional `user_id`
- Update `is_authenticated()` to check database instead of file

**Key Methods:**
```python
class GoogleDriveService:
    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.credentials = None
        self.service = None
        
    async def load_credentials_for_user(self, user_id: str) -> Optional[Credentials]:
        """Load credentials from database for specific user."""
        # Query database for user
        # Decrypt credentials
        # Return Credentials object
        
    async def save_credentials_for_user(self, user_id: str, credentials: Credentials):
        """Save credentials to database for specific user."""
        # Encrypt credentials
        # Save to database
        # Update user record
```

#### 3.2 Update Auth Endpoints
**File**: `legacy-data-manager/backend/app/api/v1/endpoints/auth.py`

**Changes:**
- `google_callback`: Create/update `WebUser` record with credentials
- `google_status`: Check database for user's credentials
- `get_current_user`: Return `GoogleDriveService` with `user_id` loaded

**Flow:**
```python
@router.get("/google/callback")
async def google_callback(
    code: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    # 1. Get or create session ID
    session_id = get_session_id(request)
    
    # 2. Exchange code for credentials
    credentials = drive_service.get_credentials_from_code(code)
    
    # 3. Create or update WebUser in database
    user = get_or_create_user(db, session_id)
    user.google_credentials_encrypted = encrypt_credentials(credentials)
    user.refresh_token = credentials.refresh_token
    # ... update other fields
    
    # 4. Set session cookie
    set_session_cookie(response, session_id)
    
    # 5. Redirect to frontend
    return redirect...
```

### Phase 4: Per-User Cache

#### 4.1 Update ScanCacheService
**File**: `legacy-data-manager/backend/app/services/scan_cache_service.py`

**Changes:**
- Remove singleton pattern
- Add `user_id` to cache key
- Cache structure: `{user_id: {drive: {...}, directories: {...}}}`

**Options:**
- **Option A**: In-memory per-user cache (simple, but lost on restart)
- **Option B**: Database-backed cache (persistent, slower)
- **Option C**: Redis cache (fast, persistent, requires Redis)

**Recommendation**: Start with **Option A**, move to **Option C** later if needed

**New Structure:**
```python
class ScanCacheService:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.cache = {
            'drive': {...},
            'directories': {...}
        }
        
    def get_cached_result(self, target_id: str) -> Optional[Dict]:
        # Cache key now includes user_id
        # Check cache for this user only
```

#### 4.2 Update Cache Usage
**File**: `legacy-data-manager/backend/app/api/v1/endpoints/drive.py`

**Changes:**
- Inject `ScanCacheService` via dependency with `user_id`
- Replace `scan_cache = ScanCacheService()` with `Depends(get_scan_cache_service)`

### Phase 5: Update Dependencies

#### 5.1 Update get_current_user
**File**: `legacy-data-manager/backend/app/core/auth.py`

**Changes:**
- Extract `user_id` from session cookie
- Query database for `WebUser`
- Return `GoogleDriveService` initialized with `user_id`
- Handle missing/expired sessions gracefully

```python
async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> GoogleDriveService:
    """Get authenticated user's GoogleDriveService."""
    # 1. Get session_id from cookie
    session_id = get_session_id(request)
    
    # 2. Query database for user
    user = db.query(WebUser).filter(WebUser.session_id == session_id).first()
    if not user:
        raise HTTPException(401, "Not authenticated")
    
    # 3. Create GoogleDriveService with user_id
    drive_service = GoogleDriveService(user_id=user.id)
    
    # 4. Load credentials for this user
    await drive_service.load_credentials_for_user(user.id)
    
    return drive_service
```

## Implementation Order

### Step 1: Database Setup (No breaking changes)
1. Create `WebUser` model
2. Create database migration
3. Test migration on existing database

### Step 2: Session Management (Minimal changes)
1. Add session middleware
2. Create `get_session_id()` helper
3. Add session cookie setting

### Step 3: Token Storage (Breaking changes)
1. Update `GoogleDriveService` to support `user_id`
2. Create `load_credentials_for_user()` and `save_credentials_for_user()`
3. Update auth callback to save to database
4. **Migration**: Import existing `token.pickle` as "default" user

### Step 4: Update Dependencies (Breaking changes)
1. Update `get_current_user` to use sessions
2. Update all endpoints to work with new dependency
3. Test all endpoints

### Step 5: Per-User Cache (Low risk)
1. Update `ScanCacheService` to accept `user_id`
2. Create `get_scan_cache_service()` dependency
3. Update all cache usages

### Step 6: Frontend Updates (Minimal)
1. Ensure `credentials: 'include'` is used (already done)
2. Test session persistence across page reloads
3. Test multiple users in different browsers

## Critical Decisions Needed

### Decision 1: Credential Storage Format
**Question**: How should we store Google credentials in database?
- **Option A**: Store full credentials JSON (encrypted)
- **Option B**: Store only refresh_token, regenerate access_token when needed
- **Recommendation**: **Option B** (simpler, more secure)

### Decision 2: Session Management Library
**Question**: Which library for session management?
- **Option A**: `itsdangerous` (simple, FastAPI recommended)
- **Option B**: `python-jose` (JWT-based, more complex)
- **Option C**: `starlette-sessions` (dedicated session middleware)
- **Recommendation**: **Option A** or **Option C**

### Decision 3: Encryption for Credentials
**Question**: How to encrypt stored credentials?
- **Option A**: Python `cryptography` library (Fernet symmetric encryption)
- **Option B**: Database-level encryption (PostgreSQL encryption)
- **Option C**: Store only refresh_token (no encryption needed)
- **Recommendation**: **Option C** for now, **Option A** if storing full credentials

### Decision 4: Cache Persistence
**Question**: Should cache survive server restart?
- **Option A**: In-memory only (simple, fast, lost on restart)
- **Option B**: Database-backed (persistent, slower)
- **Option C**: Redis (fast, persistent, requires infrastructure)
- **Recommendation**: **Option A** initially, document migration to **Option C**

### Decision 5: Existing Users Migration
**Question**: How to handle existing `token.pickle`?
- **Option A**: Import as "default" user on first migration
- **Option B**: Force re-authentication for all users
- **Option C**: Prompt users to re-authenticate
- **Recommendation**: **Option A** with clear logging

## Testing Strategy

### Unit Tests
- Test `load_credentials_for_user()` with various user IDs
- Test `save_credentials_for_user()` encryption/decryption
- Test session ID generation and cookie setting
- Test cache isolation between users

### Integration Tests
- Test full OAuth flow with session management
- Test multiple concurrent users
- Test session expiration
- Test token refresh for per-user tokens

### Manual Testing
- Test with multiple browsers (different users)
- Test session persistence across page reloads
- Test logout/clear session
- Test concurrent scans from different users

## Breaking Changes

### Backend API Changes
- ✅ **No API changes** - endpoints remain the same
- ✅ **No response format changes**
- ⚠️ **Session required** - all authenticated endpoints now require valid session
- ⚠️ **Cookie required** - frontend must send cookies

### Frontend Changes
- ✅ Already using `credentials: 'include'` (good!)
- ⚠️ Must handle 401 errors for expired sessions
- ⚠️ May need logout endpoint to clear session

### Database Changes
- ✅ New `web_users` table
- ⚠️ Migration required before deployment

## Rollback Plan

If issues arise:
1. Keep old code branch available
2. Migration is additive (new table), won't break old code
3. Can revert to file-based tokens by switching `GoogleDriveService` implementation
4. Cache can revert to singleton if needed

## Open Questions

1. **User identification**: Should we use email from Google profile, or just session ID?
2. **Session expiration**: How long should sessions last? (30 days default)
3. **Token refresh**: Should we auto-refresh tokens, or require re-authentication?
4. **Admin users**: Do we need special admin user handling?
5. **Slack integration**: How to handle Slack users vs Web users? (Separate tables or unified?)

## Next Steps

1. **Decide on critical decisions** (above)
2. **Create database migration script**
3. **Implement session management**
4. **Update GoogleDriveService**
5. **Test incrementally**

