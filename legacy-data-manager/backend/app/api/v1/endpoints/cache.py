from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from ....services.scan_cache_service import ScanCacheService
from ....services.google_drive import GoogleDriveService
from ....core.auth import get_current_user
from ....core.config import settings
from datetime import datetime

router = APIRouter()

def get_scan_cache_service(
    drive_service: GoogleDriveService = Depends(get_current_user)
) -> ScanCacheService:
    """Dependency to get a per-user cache service."""
    # Extract user_id from GoogleDriveService
    user_id = drive_service.user_id if hasattr(drive_service, 'user_id') and drive_service.user_id else None
    return ScanCacheService(user_id=user_id)

@router.get("/status")
async def get_cache_status(
    scan_cache: ScanCacheService = Depends(get_scan_cache_service)
):
    """Get the current status of the scan cache for the authenticated user."""
    return scan_cache.get_cache_status()

@router.get("/debug/{target_id}")
async def debug_cache(
    target_id: str,
    scan_cache: ScanCacheService = Depends(get_scan_cache_service)
):
    """Debug endpoint to check cache contents for a specific target (user-specific)."""
    try:
        cache_entry = scan_cache.get_cached_result(target_id)
        if cache_entry:
            return {
                "target_id": target_id,
                "cached": True,
                "data": cache_entry
            }
        return {
            "target_id": target_id,
            "cached": False,
            "message": "No cache entry found or cache expired"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/invalidate")
async def invalidate_cache(
    target_id: Optional[str] = None,
    scan_cache: ScanCacheService = Depends(get_scan_cache_service)
):
    """
    Invalidate the scan cache for the authenticated user.
    If target_id is provided, only invalidate that specific target.
    If target_id is None, invalidate all caches for this user.
    """
    try:
        scan_cache.invalidate_cache(target_id)
        return {"message": f"Cache invalidated for {target_id if target_id else 'all targets'}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/directories")
async def get_cached_directories(
    scan_cache: ScanCacheService = Depends(get_scan_cache_service)
):
    """Get a list of directory IDs that are currently cached for the authenticated user."""
    return {"directories": scan_cache.get_cached_directories()}

@router.get("/check/{target_id}")
async def check_cache(
    target_id: str,
    scan_cache: ScanCacheService = Depends(get_scan_cache_service)
):
    """Check if a specific target is currently cached and return its data (user-specific)."""
    try:
        cache_entry = scan_cache.get_cache_entry(target_id)
        if not cache_entry:
            return {
                "cached": False,
                "message": "No cache entry found"
            }
            
        # Calculate time until expiry
        now = datetime.utcnow()
        last_scan = cache_entry['last_scan']
        ttl = scan_cache.cache_ttl
        expires_at = last_scan + ttl if last_scan else None
        time_until_expiry = (expires_at - now).total_seconds() if expires_at and expires_at > now else 0
        
        return {
            "cached": True,
            "last_scan": last_scan.isoformat() if last_scan else None,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "time_until_expiry_seconds": time_until_expiry if time_until_expiry > 0 else 0,
            "data": cache_entry['data']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
