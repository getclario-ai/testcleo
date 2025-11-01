from fastapi import APIRouter, HTTPException, Request, Depends, status, BackgroundTasks
from typing import Dict, List, Optional
from ....services.google_drive import GoogleDriveService
from ....core.config import settings
import logging
from datetime import datetime, timezone, timedelta
from fastapi.responses import RedirectResponse
import json
import uuid
import asyncio
from ....core.auth import get_current_user
from ....services.file_scanner_with_json import scan_files
from ....services.scan_cache_service import ScanCacheService
from ....services.slack_service import SlackService
from ....services.chat_service import ChatService
from ....services.notification_service import NotificationService
from ....db.database import get_db, SessionLocal
from asyncio import Lock, TimeoutError

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter()
drive_service = GoogleDriveService()
scan_cache = ScanCacheService()


async def _trigger_notifications(
    directory_id: str,
    drive_service: GoogleDriveService,
    scan_results: Dict
) -> None:
    """
    Trigger notifications for scan results.
    Called asynchronously so it doesn't block the scan response.
    """
    try:
        logger.info(f"Triggering notifications for directory {directory_id}")
        
        # Get directory name for notification
        directory_name = directory_id  # Default to ID if name unavailable
        try:
            directory_metadata = await drive_service.get_file_metadata(directory_id)
            if directory_metadata and 'name' in directory_metadata:
                directory_name = directory_metadata['name']
                logger.info(f"Directory name for notification: {directory_name}")
        except Exception as e:
            logger.warning(f"Could not get directory name for notification: {e}")
        
        # Create services for notifications
        db = SessionLocal()
        try:
            chat_service = ChatService(drive_service)
            slack_service = SlackService(chat_service=chat_service, db=db)
            notification_service = NotificationService(slack_service=slack_service)
            
            # Check if notifications should be sent
            notification_flags = notification_service.should_send_notification(scan_results)
            logger.info(f"Notification flags: {notification_flags}")
            logger.info(f"Scan stats: {scan_results.get('stats', {})}")
            
            # Send notifications (this is already async, and we're in an async context)
            await notification_service.send_scan_notifications(
                directory_id=directory_id,
                directory_name=directory_name,
                scan_results=scan_results
            )
            logger.info(f"Notification process completed for {directory_name}")
        finally:
            db.close()
    except Exception as e:
        # Don't fail the scan if notifications fail
        logger.error(f"Error in notification trigger: {str(e)}", exc_info=True)


