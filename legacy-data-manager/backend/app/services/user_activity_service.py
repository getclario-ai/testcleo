"""
User Activity Tracking Service

Tracks all user activities for audit trail and analytics.
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from ..db.models import UserActivity, WebUser
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class UserActivityService:
    """Service for tracking user activities"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def record_activity(
        self,
        event_type: str,
        action: str,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        slack_user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        source: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> UserActivity:
        """
        Record a user activity event.
        
        Args:
            event_type: Type of event (e.g., 'scan_initiated', 'file_accessed', 'auth_login')
            action: Action performed (e.g., 'scan', 'view', 'analyze', 'login')
            user_id: Web user ID (if available)
            user_email: User email (denormalized for quick queries)
            slack_user_id: Slack user ID (for Slack actions)
            resource_type: Type of resource (e.g., 'directory', 'file', 'cache')
            resource_id: ID of the resource (e.g., directory_id, file_id)
            source: Source of the action ('web', 'slack', 'api')
            ip_address: Client IP address
            user_agent: User agent string
            metadata: Additional context (dict, will be stored as JSON)
            status: Status of the action ('success', 'failed', 'partial')
            error_message: Error message if action failed
            duration_ms: Duration of the action in milliseconds
        
        Returns:
            UserActivity: The created activity record
        """
        try:
            # If user_id provided but email not, try to get email
            if user_id and not user_email:
                user = self.db.query(WebUser).filter(WebUser.id == user_id).first()
                if user:
                    user_email = user.email
            
            activity = UserActivity(
                user_id=user_id,
                user_email=user_email,
                slack_user_id=slack_user_id,
                event_type=event_type,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                source=source,
                ip_address=ip_address,
                user_agent=user_agent,
                status=status,
                error_message=error_message,
                duration_ms=duration_ms,
                created_at=datetime.utcnow()
            )
            
            # Store metadata as JSON
            if metadata:
                activity.set_metadata(metadata)
            
            self.db.add(activity)
            self.db.commit()
            self.db.refresh(activity)
            
            logger.debug(f"Recorded activity: {event_type} - {action} by user {user_id or user_email}")
            
            return activity
            
        except Exception as e:
            logger.error(f"Error recording user activity: {e}", exc_info=True)
            self.db.rollback()
            # Don't raise - activity tracking shouldn't break the main flow
            return None
    
    def get_user_activities(
        self,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[UserActivity]:
        """
        Get user activities with optional filtering.
        
        Args:
            user_id: Filter by user ID
            user_email: Filter by user email
            event_type: Filter by event type
            limit: Maximum number of results
            offset: Offset for pagination
        
        Returns:
            List of UserActivity records
        """
        query = self.db.query(UserActivity)
        
        if user_id:
            query = query.filter(UserActivity.user_id == user_id)
        elif user_email:
            query = query.filter(UserActivity.user_email == user_email)
        
        if event_type:
            query = query.filter(UserActivity.event_type == event_type)
        
        return query.order_by(UserActivity.created_at.desc()).offset(offset).limit(limit).all()
    
    def get_activity_stats(
        self,
        user_id: Optional[int] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get activity statistics for a user.
        
        Args:
            user_id: User ID to get stats for
            days: Number of days to look back
        
        Returns:
            Dictionary with activity statistics
        """
        from datetime import timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        query = self.db.query(UserActivity).filter(UserActivity.created_at >= cutoff_date)
        
        if user_id:
            query = query.filter(UserActivity.user_id == user_id)
        
        activities = query.all()
        
        # Count by event type
        event_counts = {}
        action_counts = {}
        source_counts = {}
        
        for activity in activities:
            event_counts[activity.event_type] = event_counts.get(activity.event_type, 0) + 1
            action_counts[activity.action] = action_counts.get(activity.action, 0) + 1
            if activity.source:
                source_counts[activity.source] = source_counts.get(activity.source, 0) + 1
        
        return {
            "total_activities": len(activities),
            "event_type_counts": event_counts,
            "action_counts": action_counts,
            "source_counts": source_counts,
            "period_days": days
        }



