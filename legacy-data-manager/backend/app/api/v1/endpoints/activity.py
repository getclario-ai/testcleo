"""
User Activity Tracking API Endpoints

Provides endpoints to query and analyze user activity logs.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from ....db.database import get_db
from ....services.user_activity_service import UserActivityService
from ....core.auth import get_current_user
from ....services.google_drive import GoogleDriveService
from datetime import datetime, timedelta

router = APIRouter()


def get_activity_service(db: Session = Depends(get_db)) -> UserActivityService:
    """Dependency to get UserActivityService instance."""
    return UserActivityService(db)


@router.get("/activities", summary="Get user activities")
async def get_activities(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    activity_service: UserActivityService = Depends(get_activity_service),
    drive_service: GoogleDriveService = Depends(get_current_user)
):
    """
    Get activity logs for the authenticated user.
    
    Returns a list of user activities with optional filtering.
    """
    try:
        user_id = drive_service.user_id if hasattr(drive_service, 'user_id') else None
        
        activities = activity_service.get_user_activities(
            user_id=user_id,
            event_type=event_type,
            limit=limit,
            offset=offset
        )
        
        # Convert to dict format for JSON response
        result = []
        for activity in activities:
            result.append({
                "id": activity.id,
                "event_type": activity.event_type,
                "action": activity.action,
                "resource_type": activity.resource_type,
                "resource_id": activity.resource_id,
                "source": activity.source,
                "status": activity.status,
                "duration_ms": activity.duration_ms,
                "metadata": activity.get_metadata(),
                "created_at": activity.created_at.isoformat() if activity.created_at else None
            })
        
        return {
            "activities": result,
            "count": len(result),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving activities: {str(e)}")


@router.get("/activities/stats", summary="Get user activity statistics")
async def get_activity_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    activity_service: UserActivityService = Depends(get_activity_service),
    drive_service: GoogleDriveService = Depends(get_current_user)
):
    """
    Get activity statistics for the authenticated user.
    
    Returns summary statistics about user activities.
    """
    try:
        user_id = drive_service.user_id if hasattr(drive_service, 'user_id') else None
        
        stats = activity_service.get_activity_stats(
            user_id=user_id,
            days=days
        )
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving activity stats: {str(e)}")



