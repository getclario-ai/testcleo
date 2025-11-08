from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
import logging

logger = logging.getLogger(__name__)

# Global per-user cache storage
# Structure: {user_id: {drive: {...}, directories: {...}}}
# Key can be int (user_id) or str ("global" for legacy mode)
_user_cache_storage: Dict[Any, Dict[str, Any]] = {}

class ScanCacheService:
    def __init__(self, user_id: Optional[int] = None):
        """
        Initialize cache service for a specific user.
        
        Args:
            user_id: Optional user ID for multi-user support. If None, uses global cache (legacy mode).
        """
        self.user_id = user_id
        self.cache_ttl = timedelta(minutes=60)
        
        # Initialize cache for this user if needed
        if user_id is not None:
            if user_id not in _user_cache_storage:
                _user_cache_storage[user_id] = {
                    'drive': {
                        'last_scan': None,
                        'data': None
                    },
                    'directories': {}
                }
                logger.info(f"Initialized per-user cache for user_id={user_id}")
            else:
                logger.debug(f"Using existing per-user cache for user_id={user_id}")
            self.cache = _user_cache_storage[user_id]
        else:
            # Legacy mode: shared cache (for backward compatibility)
            if 'global' not in _user_cache_storage:
                _user_cache_storage['global'] = {
                    'drive': {
                        'last_scan': None,
                        'data': None
                    },
                    'directories': {}
                }
                logger.warning("Using global cache (legacy mode) - user_id is None")
            else:
                logger.debug("Using existing global cache (legacy mode)")
            self.cache = _user_cache_storage['global']

    def get_cached_result(self, target_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached scan result for a target (drive or directory).
        Returns None if no cache exists or if cache is expired.
        """
        try:
            cache_key = f"user_id={self.user_id}" if self.user_id else "global"
            logger.debug(f"Getting cached result for {target_id} (cache_key={cache_key})")
            
            if target_id == 'drive':
                cache_entry = self.cache['drive']
            else:
                cache_entry = self.cache['directories'].get(target_id)

            if not cache_entry or not cache_entry['last_scan']:
                logger.debug(f"No cache found for {target_id} (cache_key={cache_key})")
                return None

            # Check if cache is expired
            if datetime.utcnow() - cache_entry['last_scan'] > self.cache_ttl:
                logger.info(f"Cache expired for {target_id} (cache_key={cache_key})")
                return None

            logger.info(f"Using cached result for {target_id} (cache_key={cache_key}, cached_at={cache_entry['last_scan']})")
            return cache_entry['data']

        except Exception as e:
            logger.error(f"Error getting cached result: {str(e)}", exc_info=True)
            return None

    def update_cache(self, target_id: str, data: Dict[str, Any]) -> None:
        """
        Update cache with new scan result.
        """
        try:
            cache_key = f"user_id={self.user_id}" if self.user_id else "global"
            logger.info(f"Updating cache for {target_id} (cache_key={cache_key})")
            
            # Log existing cached directories for this user
            existing_dirs = list(self.cache['directories'].keys())
            if existing_dirs:
                logger.info(f"Existing cached directories for user_id={self.user_id}: {existing_dirs}")
            
            if target_id == 'drive':
                self.cache['drive'] = {
                    'last_scan': datetime.utcnow(),
                    'data': data
                }
            else:
                self.cache['directories'][target_id] = {
                    'last_scan': datetime.utcnow(),
                    'data': data
                }
            logger.info(f"Updated cache for {target_id} (cache_key={cache_key}, stats={data.get('stats', {})})")
            logger.info(f"All cached directories after update: {list(self.cache['directories'].keys())}")
        except Exception as e:
            logger.error(f"Error updating cache: {str(e)}", exc_info=True)

    def invalidate_cache(self, target_id: Optional[str] = None) -> None:
        """
        Invalidate cache for a specific target or all targets.
        If target_id is None, invalidate all caches.
        """
        try:
            if target_id is None:
                # Invalidate all caches
                self.cache['drive'] = {'last_scan': None, 'data': None}
                self.cache['directories'] = {}
                logger.info("Invalidated all caches")
            elif target_id == 'drive':
                self.cache['drive'] = {'last_scan': None, 'data': None}
                logger.info("Invalidated drive cache")
            else:
                self.cache['directories'].pop(target_id, None)
                logger.info(f"Invalidated cache for directory {target_id}")
        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}", exc_info=True)

    def get_cache_status(self) -> Dict[str, Any]:
        """
        Get current cache status.
        """
        try:
            status = {
                'drive': {
                    'cached': self.cache['drive']['last_scan'] is not None,
                    'last_scan': self.cache['drive']['last_scan'].isoformat() if self.cache['drive']['last_scan'] else None
                },
                'directories': {}
            }

            for dir_id, cache_entry in self.cache['directories'].items():
                status['directories'][dir_id] = {
                    'cached': cache_entry['last_scan'] is not None,
                    'last_scan': cache_entry['last_scan'].isoformat() if cache_entry['last_scan'] else None
                }

            return status
        except Exception as e:
            logger.error(f"Error getting cache status: {str(e)}", exc_info=True)
            return {'error': str(e)}

    def get_cached_directories(self) -> List[str]:
        """
        Get list of directory IDs that are currently cached.
        """
        return list(self.cache['directories'].keys())

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
                return self.cache['drive']
            else:
                return self.cache['directories'].get(target_id)
        except Exception as e:
            logger.error(f"Error getting cache entry: {str(e)}", exc_info=True)
            return None 