def determine_file_type(file: Dict) -> str:
    """
    Determine the type of file based on its MIME type.
    Returns one of: "documents", "spreadsheets", "presentations", "pdfs", "images", "others"
    """
    mime_type = file.get('mimeType', '')
    
    if mime_type == 'application/pdf':
        return 'pdfs'
    elif mime_type.startswith('image/'):
        return 'images'
    elif mime_type in ['application/vnd.google-apps.document', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        return 'documents'
    elif mime_type in ['application/vnd.google-apps.spreadsheet', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
        return 'spreadsheets'
    elif mime_type in ['application/vnd.google-apps.presentation', 'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation']:
        return 'presentations'
    else:
        return 'others'

def categorize_file_by_age(file: Dict) -> str:
    """
    Categorize a file based on its modification date.
    Returns one of: "moreThanThreeYears", "oneToThreeYears", "lessThanOneYear"
    """
    try:
        modified_time = datetime.fromisoformat(file['modifiedTime'].replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        age = now - modified_time
        
        if age > timedelta(days=3*365):  # More than 3 years
            return "moreThanThreeYears"
        elif age > timedelta(days=365):   # Between 1-3 years
            return "oneToThreeYears"
        else:                             # Less than 1 year
            return "lessThanOneYear"
    except Exception as e:
        logger.error(f"Error categorizing file age: {e}")
        return "moreThanThreeYears"  # Default to oldest category if we can't determine age

@router.get("/auth/url")
async def get_auth_url_redirect():
    """Redirect to the new auth URL endpoint."""
    logger.info("Redirecting old auth URL endpoint to new endpoint")
    return RedirectResponse(url="/api/v1/auth/google/login")

@router.get("/auth/callback")
async def auth_callback_redirect(code: str):
    """Redirect to the new auth callback endpoint."""
    logger.info("Redirecting old auth callback endpoint to new endpoint")
    return RedirectResponse(url=f"/api/v1/auth/google/callback?code={code}")

@router.get("/auth/status")
async def get_auth_status_redirect(drive_service: GoogleDriveService = Depends(get_current_user)):
    """Check Google Drive authentication status."""
    try:
        is_authenticated = await drive_service.is_authenticated()
        return {
            "isAuthenticated": is_authenticated,
            "userType": "cleo",
            "detail": "Successfully checked authentication status"
        }
    except Exception as e:
        logger.error(f"Error checking auth status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files")
async def list_files(
    age_group: str = None,
    category: str = None,
    risk_level: str = None,
    department: str = None,
    page: int = 1,
    per_page: int = 20,
    drive_service: GoogleDriveService = Depends(get_current_user)
):
    """List files from Google Drive with filtering by various criteria."""
    try:
        # Get cached analysis results
        cached_result = scan_cache.get_cached_result('drive')
        if not cached_result:
            # No cache, so fetch, analyze, and cache
            files_response = await drive_service.list_files(page_size=1000)
            files = files_response.get('files', [])
            # Run analysis/categorization on the root folder for drive-wide scan
            results = await scan_files(source='gdrive', path_or_drive_id='root')
            scan_cache.update_cache('drive', results)
            cached_result = results

        # Apply filters to the files list
        filtered_files = cached_result.get("files", [])
        
        # Filter by age group if specified
        if age_group:
            filtered_files = [f for f in filtered_files if f.get("ageGroup") == age_group]
            
        # Filter by sensitivity category if specified
        if category:
            filtered_files = [f for f in filtered_files if f.get("sensitiveCategories") and category in f.get("sensitiveCategories", [])]
            
        # Filter by risk level if specified
        if risk_level:
            filtered_files = [f for f in filtered_files if f.get("riskLevelLabel") == risk_level]
            
        # Filter by department if specified
        if department:
            filtered_files = [f for f in filtered_files if f.get("department") == department]
        
        total_files = len(filtered_files)
        
        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_files = filtered_files[start_idx:end_idx]

        return {
            "files": paginated_files,
            "total": total_files,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_files + per_page - 1) // per_page
        }

    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing files: {str(e)}"
        )

@router.get("/files/inactive")
async def list_inactive_files():
    """List inactive files from Google Drive."""
    if not drive_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated. Please authenticate first.")
    try:
        files = drive_service.get_inactive_files()
        return {"files": files}
    except Exception as e:
        logger.error(f"Error listing inactive files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/{file_id}")
async def get_file_metadata(
    file_id: str,
    drive_service: GoogleDriveService = Depends(get_current_user)
):
    """Get metadata for a specific file."""
    try:
        metadata = await drive_service.get_file_metadata(file_id)
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/directories/{folder_id}/files")
async def list_directory_files(
    folder_id: str, 
    age_group: str = None,
    category: str = None,
    risk_level: str = None,
    department: str = None,
    page: int = 1,
    per_page: int = 100
):
    """List files in a specific directory with filtering options."""
    try:
        cached_result = scan_cache.get_cached_result(folder_id)
        if not cached_result:
            # No cache, so fetch, analyze, and cache
            files = await drive_service.list_directory(folder_id, per_page, recursive=True)
            results = await scan_files(source='gdrive', path_or_drive_id=folder_id)
            scan_cache.update_cache(folder_id, results)
            cached_result = results
            
        # Get all files from the flattened structure
        all_files = cached_result.get("files", [])
        
        # Apply filters
        filtered_files = all_files
        
        # Filter by age group if specified
        if age_group:
            filtered_files = [f for f in filtered_files if f.get("ageGroup") == age_group]
            
        # Filter by sensitivity category if specified
        if category:
            filtered_files = [f for f in filtered_files if f.get("sensitiveCategories") and category in f.get("sensitiveCategories", [])]
            
        # Filter by risk level if specified
        if risk_level:
            filtered_files = [f for f in filtered_files if f.get("riskLevelLabel") == risk_level]
            
        # Filter by department if specified
        if department:
            filtered_files = [f for f in filtered_files if f.get("department") == department]
        
        # Calculate pagination
        total_files = len(filtered_files)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_files = filtered_files[start_idx:end_idx]
        
        return {
            "files": paginated_files,
            "total": total_files,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_files + per_page - 1) // per_page
        }
    except Exception as e:
        logger.error(f"Error listing directory files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def initialize_response_structure():
    """Initialize the simplified response structure."""
    return {
        "files": [],
        "stats": {
            "total_documents": 0,
            "total_sensitive": 0,
            "by_file_type": {
                "documents": 0,
                "spreadsheets": 0,
                "presentations": 0,
                "pdfs": 0,
                "images": 0,
                "videos": 0,
                "audio": 0,
                "archives": 0,
                "code": 0,
                "others": 0
            },
            "by_sensitivity": {
                "pii": 0,
                "financial": 0,
                "legal": 0,
                "confidential": 0
            },
            "by_age_group": {
                "moreThanThreeYears": 0,
                "oneToThreeYears": 0,
                "lessThanOneYear": 0
            },
            "by_risk_level": {
                "high": 0,
                "medium": 0,
                "low": 0
            },
            "by_department": {}  # Will be populated with department counts
        },
        "scan_complete": False,
        "processed_files": 0,
        "total_files": 0,
        "failed_files": []
    }

@router.post("/directories/{folder_id}/analyze")
async def analyze_directory(
    folder_id: str,
    background_tasks: BackgroundTasks,
    drive_service: GoogleDriveService = Depends(get_current_user),
):
    try:
        # Fetch directory metadata to include in response
        directory_metadata = None
        try:
            directory_metadata = await drive_service.get_file_metadata(folder_id)
        except Exception as e:
            logger.warning(f"Could not fetch directory metadata for {folder_id}: {e}")
        
        # Check cache first
        cached_result = scan_cache.get_cached_result(folder_id)
        if cached_result:
            logger.info(f"Using cached result for directory {folder_id}")
            # Add directory metadata to cached result if available
            if directory_metadata:
                cached_result["directory"] = {
                    "id": folder_id,
                    "name": directory_metadata.get("name", folder_id)
                }
            return cached_result

        # Initialize response structure
        response = initialize_response_structure()
        
        # Add directory metadata to response
        if directory_metadata:
            response["directory"] = {
                "id": folder_id,
                "name": directory_metadata.get("name", folder_id)
            }
        
        # Get files in directory
        try:
            files = await drive_service.list_directory(folder_id, recursive=True)
        except Exception as e:
            logger.error(f"Error listing directory: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error listing directory: {str(e)}"
            )
            
        if not files:
            return response
        
        # Process files using the scanner
        try:
            response = await scan_files(source='gdrive', path_or_drive_id=folder_id)
            response["scan_complete"] = True
            
            # Ensure directory metadata is in response
            if directory_metadata:
                response["directory"] = {
                    "id": folder_id,
                    "name": directory_metadata.get("name", folder_id)
                }
            
            # Cache the results
            scan_cache.update_cache(folder_id, response)
            
            # DEBUG: Print sensitive files data being returned
            logger.info("=== DEBUG: Sensitive files data being returned ===")
            sensitive_files = [f for f in response["files"] if f.get("sensitiveCategories")]
            logger.info(f"Total files: {len(response['files'])}, Sensitive files: {len(sensitive_files)}")
            
            # Log risk distribution
            risk_counts = {
                "high": sum(1 for f in response["files"] if f.get("riskLevelLabel") == "high"),
                "medium": sum(1 for f in response["files"] if f.get("riskLevelLabel") == "medium"),
                "low": sum(1 for f in response["files"] if f.get("riskLevelLabel") == "low")
            }
            logger.info(f"Risk distribution: High={risk_counts['high']}, Medium={risk_counts['medium']}, Low={risk_counts['low']}")
            
            # Log sample files from each category
            for category in ["pii", "financial", "legal", "confidential"]:
                category_files = [f for f in response["files"] if f.get("sensitiveCategories") and category in f.get("sensitiveCategories", [])]
                if category_files:
                    sample = category_files[0]
                    logger.info(f"Category {category}: {len(category_files)} files, Sample: {sample.get('name')} - Risk: {sample.get('riskLevel')} ({sample.get('riskLevelLabel')})")
            
            logger.info("=== END DEBUG ===")
            
            # Send notifications if issues found (only on NEW scans, not cached)
            # Use BackgroundTasks to ensure notification completes even after response
            background_tasks.add_task(
                _trigger_notifications,
                directory_id=folder_id,
                drive_service=drive_service,
                scan_results=response
            )
            logger.info(f"Scheduled notification task for directory {folder_id}")
            
            return response
        except Exception as e:
            logger.error(f"Error scanning files: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error scanning files: {str(e)}"
            )
        
    except Exception as e:
        logger.error(f"Error analyzing directory: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing directory: {str(e)}"
        )

@router.get("/directories/{folder_id}/categorize")
async def categorize_directory(folder_id: str, page_size: int = 100):
    """Get categorized files in a specific directory."""
    if not drive_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated. Please authenticate first.")
    try:
        categories = drive_service.categorize_directory(folder_id, page_size)
        return {
            "folder_id": folder_id,
            "categories": categories
        }
    except Exception as e:
        logger.error(f"Error categorizing directory: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/directories", response_model=List[Dict])
async def list_directories(
    drive_service: GoogleDriveService = Depends(get_current_user)
) -> List[Dict]:
    """List all directories in the user's drive."""
    try:
        directories = await drive_service.list_directories()
        return directories
    except asyncio.TimeoutError:
        logger.error("Timeout listing directories")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Operation timed out"
        )
    except Exception as e:
        logger.error(f"Error listing directories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

# Debug endpoint to receive frontend debug messages
@router.post("/debug/log")
async def debug_log(request: Request):
    """Debug endpoint to receive frontend debug messages and log them to terminal"""
    try:
        data = await request.json()
        if 'data' in data:
            logger.info(f"Frontend Debug: {data['data']}")
        return {"status": "logged"}
    except Exception as e:
        logger.error(f"Error logging debug message: {e}")
        return {"status": "error"}

# Department management endpoints
@router.get("/departments")
async def list_departments():
    """List all available departments"""
    departments = [
        {"id": "sales-and-marketing", "name": "Sales & Marketing", "description": "Sales and marketing activities"},
        {"id": "operations", "name": "Operations", "description": "Administrative and operational tasks"},
        {"id": "r-and-d", "name": "R&D", "description": "Research and development"},
        {"id": "others", "name": "Others", "description": "Other departments and unclassified files"}
    ]
    return departments

@router.post("/files/{file_id}/department")
async def set_file_department(
    file_id: str, 
    department_id: str,
    drive_service: GoogleDriveService = Depends(get_current_user)
):
    """Set the department for a specific file"""
    try:
        # Get all cached results
        cached_dirs = scan_cache.get_cached_directories()
        
        # Find the file in any of the cached results
        file_found = False
        for dir_id in cached_dirs + ['drive']:
            cached_result = scan_cache.get_cached_result(dir_id)
            if cached_result and "files" in cached_result:
                for i, file in enumerate(cached_result["files"]):
                    if file.get("id") == file_id:
                        # Update the file's department
                        cached_result["files"][i]["department"] = department_id
                        
                        # Update department stats
                        if "by_department" not in cached_result["stats"]:
                            cached_result["stats"]["by_department"] = {}
                        
                        # Increment count for new department
                        if department_id not in cached_result["stats"]["by_department"]:
                            cached_result["stats"]["by_department"][department_id] = 0
                        cached_result["stats"]["by_department"][department_id] += 1
                        
                        # Update the cache
                        scan_cache.update_cache(dir_id, cached_result)
                        file_found = True
                        break
                
                # If file was found in this cache, no need to check others
                if file_found:
                    break
        
        if not file_found:
            raise HTTPException(status_code=404, detail=f"File {file_id} not found in any cached results")
        
        return {"status": "success", "file_id": file_id, "department": department_id}
    except Exception as e:
        logger.error(f"Error setting file department: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/departments/{department_id}/files")
async def list_department_files(
    department_id: str,
    page: int = 1,
    per_page: int = 20
):
    """List all files assigned to a specific department"""
    try:
        # Get all cached results
        cached_dirs = scan_cache.get_cached_directories()
        
        # Collect all files from this department
        department_files = []
        
        # Check drive cache first
        drive_cache = scan_cache.get_cached_result('drive')
        if drive_cache and "files" in drive_cache:
            department_files.extend([
                f for f in drive_cache["files"] 
                if f.get("department") == department_id
            ])
        
        # Then check all directory caches
        for dir_id in cached_dirs:
            cached_result = scan_cache.get_cached_result(dir_id)
            if cached_result and "files" in cached_result:
                department_files.extend([
                    f for f in cached_result["files"] 
                    if f.get("department") == department_id
                ])
        
        # Deduplicate files by ID
        unique_files = {}
        for file in department_files:
            if file["id"] not in unique_files:
                unique_files[file["id"]] = file
        
        department_files = list(unique_files.values())
        
        # Calculate pagination
        total_files = len(department_files)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_files = department_files[start_idx:end_idx]
        
        return {
            "files": paginated_files,
            "total": total_files,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_files + per_page - 1) // per_page
        }
    except Exception as e:
        logger.error(f"Error listing department files: {e}")
        raise HTTPException(status_code=500, detail=str(e))
