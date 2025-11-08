from typing import Dict, List, Optional
from .google_drive import GoogleDriveService
from .scan_cache_service import ScanCacheService
from .file_scanner_with_json import scan_files
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, drive_service: GoogleDriveService):
        self.drive_service = drive_service
        # Use per-user cache if user_id is available, otherwise use global cache (legacy mode)
        user_id = drive_service.user_id if hasattr(drive_service, 'user_id') and drive_service.user_id else None
        self.scan_cache = ScanCacheService(user_id=user_id)
        self.commands = {
            "help": self._handle_help,
            "list": self._handle_list,
            "inactive": self._handle_inactive,
            "find": self._handle_find,
            "status": self._handle_status,
            "directories": self._handle_directories,
            "categorize": self._handle_categorize,
            "analyze": self._handle_analyze,
            "summary": self._handle_summary,
            "risks": self._handle_risks
        }

    async def process_command(self, command: str) -> Dict:
        """Process a command from the API endpoint."""
        logger.info(f"Processing command: {command}")
        return await self.process_message(command)

    async def process_message(self, message: str) -> Dict:
        """Process a user message and return a response."""
        original_message = message.strip()
        lower_message = original_message.lower() # Lowercase version for command matching
        
        # Check if it's a command
        for cmd, handler in self.commands.items():
            # Match against the lowercase version
            if lower_message.startswith(cmd):
                # Extract arguments from the *original* message to preserve case
                # Add a space check to handle commands with and without args correctly
                if len(original_message) > len(cmd) and original_message[len(cmd)] == ' ':
                    arguments = original_message[len(cmd):].strip()
                elif len(original_message) == len(cmd):
                     arguments = "" # Command was entered with no arguments
                else:
                    # Command doesn't match exactly (e.g., typed 'listx' when command is 'list')
                    # This case might not be strictly needed if startswith is sufficient,
                    # but added for robustness. Let default handle it.
                    continue 
                    
                return await handler(arguments) # Pass original-case arguments
        
        # Default response for unknown commands or commands needing arguments but not provided
        logger.warning(f"Unknown command or format: {original_message}")
        return {
            "type": "text",
            "content": "I'm not sure how to help with that, or the command format was incorrect. Type 'help' to see available commands and formats."
        }

    async def _handle_help(self, _: str) -> Dict:
        """Handle the help command."""
        return {
            "type": "text",
            "content": """I can help you with the following commands:
- help: Show this help message
- list: List recent files
- inactive: Show inactive files
- find <filename>: Search for a specific file
- status: Check authentication status
- directories: List your top-level folders
- categorize <folder_id>: Show a summary of a folder's contents
- analyze: Analyze drive statistics
- summary: Get a summary of drive statistics
- risks: Identify potential risks in your drive

Try any of these commands!"""
        }

    async def _handle_list(self, _: str) -> Dict:
        """Handle the list command."""
        if not await self.drive_service.is_authenticated():
            return {
                "type": "text",
                "content": "Please authenticate first using the /auth/url endpoint"
            }
        
        try:
            # Get directories from the API
            directories = await self.drive_service.list_directories()
            
            if not directories:
                return {
                    "type": "text",
                    "content": "No directories found in your drive."
                }
            
            response = "Available Directories 📁\n\n"
            for directory in directories:
                response += f"- {directory['name']} (ID: {directory['id']})\n"
            
            return {
                "type": "text",
                "content": response
            }
        except Exception as e:
            logger.error(f"Error listing directories: {str(e)}", exc_info=True)
            return {
                "type": "text",
                "content": f"Sorry, I encountered an error: {str(e)}"
            }

    async def _handle_inactive(self, _: str) -> Dict:
        """Handle the inactive command."""
        if not self.drive_service.is_authenticated():
            return {
                "type": "text",
                "content": "Please authenticate first using the /auth/url endpoint"
            }
        
        try:
            files = self.drive_service.get_inactive_files()
            if not files:
                return {
                    "type": "text",
                    "content": "No inactive files found."
                }
            
            response = "Here are your inactive files:\n"
            for file in files:
                response += f"- {file['name']} (Last modified: {file['modifiedTime']})\n"
            
            return {
                "type": "text",
                "content": response
            }
        except Exception as e:
            logger.error(f"Error listing inactive files: {str(e)}")
            return {
                "type": "text",
                "content": f"Sorry, I encountered an error: {str(e)}"
            }

    async def _handle_find(self, query: str) -> Dict:
        """Handle the find command."""
        if not query:
            return {
                "type": "text",
                "content": "Please provide a search term. Example: find report.pdf"
            }
        
        if not self.drive_service.is_authenticated():
            return {
                "type": "text",
                "content": "Please authenticate first using the /auth/url endpoint"
            }
        
        try:
            files = self.drive_service.list_files(page_size=10)
            matching_files = [
                file for file in files 
                if query.lower() in file['name'].lower()
            ]
            
            if not matching_files:
                return {
                    "type": "text",
                    "content": f"No files found matching '{query}'"
                }
            
            response = f"Found {len(matching_files)} matching files:\n"
            for file in matching_files:
                response += f"- {file['name']} (Last modified: {file['modifiedTime']})\n"
            
            return {
                "type": "text",
                "content": response
            }
        except Exception as e:
            logger.error(f"Error searching files: {str(e)}")
            return {
                "type": "text",
                "content": f"Sorry, I encountered an error: {str(e)}"
            }

    async def _handle_status(self, _: str) -> Dict:
        """Handle the status command."""
        is_authenticated = self.drive_service.is_authenticated()
        return {
            "type": "text",
            "content": "Authenticated" if is_authenticated else "Not authenticated. Please authenticate first using the /auth/url endpoint"
        }

    async def _handle_directories(self, _: str) -> Dict:
        """Handle the directories command."""
        if not await self.drive_service.is_authenticated():
            return {
                "type": "text",
                "content": "Please authenticate first using the /auth/url endpoint"
            }
        
        try:
            directories = await self.drive_service.list_directories()
            if not directories:
                return {
                    "type": "text",
                    "content": "No top-level directories found that you own."
                }
            
            response = "Here are your top-level directories:\n"
            for directory in directories:
                response += f"- {directory['name']} (ID: {directory['id']})\n"
            
            return {
                "type": "text",
                "content": response
            }
        except Exception as e:
            logger.error(f"Error listing directories: {str(e)}", exc_info=True)
            return {
                "type": "text",
                "content": f"Sorry, I encountered an error listing directories: {str(e)}"
            }

    async def _handle_categorize(self, folder_id: str) -> Dict:
        """Handle the categorize command."""
        if not folder_id:
            return {
                "type": "text",
                "content": "Please provide a folder ID. Example: categorize 1A2B3C..."
            }
            
        if not self.drive_service.is_authenticated():
            return {
                "type": "text",
                "content": "Please authenticate first using the /auth/url endpoint"
            }
            
        try:
            categories = self.drive_service.categorize_directory(folder_id)
            summary = categories.get('summary', {})
            
            if not summary or summary.get('total_files', 0) == 0:
                 return {
                    "type": "text",
                    "content": f"Could not find or categorize folder with ID '{folder_id}'. It might be empty or inaccessible."
                }

            response = f"Summary for folder ID {folder_id}:\n"
            response += f"- Total Files: {summary.get('total_files', 0)}\n"
            response += f"- Total Size: {summary.get('total_size', 0)} bytes\n"
            response += "- Files by Type:\n"
            for type_name, count in summary.get('by_type', {}).items():
                if count > 0:
                    response += f"    - {type_name.capitalize()}: {count}\n"
            response += f"- Recent Files (last 30 days): {summary.get('recent_files', 0)}\n"
            response += f"- Large Files (>10MB): {summary.get('large_files', 0)}\n"
            response += f"- Number of Owners: {summary.get('owners', 0)}\n"
            
            return {
                "type": "text",
                "content": response
            }
        except Exception as e:
            logger.error(f"Error categorizing directory {folder_id}: {str(e)}", exc_info=True)
            return {
                "type": "text",
                "content": f"Sorry, I encountered an error categorizing the directory: {str(e)}"
            }

    async def _handle_analyze(self, _: str) -> Dict:
        """Handle the analyze command."""
        return {
            "type": "text",
            "content": "Analyze command not implemented yet."
        }

    async def _handle_summary(self, _: str) -> Dict:
        """Handle the summary command."""
        return {
            "type": "text",
            "content": "Summary command not implemented yet."
        }

    async def _handle_risks(self, _: str) -> Dict:
        """Handle the risks command."""
        return {
            "type": "text",
            "content": "Risks command not implemented yet."
        }

    async def get_drive_stats(self) -> Dict:
        """Get overall drive statistics."""
        logger.info("Starting get_drive_stats")
        if not await self.drive_service.is_authenticated():
            logger.error("Not authenticated with Google Drive")
            raise ValueError("Not authenticated with Google Drive")

        try:
            logger.info("Fetching files from Google Drive")
            # Get all files
            files_response = await self.drive_service.list_files(page_size=1000)
            files = files_response.get('files', [])
            logger.info(f"Retrieved {len(files)} files from Google Drive")
            
            # Calculate statistics
            total_files = len(files)
            sensitive_files = 0
            old_files = 0
            total_size = 0
            
            # Calculate cutoff date for old files (3 years)
            cutoff_date = datetime.utcnow() - timedelta(days=3*365)
            
            logger.info("Processing files for statistics")
            for file in files:
                # Calculate total size
                if 'size' in file:
                    total_size += int(file.get('size', 0))
                
                # Check for old files
                modified_time = datetime.fromisoformat(file['modifiedTime'].rstrip('Z'))
                if modified_time < cutoff_date:
                    old_files += 1
                
                # Check for sensitive files (placeholder - implement actual detection)
                if any(keyword in file['name'].lower() for keyword in ['password', 'secret', 'confidential']):
                    sensitive_files += 1
            
            # Calculate storage usage percentage (placeholder - implement actual calculation)
            storage_used_percentage = min((total_size / (1024 * 1024 * 1024)) * 100, 100)  # Assuming 1GB total storage
            
            stats = {
                'total_files': total_files,
                'sensitive_files': sensitive_files,
                'old_files': old_files,
                'storage_used_percentage': storage_used_percentage
            }
            logger.info(f"Calculated stats: {stats}")
            return stats
        except Exception as e:
            logger.error(f"Error getting drive stats: {str(e)}", exc_info=True)
            raise

    async def analyze_directory(self, directory: str) -> Dict:
        """Analyze a directory for file types and sensitive information."""
        try:
            # Check cache first
            cached_result = self.scan_cache.get_cached_result(directory)
            if cached_result:
                logger.info(f"Using cached result for directory {directory}")
                return cached_result

            # Get files in directory
            files = await self.drive_service.list_directory(directory, recursive=True)
            
            # Process files using the scanner
            results = await scan_files(source='gdrive', path_or_drive_id=directory, drive_service=self.drive_service)
            
            # Cache the results
            self.scan_cache.update_cache(directory, results)
            logger.info(f"Cached scan results for directory {directory}")
            
            return results
        except Exception as e:
            logger.error(f"Error analyzing directory: {str(e)}", exc_info=True)
            raise

    def _calculate_storage_percentage(self, files: List[Dict]) -> float:
        """Calculate storage usage percentage."""
        total_size = sum(int(f.get('size', 0)) for f in files)
        # Assuming 15GB free tier limit for Google Drive
        storage_limit = 15 * 1024 * 1024 * 1024  
        return min(round((total_size / storage_limit) * 100, 2), 100)

    def _is_old_file(self, file: Dict) -> bool:
        """Check if a file is older than 3 years."""
        modified_time = datetime.fromisoformat(file['modifiedTime'].rstrip('Z'))
        return (datetime.utcnow() - modified_time).days > 1095  # 3 years in days

    def _summarize_file_types(self, results: Dict) -> Dict:
        """Summarize file types across all age categories."""
        summary = {}
        for file_type in results['moreThanThreeYears']['file_types'].keys():
            total = (len(results['moreThanThreeYears']['file_types'][file_type]) +
                    len(results['oneToThreeYears']['file_types'][file_type]) +
                    len(results['lessThanOneYear']['file_types'][file_type]))
            if total > 0:
                summary[file_type] = total
        return summary

    async def get_summary_stats(self, directory: str = None) -> Dict:
        """Get summary statistics for a directory or entire drive."""
        try:
            # Check cache first
            target_id = directory if directory else 'drive'
            cached_result = self.scan_cache.get_cached_result(target_id)
            if cached_result:
                logger.info(f"Using cached result for {target_id}")
                return cached_result

            # Get files either from specific directory or entire drive
            if directory:
                files = await self.drive_service.list_directory(directory, recursive=True)
            else:
                # For entire drive, use list_files
                files_response = await self.drive_service.list_files(page_size=1000)
                files = files_response.get('files', [])

            logger.info(f"Retrieved {len(files)} files for analysis")

            # Process files using the scanner
            results = await scan_files(source='gdrive', path_or_drive_id=directory if directory else 'drive', drive_service=self.drive_service)
            
            # Create a summary of the results
            summary = {
                'total_files': results['total_files'],
                'sensitive_files': results['total_sensitive_files'],
                'storage_used_percentage': self._calculate_storage_percentage(files),
                'old_files': len([f for f in files if self._is_old_file(f)]),
                'file_types': self._summarize_file_types(results),
                'age_distribution': {
                    'moreThanThreeYears': results['moreThanThreeYears']['total_documents'],
                    'oneToThreeYears': results['oneToThreeYears']['total_documents'],
                    'lessThanOneYear': results['lessThanOneYear']['total_documents']
                },
                'sensitive_info': {
                    'pii': len(results['moreThanThreeYears']['sensitive_info']['pii'] +
                              results['oneToThreeYears']['sensitive_info']['pii'] +
                              results['lessThanOneYear']['sensitive_info']['pii']),
                    'financial': len(results['moreThanThreeYears']['sensitive_info']['financial'] +
                                   results['oneToThreeYears']['sensitive_info']['financial'] +
                                   results['lessThanOneYear']['sensitive_info']['financial']),
                    'legal': len(results['moreThanThreeYears']['sensitive_info']['legal'] +
                               results['oneToThreeYears']['sensitive_info']['legal'] +
                               results['lessThanOneYear']['sensitive_info']['legal']),
                    'confidential': len(results['moreThanThreeYears']['sensitive_info']['confidential'] +
                                      results['oneToThreeYears']['sensitive_info']['confidential'] +
                                      results['lessThanOneYear']['sensitive_info']['confidential'])
                }
            }

            # Cache the results
            self.scan_cache.update_cache(target_id, summary)
            logger.info(f"Cached summary stats for {target_id}")
            
            return summary

        except Exception as e:
            logger.error(f"Error getting summary stats: {str(e)}", exc_info=True)
            raise

    async def analyze_risks(self, directory: str) -> Dict:
        """Analyze risks in a directory."""
        try:
            # Check cache first
            cached_result = self.scan_cache.get_cached_result(directory)
            if cached_result:
                logger.info(f"Using cached result for directory {directory}")
                return cached_result

            # Get files in directory
            files = await self.drive_service.list_directory(directory, recursive=True)
            
            # Process files for risk analysis
            results = await scan_files(source='gdrive', path_or_drive_id=directory, drive_service=self.drive_service)
            
            # Cache the results
            self.scan_cache.update_cache(directory, results)
            logger.info(f"Cached risk analysis for directory {directory}")
            
            return results
        except Exception as e:
            logger.error(f"Error analyzing risks: {str(e)}", exc_info=True)
            raise 