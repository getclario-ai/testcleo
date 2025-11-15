from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
import logging

logger = logging.getLogger(__name__)

# Shared cache for directories (keyed by directory_id only)
# All users share the same directory cache since same directory = same results
_directory_cache: Dict[str, Dict[str, Any]] = {}

# Per-user cache for drive-wide scans (each user's drive is different)
_user_drive_cache: Dict[int, Dict[str, Any]] = {}

# Legacy global cache (for backward compatibility when user_id is None)
_global_cache: Dict[str, Any] = {
    'drive': {
        'last_scan': None,
        'data': None
    },
    'directories': {}
}

class ScanCacheService:
    def __init__(self, user_id: Optional[int] = None):
        """
        Initialize cache service for a specific user.
        
        Architecture:
        - Directories: Shared cache (keyed by directory_id) - same directory = same results
        - Drive: Per-user cache (keyed by user_id) - each user's drive is different
        
        Args:
            user_id: Optional user ID for multi-user support. If None, uses global cache (legacy mode).
        """
        self.user_id = user_id
        self.cache_ttl = timedelta(minutes=60)
        
        # Initialize per-user drive cache if needed
        if user_id is not None:
            if user_id not in _user_drive_cache:
                _user_drive_cache[user_id] = {
                    'last_scan': None,
                    'data': None
                }
                logger.debug(f"Initialized per-user drive cache for user_id={user_id}")
            else:
                logger.debug(f"Using existing per-user drive cache for user_id={user_id}")
        else:
            logger.warning("Using global cache (legacy mode) - user_id is None")

    def get_cached_result(self, target_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached scan result for a target (drive or directory).
        Returns None if no cache exists or if cache is expired.
        
        Architecture:
        - Directories: Shared cache (all users share same directory cache)
        - Drive: Per-user cache (each user's drive is different)
        """
        try:
            if target_id == 'drive':
                # Per-user drive cache
                if self.user_id is None:
                    # Legacy mode: use global cache
                    cache_entry = _global_cache['drive']
                else:
                    cache_entry = _user_drive_cache.get(self.user_id)
                    if not cache_entry:
                        logger.debug(f"No drive cache found for user_id={self.user_id}")
                        return None
            else:
                # Shared directory cache (all users share same directory cache)
                cache_entry = _directory_cache.get(target_id)
                if not cache_entry:
                    # Legacy mode: check global cache
                    if self.user_id is None:
                        cache_entry = _global_cache['directories'].get(target_id)
                    if not cache_entry:
                        logger.debug(f"No cache found for directory {target_id}")
                        return None

            if not cache_entry or not cache_entry.get('last_scan'):
                logger.debug(f"No cache entry found for {target_id}")
                return None

            # Check if cache is expired
            if datetime.utcnow() - cache_entry['last_scan'] > self.cache_ttl:
                logger.info(f"Cache expired for {target_id}")
                return None

            cache_type = "shared directory" if target_id != 'drive' else f"user_{self.user_id} drive"
            logger.info(f"Using cached result for {target_id} (type={cache_type})")
            return cache_entry['data']

        except Exception as e:
            logger.error(f"Error getting cached result: {str(e)}", exc_info=True)
            return None

    def update_cache(self, target_id: str, data: Dict[str, Any]) -> None:
        """
        Update cache with new scan result.
        
        Architecture:
        - Directories: Shared cache (all users share same directory cache)
        - Drive: Per-user cache (each user's drive is different)
        """
        try:
            if target_id == 'drive':
                # Per-user drive cache
                if self.user_id is None:
                    # Legacy mode: use global cache
                    _global_cache['drive'] = {
                        'last_scan': datetime.utcnow(),
                        'data': data
                    }
                    logger.debug(f"Updated global drive cache")
                else:
                    _user_drive_cache[self.user_id] = {
                        'last_scan': datetime.utcnow(),
                        'data': data
                    }
                    logger.debug(f"Updated drive cache for user_id={self.user_id}")
            else:
                # Shared directory cache (all users share same directory cache)
                if target_id not in _directory_cache:
                    _directory_cache[target_id] = {
                        'scanned_by_users': []
                    }
                
                # Track which users have scanned this directory (for analytics/debugging)
                if self.user_id and self.user_id not in _directory_cache[target_id]['scanned_by_users']:
                    _directory_cache[target_id]['scanned_by_users'].append(self.user_id)
                
                _directory_cache[target_id].update({
                    'last_scan': datetime.utcnow(),
                    'data': data
                })
                
                scanned_by = _directory_cache[target_id].get('scanned_by_users', [])
                logger.debug(f"Updated shared directory cache for {target_id} (scanned by users: {scanned_by})")
                
                # Legacy mode: also update global cache
                if self.user_id is None:
                    _global_cache['directories'][target_id] = {
                        'last_scan': datetime.utcnow(),
                        'data': data
                    }
        except Exception as e:
            logger.error(f"Error updating cache: {str(e)}", exc_info=True)

    def invalidate_cache(self, target_id: Optional[str] = None) -> None:
        """
        Invalidate cache for a specific target or all targets.
        If target_id is None, invalidate all caches for this user (drive) or all directories (shared).
        """
        try:
            if target_id is None:
                # Invalidate all caches
                if self.user_id is None:
                    # Legacy mode: invalidate global cache
                    _global_cache['drive'] = {'last_scan': None, 'data': None}
                    _global_cache['directories'] = {}
                    logger.debug("Invalidated all global caches")
                else:
                    # Invalidate this user's drive cache
                    if self.user_id in _user_drive_cache:
                        _user_drive_cache[self.user_id] = {'last_scan': None, 'data': None}
                        logger.debug(f"Invalidated drive cache for user_id={self.user_id}")
                
                # Invalidate all shared directory caches
                _directory_cache.clear()
                logger.debug("Invalidated all shared directory caches")
            elif target_id == 'drive':
                # Invalidate drive cache for this user
                if self.user_id is None:
                    _global_cache['drive'] = {'last_scan': None, 'data': None}
                    logger.debug("Invalidated global drive cache")
                else:
                    if self.user_id in _user_drive_cache:
                        _user_drive_cache[self.user_id] = {'last_scan': None, 'data': None}
                        logger.debug(f"Invalidated drive cache for user_id={self.user_id}")
            else:
                # Invalidate shared directory cache (affects all users)
                _directory_cache.pop(target_id, None)
                # Also invalidate in legacy global cache if exists
                if self.user_id is None and target_id in _global_cache['directories']:
                    _global_cache['directories'].pop(target_id, None)
                logger.debug(f"Invalidated shared directory cache for {target_id}")
        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}", exc_info=True)

    def get_cache_status(self) -> Dict[str, Any]:
        """
        Get current cache status.
        Returns status for this user's drive cache and all shared directory caches.
        """
        try:
            # Get drive cache status
            if self.user_id is None:
                drive_cache = _global_cache['drive']
            else:
                drive_cache = _user_drive_cache.get(self.user_id, {'last_scan': None, 'data': None})
            
            status = {
                'drive': {
                    'cached': drive_cache.get('last_scan') is not None,
                    'last_scan': drive_cache['last_scan'].isoformat() if drive_cache.get('last_scan') else None
                },
                'directories': {}
            }

            # Get all shared directory caches
            for dir_id, cache_entry in _directory_cache.items():
                status['directories'][dir_id] = {
                    'cached': cache_entry.get('last_scan') is not None,
                    'last_scan': cache_entry['last_scan'].isoformat() if cache_entry.get('last_scan') else None,
                    'scanned_by_users': cache_entry.get('scanned_by_users', [])
                }

            return status
        except Exception as e:
            logger.error(f"Error getting cache status: {str(e)}", exc_info=True)
            return {'error': str(e)}

    def get_cached_directories(self) -> List[str]:
        """
        Get list of directory IDs that are currently cached (shared directory cache).
        """
        return list(_directory_cache.keys())

    def is_cached(self, target_id: str) -> bool:
        """
        Check if a target is currently cached and not expired.
        """
        return self.get_cached_result(target_id) is not None 

    def get_cache_entry(self, target_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the full cache entry including metadata for a target (drive or directory).
        Returns None if no cache exists.
        """
        try:
            if target_id == 'drive':
                # Per-user drive cache
                if self.user_id is None:
                    return _global_cache['drive']
                else:
                    return _user_drive_cache.get(self.user_id)
            else:
                # Shared directory cache
                cache_entry = _directory_cache.get(target_id)
                if not cache_entry and self.user_id is None:
                    # Legacy mode: check global cache
                    cache_entry = _global_cache['directories'].get(target_id)
                return cache_entry
        except Exception as e:
            logger.error(f"Error getting cache entry: {str(e)}", exc_info=True)
            return None 