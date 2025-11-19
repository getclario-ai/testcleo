"""
Activity Tracking Middleware - Enhanced Version

Automatically tracks all user activities with improved user and resource tracking.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Tuple
import time
import logging

from ..services.user_activity_service import UserActivityService
from ..db.database import SessionLocal
from ..db.models import WebUser

logger = logging.getLogger(__name__)


class ActivityTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically track user activities with enhanced context"""
    
    def __init__(self, app):
        super().__init__(app)
        # Paths to exclude from tracking
        self.exclude_path_prefixes = [
            '/api/v1/activity',  # Don't track audit trail views
            '/docs',
            '/openapi.json',
            '/favicon.ico'
        ]
    
    async def dispatch(self, request: Request, call_next):
        # Check if path should be excluded
        path = str(request.url.path)
        if any(path.startswith(prefix) for prefix in self.exclude_path_prefixes):
            return await call_next(request)
        
        # Get event type and action from route
        event_type, action = get_event_type_from_route(request.method, path)
        
        # Skip if no event type (internal endpoints)
        if event_type is None:
            return await call_next(request)
        
        # Extract user info - try multiple sources
        user_id = None
        user_email = None
        session_id = request.cookies.get('session_id')
        
        # Try to get user from request state first (set by auth dependency)
        # This is the most efficient path - no DB query needed
        if hasattr(request.state, 'user_data'):
            user_data = request.state.user_data
            user_id = user_data.get('user_id')
            user_email = user_data.get('user_email')
        
        # Only query database if user info not in request.state
        # This reduces DB hits significantly since most authenticated requests
        # will have user_data populated by get_current_user dependency
        if not user_email and session_id:
            db = SessionLocal()
            try:
                user = db.query(WebUser).filter(WebUser.session_id == session_id).first()
                if user:
                    user_id = user.id
                    user_email = user.email
                    # Store in request.state for potential reuse (though request is almost done)
                    if not hasattr(request.state, 'user_data'):
                        request.state.user_data = {}
                    request.state.user_data['user_id'] = user_id
                    request.state.user_data['user_email'] = user_email
            except Exception as e:
                logger.debug(f"Could not lookup user from session: {e}")
            finally:
                db.close()
        
        # Extract request metadata
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get('user-agent')
        source = determine_source(path, user_agent, user_email)
        
        # Extract resource info
        resource_type, resource_id = extract_resource_info(path)
        
        # Start timing
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Determine status
        if response.status_code < 400:
            activity_status = "success"
        elif response.status_code < 500:
            activity_status = "failed"
        else:
            activity_status = "error"
        
        # Record activity (non-blocking)
        try:
            db = SessionLocal()
            try:
                activity_service = UserActivityService(db)
                activity_service.record_activity(
                    event_type=event_type,
                    action=action,
                    user_id=user_id,
                    user_email=user_email,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    source=source,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status=activity_status,
                    duration_ms=duration_ms
                )
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error recording activity: {e}", exc_info=True)
        
        return response


def get_event_type_from_route(method: str, path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Determine event type and action from HTTP method and path.
    Returns: (event_type, action) or (None, None) to skip tracking
    """
    normalized_path = path.lower()
    
    # Authentication events
    if '/auth/google/login' in normalized_path:
        return ('auth_login', 'login')
    elif '/auth/google/logout' in normalized_path:
        return ('auth_logout', 'logout')
    elif '/auth/google/status' in normalized_path:
        return (None, None)  # Don't track status checks
    elif '/auth/google/callback' in normalized_path:
        return (None, None)  # Don't track callback (covered by login)
    
    # Directory/Drive events
    elif normalized_path.endswith('/directories') and method == 'GET':
        return (None, None)  # Manual tracking in endpoint (exclude from middleware)
    elif '/directories/' in normalized_path and '/analyze' in normalized_path:
        return (None, None)  # Manual tracking in endpoint
    elif '/directories/' in normalized_path and '/files' in normalized_path:
        return (None, None)  # Manual tracking in endpoint
    
    # File events
    elif '/drive/files/' in normalized_path and method == 'GET':
        return (None, None)  # Internal metadata lookup
    
    # Slack events
    elif '/slack' in normalized_path:
        return ('slack_event', 'process')
    
    # Default: skip tracking for unmatched paths
    return (None, None)


def determine_source(path: str, user_agent: Optional[str], user_email: Optional[str]) -> str:
    """Determine request source: web, slack, or api"""
    if '/slack' in path.lower():
        return 'slack'
    elif user_email:  # If we have authenticated web user
        return 'web'
    elif user_agent and ('mozilla' in user_agent.lower() or 'chrome' in user_agent.lower()):
        return 'web'
    else:
        return 'api'


def extract_resource_info(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract resource type and ID from path"""
    # Extract directory ID
    if '/directories/' in path:
        parts = path.split('/directories/')
        if len(parts) > 1:
            resource_id = parts[1].split('/')[0].split('?')[0]
            return ('directory', resource_id)
    
    # Extract file ID
    if '/files/' in path:
        parts = path.split('/files/')
        if len(parts) > 1:
            resource_id = parts[1].split('/')[0].split('?')[0]
            return ('file', resource_id)
    
    return (None, None)

