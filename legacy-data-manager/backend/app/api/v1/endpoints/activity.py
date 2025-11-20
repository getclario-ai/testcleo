"""
API endpoints for user activity tracking and audit trail.
Enhanced version with better user and resource information.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import logging

from ....db.database import get_db
from ....db.models import UserActivity, WebUser
from ....core.auth import get_current_user
from ....services.google_drive import GoogleDriveService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/activity", tags=["activity"])

# TODO: Add rate limiting middleware - target: 500 requests per minute per IP
# This prevents DoS attacks and data exfiltration attempts
# Consider using slowapi or similar rate limiting library


@router.get("/")
async def get_activities(
    # Input validation: event_type max 50 chars, alphanumeric + underscore only
    event_type: Optional[str] = Query(None, max_length=50, regex="^[a-z0-9_]+$"),
    # Input validation: user_email max 255 chars, basic email format
    user_email: Optional[str] = Query(None, max_length=255, regex="^[^@]+@[^@]+\\.[^@]+$"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    days: int = Query(30, ge=1, le=365),
    drive_service: GoogleDriveService = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user activities with enhanced details.
    
    Args:
        event_type: Filter by event type
        user_email: Filter by user email
        limit: Maximum number of records to return
        offset: Number of records to skip
        days: Number of days to look back (default 30)
    """
    try:
        # Base query
        query = db.query(UserActivity)
        
        # Filter by date range
        since_date = datetime.utcnow() - timedelta(days=days)
        query = query.filter(UserActivity.created_at >= since_date)
        
        # Apply filters
        if event_type:
            query = query.filter(UserActivity.event_type == event_type)
        
        if user_email:
            query = query.filter(UserActivity.user_email == user_email)
        
        # Order by created_at descending (newest first)
        query = query.order_by(desc(UserActivity.created_at))
        
        # Apply pagination
        activities = query.offset(offset).limit(limit).all()
        
        # Convert to dict with enhanced information
        result = []
        for activity in activities:
            metadata = activity.get_metadata() or {}
            
            result.append({
                "id": activity.id,
                "user_id": activity.user_id,
                "user_email": activity.user_email or "N/A",
                "event_type": activity.event_type,
                "action": activity.action,
                "resource_type": activity.resource_type,
                "resource_id": activity.resource_id,
                "source": activity.source,
                "ip_address": activity.ip_address,
                "user_agent": activity.user_agent,
                "trace_id": activity.trace_id,
                "metadata": metadata,
                "status": activity.status,
                "error_message": activity.error_message,
                "duration_ms": activity.duration_ms,
                "created_at": activity.created_at.isoformat() if activity.created_at else None
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching activities: {e}", exc_info=True)
        return []


@router.get("/stats")
async def get_activity_stats(
    days: int = Query(30, ge=1, le=365),
    drive_service: GoogleDriveService = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get aggregated activity statistics.
    
    Args:
        days: Number of days to look back (default 30)
    """
    try:
        # Filter by date range
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Total activities
        total_activities = db.query(func.count(UserActivity.id)).filter(
            UserActivity.created_at >= since_date
        ).scalar()
        
        # Count by event_type
        event_type_counts = {}
        event_type_results = db.query(
            UserActivity.event_type,
            func.count(UserActivity.id)
        ).filter(
            UserActivity.created_at >= since_date
        ).group_by(UserActivity.event_type).all()
        
        for event_type, count in event_type_results:
            event_type_counts[event_type] = count
        
        # Count by action
        action_counts = {}
        action_results = db.query(
            UserActivity.action,
            func.count(UserActivity.id)
        ).filter(
            UserActivity.created_at >= since_date
        ).group_by(UserActivity.action).all()
        
        for action, count in action_results:
            action_counts[action] = count
        
        # Count by source
        source_counts = {}
        source_results = db.query(
            UserActivity.source,
            func.count(UserActivity.id)
        ).filter(
            UserActivity.created_at >= since_date
        ).group_by(UserActivity.source).all()
        
        for source, count in source_results:
            source_counts[source or "unknown"] = count
        
        return {
            "total_activities": total_activities,
            "event_type_counts": event_type_counts,
            "action_counts": action_counts,
            "source_counts": source_counts,
            "period_days": days
        }
        
    except Exception as e:
        logger.error(f"Error fetching activity stats: {e}", exc_info=True)
        return {
            "total_activities": 0,
            "event_type_counts": {},
            "action_counts": {},
            "source_counts": {},
            "period_days": days
        }


@router.get("/users")
async def get_active_users(
    days: int = Query(30, ge=1, le=365),
    drive_service: GoogleDriveService = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of users with activity in the given period.
    
    Args:
        days: Number of days to look back (default 30)
    """
    try:
        since_date = datetime.utcnow() - timedelta(days=days)
        
        users = db.query(UserActivity.user_email).filter(
            UserActivity.created_at >= since_date,
            UserActivity.user_email.isnot(None),
            UserActivity.user_email != "N/A"
        ).distinct().all()
        
        return [user[0] for user in users if user[0]]
        
    except Exception as e:
        logger.error(f"Error fetching active users: {e}", exc_info=True)
        return []
