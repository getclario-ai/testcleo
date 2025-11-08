from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from ..core.config import settings
from .chat_service import ChatService
from ..db.models import SlackUser, WebUser
from .google_drive import GoogleDriveService
from sqlalchemy.orm import Session
import logging
import json
import ssl
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
import re

logger = logging.getLogger(__name__)

# Configure SSL certificates for macOS compatibility
# This ensures Slack API calls work on macOS where Python might not find system certificates
try:
    import certifi
    # Set SSL certificate file environment variable for urllib (used by Slack SDK)
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    
    # Also patch ssl._create_default_https_context to use certifi
    # This ensures urllib uses certifi certificates
    _original_create_context = ssl._create_default_https_context
    
    def _create_https_context_certifi(*args, **kwargs):
        ctx = _original_create_context(*args, **kwargs)
        ctx.load_verify_locations(certifi.where())
        return ctx
    
    ssl._create_default_https_context = _create_https_context_certifi
    
    logger.debug(f"Configured SSL certificates using certifi: {certifi.where()}")
except ImportError:
    logger.warning("certifi not available - SSL certificate verification may fail on macOS")
    logger.warning("Install certifi: pip install certifi")
    # On macOS, try to use the system certificates
    # If this fails, user should run: /Applications/Python\ 3.12/Install\ Certificates.command
except Exception as e:
    logger.warning(f"Could not configure SSL certificates: {e}")

class SlackMessageTemplates:
    @staticmethod
    def status_message(health_score: int, urgent_items: List[str], dashboard_url: str) -> Dict:
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Drive Health Status 🏥"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Health Score:* {health_score}/100"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*Urgent Items:*\n" + 
                            "\n".join(f"• {item}" for item in urgent_items)}
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Details"},
                            "url": dashboard_url
                        }
                    ]
                }
            ]
        }


    @staticmethod
    def help_message() -> Dict:
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Zo - Your Drive Assistant 🤖"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": 
                        "*Available Commands:*\n\n" +
                        "• `/zo help` - Show this help message\n" +
                        "• `/zo connect` - Connect your Google Drive\n" +
                        "• `/zo list` - List your directories\n" +
                        "• `/zo scan [directory]` - Scan a directory and show files by age"
                    }
                }
            ]
        }

class SlackService:
    def __init__(self, chat_service: ChatService, db: Session):
        # Initialize Slack client
        # SSL certificates are configured at module level via environment variables
        self.client = WebClient(token=settings.SLACK_BOT_TOKEN)
        
        self.chat_service = chat_service
        self.db = db
        self.templates = SlackMessageTemplates()
        self.dashboard_base_url = settings.FRONTEND_URL
        self._bot_info_cache = None
        # Cache for Slack user emails: {slack_user_id: (email, cached_at)}
        self._email_cache: Dict[str, tuple[str, datetime]] = {}
        self._email_cache_ttl = timedelta(hours=1)  # Cache email for 1 hour
    
    def get_bot_name(self) -> str:
        """
        Get the bot's display name for notifications/invites.
        Caches the result to avoid repeated API calls.
        """
        if self._bot_info_cache is None:
            try:
                result = self.client.auth_test()
                self._bot_info_cache = result.get("user", "Zo")
                logger.info(f"Bot name retrieved: {self._bot_info_cache}")
            except Exception as e:
                logger.warning(f"Could not get bot name from Slack API: {e}")
                self._bot_info_cache = "Zo"  # Default fallback
        return self._bot_info_cache
        
    async def is_user_authenticated(self, user_id: str) -> bool:
        """Check if a user is authenticated with Google Drive"""
        user = self.db.query(SlackUser).filter(SlackUser.slack_user_id == user_id).first()
        return user is not None and user.google_drive_token is not None
        
    async def store_google_tokens(self, user_id: str, access_token: str, refresh_token: str, expires_in: int) -> None:
        """Store Google Drive tokens for a Slack user"""
        try:
            user = self.db.query(SlackUser).filter(SlackUser.slack_user_id == user_id).first()
            if not user:
                user = SlackUser(slack_user_id=user_id)
                self.db.add(user)
            
            user.google_drive_token = access_token
            user.google_drive_refresh_token = refresh_token
            user.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            self.db.commit()
            logger.info(f"Stored Google Drive tokens for user {user_id}")
        except Exception as e:
            logger.error(f"Error storing Google Drive tokens: {str(e)}")
            self.db.rollback()
            raise
            
    async def get_google_tokens(self, user_id: str) -> dict:
        """Retrieve Google Drive tokens for a Slack user"""
        try:
            user = self.db.query(SlackUser).filter(SlackUser.slack_user_id == user_id).first()
            if not user or not user.google_drive_token:
                return None
                
            # Check if token is expired
            if user.token_expires_at and user.token_expires_at <= datetime.utcnow():
                # Token is expired, we'll need to refresh it
                return {
                    "access_token": user.google_drive_token,
                    "refresh_token": user.google_drive_refresh_token,
                    "expires_at": user.token_expires_at,
                    "needs_refresh": True
                }
                
            return {
                "access_token": user.google_drive_token,
                "refresh_token": user.google_drive_refresh_token,
                "expires_at": user.token_expires_at,
                "needs_refresh": False
            }
        except Exception as e:
            logger.error(f"Error retrieving Google Drive tokens: {str(e)}")
            return None
            
    async def clear_google_tokens(self, user_id: str) -> None:
        """Clear Google Drive tokens for a Slack user"""
        try:
            user = self.db.query(SlackUser).filter(SlackUser.slack_user_id == user_id).first()
            if user:
                user.google_drive_token = None
                user.google_drive_refresh_token = None
                user.token_expires_at = None
                self.db.commit()
                logger.info(f"Cleared Google Drive tokens for user {user_id}")
        except Exception as e:
            logger.error(f"Error clearing Google Drive tokens: {str(e)}")
            self.db.rollback()
            raise
    
    async def get_slack_user_email(self, slack_user_id: str) -> Optional[str]:
        """Get Slack user's email from Slack API (with caching)"""
        # Check cache first
        if slack_user_id in self._email_cache:
            email, cached_at = self._email_cache[slack_user_id]
            if datetime.utcnow() - cached_at < self._email_cache_ttl:
                logger.debug(f"Using cached email for Slack user {slack_user_id}: {email}")
                return email
            else:
                # Cache expired, remove it
                del self._email_cache[slack_user_id]
        
        # Cache miss or expired - fetch from Slack API
        try:
            response = self.client.users_info(user=slack_user_id)
            if response["ok"]:
                user_info = response["user"]
                email = user_info.get("profile", {}).get("email")
                if email:
                    # Cache the email
                    self._email_cache[slack_user_id] = (email, datetime.utcnow())
                    logger.info(f"Retrieved and cached Slack user email for {slack_user_id}: {email}")
                    return email
                else:
                    logger.warning(f"No email found for Slack user {slack_user_id}")
                    return None
            else:
                logger.error(f"Slack API error getting user info: {response.get('error')}")
                return None
        except SlackApiError as e:
            logger.error(f"Slack API error getting user email: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting Slack user email: {str(e)}", exc_info=True)
            return None
    
    async def get_user_drive_service(self, slack_user_id: str) -> Optional[GoogleDriveService]:
        """
        Get authenticated GoogleDriveService for a Slack user.
        Returns None if user is not linked or not authenticated.
        """
        try:
            # Get Slack user's email from Slack API
            slack_email = await self.get_slack_user_email(slack_user_id)
            if not slack_email:
                logger.warning(f"Could not get email for Slack user {slack_user_id}")
                return None
            
            # Look up WebUser by email
            web_user = self.db.query(WebUser).filter(WebUser.email == slack_email).first()
            if not web_user:
                logger.warning(f"No WebUser found for email {slack_email} (Slack user {slack_user_id})")
                return None
            
            if not web_user.google_refresh_token:
                logger.warning(f"WebUser {web_user.email} has no Google Drive credentials")
                return None
            
            # Create GoogleDriveService with user's credentials
            drive_service = GoogleDriveService(user_id=web_user.id)
            credentials = drive_service.load_credentials_from_db(self.db, web_user.google_refresh_token)
            if not credentials:
                logger.error(f"Failed to load credentials for WebUser {web_user.email}")
                return None
            
            logger.info(f"Created authenticated drive_service for Slack user {slack_user_id} (email: {slack_email}, web_user_id: {web_user.id})")
            return drive_service
            
        except Exception as e:
            logger.error(f"Error getting user drive_service for Slack user {slack_user_id}: {str(e)}", exc_info=True)
            return None
    
    async def get_user_chat_service(self, slack_user_id: str) -> Optional[ChatService]:
        """
        Get user-specific ChatService for a Slack user.
        Returns None if user is not linked or not authenticated.
        """
        drive_service = await self.get_user_drive_service(slack_user_id)
        if not drive_service:
            return None
        return ChatService(drive_service=drive_service)
    
    def _get_auth_error_message(self) -> Dict:
        """Get standard authentication error message"""
        return {
            "response_type": "ephemeral",
            "text": f"❌ Not authenticated. Please link your Slack account to your Google Drive account.\n\nVisit: {self.dashboard_base_url} to authenticate."
        }
    
    async def _with_user_chat_service(
        self,
        user_id: str,
        handler: Callable,
        args: List[str],
        channel_id: str
    ) -> Dict:
        """
        Helper method to get user_chat_service and call handler with it.
        Returns authentication error if user is not authenticated.
        
        Args:
            user_id: Slack user ID
            handler: Handler function to call with user_chat_service
            args: Command arguments
            channel_id: Slack channel ID
            
        Returns:
            Dict response from handler or authentication error
        """
        user_chat_service = await self.get_user_chat_service(user_id)
        if not user_chat_service:
            return self._get_auth_error_message()
        return await handler(args, user_id, channel_id, user_chat_service)
        
    async def handle_mention(self, event_data: dict) -> None:
        """Handle app mention events"""
        try:
            # Extract channel and text from the event
            channel_id = event_data.get("channel")
            text = event_data.get("text", "")
            user = event_data.get("user")
            
            # Remove the bot mention from the text
            # Format is typically <@BOT_ID> command
            command = " ".join(text.split()[1:]) if text else ""
            
            logger.debug(f"Processing command from mention: {command}")
            
            if not command:
                await self.send_message(channel_id, "How can I help you? Try typing 'help' to see available commands.")
                return
                
            # Process the command through our chat service
            response = await self.chat_service.process_message(command)
            
            # Send the response back to Slack
            await self.send_message(channel_id, response.get("content", "Sorry, I couldn't process that command."))
            
        except Exception as e:
            logger.error(f"Error handling mention: {str(e)}", exc_info=True)
            await self.send_message(channel_id, f"Sorry, I encountered an error processing your request: {str(e)}")
    
    async def handle_slash_command(self, command_data: dict) -> dict:
        """Handle slash commands"""
        try:
            logger.debug(f"Received command data: {command_data}")
            
            command_text = command_data.get("text", "").strip()
            channel_id = command_data.get("channel_id")
            user_id = command_data.get("user_id")
            
            if not command_text:
                return self.templates.help_message()

            # Parse command and arguments
            parts = command_text.split()
            command = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []

            # Command handlers for /zo commands
            # Handlers that require authentication
            authenticated_handlers = {
                "list": self._handle_list,
                "scan": self._handle_scan
            }
            
            # Handlers that don't require authentication
            unauthenticated_handlers = {
                "help": self._handle_help,
                "connect": self._handle_connect
            }
            
            # Check if command requires authentication
            if command in authenticated_handlers:
                handler = authenticated_handlers[command]
                return await self._with_user_chat_service(user_id, handler, args, channel_id)
            elif command in unauthenticated_handlers:
                handler = unauthenticated_handlers[command]
                return await handler(args, user_id, channel_id)
            else:
                return {
                    "response_type": "ephemeral",
                    "text": f"Unknown command: {command}. Try `/zo help` for available commands."
                }

        except Exception as e:
            logger.error(f"Error handling slash command: {str(e)}", exc_info=True)
            return {
                "response_type": "ephemeral",
                "text": f"Sorry, I encountered an error processing your command: {str(e)}"
            }

    async def _handle_help(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        return self.templates.help_message()

    async def _handle_connect(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        """Handle Google Drive connection"""
        try:
            # For testing: using shared Google Drive session from web dashboard
            # Check if the main drive service is authenticated
            is_authenticated = await self.chat_service.drive_service.is_authenticated()
            
            if is_authenticated:
                return {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "✅ Connected to Google Drive! (using shared session for testing)"}
                        }
                    ]
                }
            
            return {
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": 
                            "❌ *Not Connected*\n\n" +
                            "Please authenticate via the web dashboard first:\n" +
                            f"{self.dashboard_base_url}"
                        }
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Error in connect command: {str(e)}", exc_info=True)
            return {"response_type": "ephemeral", "text": f"Error connecting: {str(e)}"}

    async def _handle_list(self, args: List[str], user_id: str, channel_id: str, user_chat_service: ChatService) -> Dict:
        """Handle /zo list command - List user's directories"""
        try:
            # Use the chat service's list handler
            response = await user_chat_service._handle_list("")
            
            # Convert the response to Slack format
            return {
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "Your Directories 📁"}
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": response["content"]}
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Error in list command: {str(e)}", exc_info=True)
            return {"response_type": "ephemeral", "text": f"Error listing directories: {str(e)}"}

    async def _handle_scan(self, args: List[str], user_id: str, channel_id: str, user_chat_service: ChatService) -> Dict:
        """Scan a directory and show files by age"""
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please specify a directory. Usage: `/zo scan [directory_id or name]`\n\nTip: Use `/zo list` to see available directories."
            }

        directory_input = " ".join(args)
        
        try:
            # Try to resolve directory name to ID if needed
            # This ensures we use the same cache key as the web dashboard
            directory = directory_input
            
            # If it looks like a name (not a long ID), try to find the ID
            if len(directory_input) < 20:  # IDs are typically longer
                try:
                    # Get list of directories using user-specific chat_service
                    response = await user_chat_service._handle_list("")
                    content = response.get("content", "")
                    
                    # Parse the directory list to find matching name
                    # Format is: "- DirectoryName (ID: 1a2b3c4d)"
                    for line in content.split('\n'):
                        match = re.search(rf'- (.+?) \(ID: (.+?)\)', line)
                        if match:
                            name, dir_id = match.groups()
                            if name.lower().strip() == directory_input.lower().strip():
                                directory = dir_id
                                logger.info(f"Resolved directory name '{directory_input}' to ID '{directory}'")
                                break
                except Exception as e:
                    logger.warning(f"Could not resolve directory name: {e}")
                    # Continue with original input
            
            # Check cache first for quick response (using user-specific cache)
            cached_result = user_chat_service.scan_cache.get_cached_result(directory)
            
            if cached_result:
                # We have cached data, return it immediately
                stats = cached_result.get('stats', {})
                by_age = stats.get('by_age_group', {})
                
                more_than_3y = by_age.get('moreThanThreeYears', 0)
                one_to_3y = by_age.get('oneToThreeYears', 0)
                less_than_1y = by_age.get('lessThanOneYear', 0)
                total = more_than_3y + one_to_3y + less_than_1y
                
                # Show the name if it was resolved, otherwise show the ID
                display_name = directory_input if directory != directory_input else directory
                
                return {
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": "Scan Results 📊 (cached)"}
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": 
                                f"*Directory:* {display_name}\n" +
                                f"*Total Files:* {total}\n\n" +
                                "*Files by Age:*\n" +
                                f"• More than 3 years: {more_than_3y}\n" +
                                f"• 1-3 years: {one_to_3y}\n" +
                                f"• Less than 1 year: {less_than_1y}"
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "View Full Dashboard"},
                                    "url": f"{self.dashboard_base_url}?directory={directory}"
                                }
                            ]
                        }
                    ]
                }
            else:
                # No cache - need to scan
                # Try to do a quick scan (with timeout)
                logger.info(f"Starting scan for directory: {directory}")
                
                # Start the scan in the background (will continue even if we timeout)
                import asyncio
                
                async def background_scan():
                    """Run scan in background and cache results"""
                    try:
                        logger.info(f"Background scan starting for: {directory}")
                        # Use user-specific chat_service for the scan
                        results = await user_chat_service.analyze_directory(directory)
                        logger.info(f"Background scan completed for: {directory}")
                        # Results are automatically cached by analyze_directory
                        return results
                    except Exception as e:
                        logger.error(f"Background scan failed for {directory}: {str(e)}", exc_info=True)
                        return None
                
                # Create background task that continues after we return
                scan_task = asyncio.create_task(background_scan())
                
                try:
                    # Try to wait for quick results
                    results = await asyncio.wait_for(scan_task, timeout=2.5)
                    
                    # Check if scan succeeded
                    if not results:
                        return {
                            "response_type": "ephemeral",
                            "text": f"Error: Could not scan directory '{directory}'. Please check the directory ID."
                        }
                    
                    # Scan completed quickly! Extract and return results
                    stats = results.get('stats', {})
                    by_age = stats.get('by_age_group', {})
                    
                    more_than_3y = by_age.get('moreThanThreeYears', 0)
                    one_to_3y = by_age.get('oneToThreeYears', 0)
                    less_than_1y = by_age.get('lessThanOneYear', 0)
                    total = more_than_3y + one_to_3y + less_than_1y
                    
                    # Show the name if it was resolved, otherwise show the ID
                    display_name = directory_input if directory != directory_input else directory
                    
                    return {
                        "blocks": [
                            {
                                "type": "header",
                                "text": {"type": "plain_text", "text": "Scan Results 📊"}
                            },
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": 
                                    f"*Directory:* {display_name}\n" +
                                    f"*Total Files:* {total}\n\n" +
                                    "*Files by Age:*\n" +
                                    f"• More than 3 years: {more_than_3y}\n" +
                                    f"• 1-3 years: {one_to_3y}\n" +
                                    f"• Less than 1 year: {less_than_1y}"
                                }
                            },
                            {
                                "type": "actions",
                                "elements": [
                                    {
                                        "type": "button",
                                        "text": {"type": "plain_text", "text": "View Full Dashboard"},
                                        "url": f"{self.dashboard_base_url}?directory={directory}"
                                    }
                                ]
                            }
                        ]
                    }
                except asyncio.TimeoutError:
                    # Scan is taking too long, but continues in background
                    logger.warning(f"Scan timeout for directory: {directory}, continuing in background")
                    # Note: scan_task continues running and will cache results when done
                    display_name = directory_input if directory != directory_input else directory
                    return {
                        "blocks": [
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": 
                                    f"🔄 *Scanning directory:* {display_name}\n\n" +
                                    "This directory is large and is being scanned in the background.\n\n" +
                                    f"View results in the dashboard: {self.dashboard_base_url}\n\n" +
                                    "💡 _Tip: Run this command again in 30 seconds to see cached results instantly!_"
                                }
                            }
                        ]
                    }
                    
        except Exception as e:
            logger.error(f"Error in scan command: {str(e)}", exc_info=True)
            return {"response_type": "ephemeral", "text": f"Error scanning directory: {str(e)}"}

    async def _handle_risks(self, args: List[str], user_id: str, channel_id: str, user_chat_service: ChatService) -> Dict:
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please specify a directory. Usage: `/testlegacy risks [directory]`"
            }

        directory = " ".join(args)
        try:
            # Get risk analysis
            risks = await user_chat_service.analyze_risks(directory)
            
            # Just point to the main dashboard
            dashboard_url = f"{self.dashboard_base_url}"
            
            return {
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"Risk Analysis: {directory} 🚨"}
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": self._format_risks(risks)}
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "View Details"},
                                "url": dashboard_url
                            }
                        ]
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Error in risks command: {str(e)}", exc_info=True)
            return {"response_type": "ephemeral", "text": f"Error analyzing risks: {str(e)}"}

    async def _handle_hot(self, args: List[str], user_id: str, channel_id: str, user_chat_service: ChatService) -> Dict:
        """Handle /grbg hot command - Show highest priority items right now"""
        try:
            # Get drive statistics from chat service
            stats = await user_chat_service.get_drive_stats()
            
            # Get urgent items (highest priority)
            urgent_items = self._get_urgent_items(stats)
            
            # Create hot items message
            if not urgent_items:
                return {
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": "🔥 Hot Items - All Clear!"}
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "No urgent items found. Your drive is in good shape! 🎉"}
                        }
                    ]
                }
            
            # Format hot items with priority indicators
            hot_items_text = "\n".join(f"🔥 {item}" for item in urgent_items)
            
            return {
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "🔥 Hot Items - Immediate Attention Required"}
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Priority Items:*\n{hot_items_text}"}
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "View Full Analysis"},
                                "url": f"{self.dashboard_base_url}"
                            }
                        ]
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Error in hot command: {str(e)}", exc_info=True)
            return {"response_type": "ephemeral", "text": f"Error getting hot items: {str(e)}"}

    async def _handle_suggest(self, args: List[str], user_id: str, channel_id: str, user_chat_service: ChatService) -> Dict:
        """Handle /grbg suggest command - Get AI-powered recommendations"""
        try:
            # Get drive statistics for recommendations
            stats = await user_chat_service.get_drive_stats()
            
            # Generate recommendations based on stats
            recommendations = self._generate_recommendations(stats)
            
            return {
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "🤖 AI Recommendations"}
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": recommendations}
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "View Detailed Analysis"},
                                "url": f"{self.dashboard_base_url}"
                            }
                        ]
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Error in suggest command: {str(e)}", exc_info=True)
            return {"response_type": "ephemeral", "text": f"Error generating recommendations: {str(e)}"}

    async def _handle_automate(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        """Handle /grbg automate command - View/configure automatic actions"""
        try:
            # For now, show available automation options
            automation_options = self._get_automation_options()
            
            return {
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "⚙️ Automation Center"}
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": automation_options}
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Configure Automation"},
                                "url": f"{self.dashboard_base_url}"
                            }
                        ]
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Error in automate command: {str(e)}", exc_info=True)
            return {"response_type": "ephemeral", "text": f"Error accessing automation: {str(e)}"}

    def _calculate_health_score(self, stats: Dict[str, Any]) -> int:
        """Calculate health score based on multiple factors with weighted scoring"""
        weights = {
            'sensitive_docs': 0.4,  # 40% weight - most important
            'old_files': 0.3,       # 30% weight - important for cleanup
            'storage_usage': 0.3    # 30% weight - important for capacity
        }
        
        # Calculate individual scores (0-100 scale)
        sensitive_score = self._score_sensitive_docs(stats.get('sensitive_files', 0))
        old_files_score = self._score_old_files(stats.get('old_files', 0))
        storage_score = self._score_storage(stats.get('storage_used_percentage', 0))
        
        # Weighted average
        total_score = (
            sensitive_score * weights['sensitive_docs'] +
            old_files_score * weights['old_files'] +
            storage_score * weights['storage_usage']
        )
        
        return int(round(total_score))

    def _score_sensitive_docs(self, sensitive_count: int) -> int:
        """Score based on sensitive documents (0-100, higher is better)"""
        if sensitive_count == 0:
            return 100
        elif sensitive_count <= 5:
            return 80
        elif sensitive_count <= 10:
            return 60
        elif sensitive_count <= 20:
            return 40
        else:
            return 20

    def _score_old_files(self, old_files_count: int) -> int:
        """Score based on old files (0-100, higher is better)"""
        if old_files_count == 0:
            return 100
        elif old_files_count <= 10:
            return 90
        elif old_files_count <= 25:
            return 70
        elif old_files_count <= 50:
            return 50
        elif old_files_count <= 100:
            return 30
        else:
            return 10

    def _score_storage(self, storage_percentage: float) -> int:
        """Score based on storage usage (0-100, higher is better)"""
        if storage_percentage <= 50:
            return 100
        elif storage_percentage <= 70:
            return 80
        elif storage_percentage <= 80:
            return 60
        elif storage_percentage <= 90:
            return 40
        else:
            return 20

    def _get_urgent_items(self, stats: Dict[str, Any]) -> List[str]:
        """Get urgent items that need immediate attention, prioritized by severity"""
        urgent_items = []
        
        sensitive_files = stats.get('sensitive_files', 0)
        old_files = stats.get('old_files', 0)
        storage_used = stats.get('storage_used_percentage', 0)
        total_files = stats.get('total_files', 0)
        
        # High priority: Security issues
        if sensitive_files > 0:
            if sensitive_files > 10:
                urgent_items.append(f"🚨 CRITICAL: {sensitive_files} sensitive files need immediate review")
            elif sensitive_files > 5:
                urgent_items.append(f"🔒 HIGH: {sensitive_files} sensitive files need review")
            else:
                urgent_items.append(f"🔒 {sensitive_files} sensitive files need review")
        
        # Medium priority: Storage issues
        if storage_used > 90:
            urgent_items.append(f"💾 CRITICAL: Storage at {storage_used}% - immediate cleanup needed")
        elif storage_used > 80:
            urgent_items.append(f"💾 HIGH: Storage at {storage_used}% - cleanup recommended")
        elif storage_used > 70:
            urgent_items.append(f"💾 Storage usage is at {storage_used}%")
        
        # Lower priority: Old files (only if significant)
        if old_files > 50:
            urgent_items.append(f"📅 {old_files} files are over 3 years old - consider archiving")
        elif old_files > 20:
            urgent_items.append(f"📅 {old_files} files are over 3 years old")
        
        # Additional insights
        if total_files > 0:
            old_ratio = (old_files / total_files) * 100
            if old_ratio > 50:
                urgent_items.append(f"📊 {old_ratio:.1f}% of files are outdated")
        
        return urgent_items

    def _format_risks(self, risks: Dict[str, Any]) -> str:
        return (
            f"*Risk Summary:*\n" +
            f"• Sensitive Files: {risks.get('sensitive_files', 0)}\n" +
            f"• High Risk: {risks.get('high_risk', 0)}\n" +
            f"• Medium Risk: {risks.get('medium_risk', 0)}\n" +
            f"• Low Risk: {risks.get('low_risk', 0)}\n\n" +
            "*Top Concerns:*\n" +
            "\n".join(f"• {concern}" for concern in risks.get('top_concerns', []))
        )

    def _create_risks_summary(self, stats: Dict[str, Any], dashboard_url: str) -> Dict:
        """Create a security-focused summary"""
        sensitive_files = stats.get('sensitive_files', 0)
        old_files = stats.get('old_files', 0)
        total_files = stats.get('total_files', 0)
        
        risk_level = "Low"
        if sensitive_files > 10 or old_files > 50:
            risk_level = "High"
        elif sensitive_files > 0 or old_files > 20:
            risk_level = "Medium"
        
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Security Summary 🔒"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": 
                        f"*Risk Level:* {risk_level}\n" +
                        f"*Sensitive Files:* {sensitive_files}\n" +
                        f"*Old Files (>3y):* {old_files}\n" +
                        f"*Total Files:* {total_files}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Security Details"},
                            "url": dashboard_url
                        }
                    ]
                }
            ]
        }

    # NOTE: _handle_risks, _handle_hot, and _handle_suggest are kept for future use
    # They are not currently registered in the command handler but can be added later

    def _generate_recommendations(self, stats: Dict[str, Any]) -> str:
        """Generate AI-powered recommendations based on drive statistics"""
        recommendations = []
        
        sensitive_files = stats.get('sensitive_files', 0)
        old_files = stats.get('old_files', 0)
        storage_used = stats.get('storage_used_percentage', 0)
        
        if sensitive_files > 0:
            recommendations.append(f"🔒 *Security Priority:* Review {sensitive_files} sensitive files")
        
        if old_files > 10:
            recommendations.append(f"📅 *Cleanup Opportunity:* Archive {old_files} files older than 3 years")
        elif old_files > 0:
            recommendations.append(f"📅 *Maintenance:* Consider reviewing {old_files} old files")
        
        if storage_used > 80:
            recommendations.append(f"💾 *Storage Alert:* Drive is {storage_used}% full - consider cleanup")
        elif storage_used > 60:
            recommendations.append(f"💾 *Storage Watch:* Drive is {storage_used}% full - monitor usage")
        
        if not recommendations:
            recommendations.append("✅ *All Good:* Your drive is well-organized and secure!")
        
        return "\n".join(recommendations)

    def _get_automation_options(self) -> str:
        """Get available automation options"""
        return (
            "*Available Automations:*\n" +
            "• 🔄 Auto-archive files older than 3 years\n" +
            "• 🔒 Flag sensitive documents for review\n" +
            "• 📊 Weekly storage usage reports\n" +
            "• 🚨 Alert on unusual access patterns\n" +
            "• 🗑️ Suggest duplicate file removal\n\n" +
            "*Coming Soon:*\n" +
            "• 📅 Scheduled cleanup workflows\n" +
            "• 🤖 AI-powered content categorization\n" +
            "• 📧 Email digest notifications"
        )

    async def send_message(self, channel: str, text: str) -> None:
        """Send a message to a Slack channel"""
        try:
            response = self.client.chat_postMessage(
                channel=channel,
                text=text
            )
            logger.debug(f"Message sent to channel {channel}")
        except SlackApiError as e:
            logger.error(f"Error sending message: {str(e)}", exc_info=True)

    async def send_notification_blocks(self, channel: str, blocks: List[Dict]) -> None:
        """Send formatted blocks to a Slack channel"""
        try:
            logger.info(f"Attempting to send notification to channel: {channel}")
            logger.debug(f"Notification blocks: {json.dumps(blocks, indent=2)}")
            
            # Try to find channel by name first, then by ID
            # Slack API accepts channel names without # prefix
            channel_id = channel
            if not channel.startswith('C') and len(channel) < 20:  # Not a channel ID (IDs start with C and are longer)
                # Try to resolve channel name to ID
                try:
                    # First, try without # prefix
                    result = self.client.conversations_list(types="public_channel,private_channel", limit=200)
                    for ch in result.get("channels", []):
                        if ch["name"] == channel or ch["name"] == channel.lstrip("#"):
                            channel_id = ch["id"]
                            logger.info(f"Resolved channel name '{channel}' to ID: {channel_id}")
                            break
                    else:
                        logger.warning(f"Channel '{channel}' not found in workspace. Make sure:")
                        logger.warning(f"  1. The channel exists")
                        logger.warning(f"  2. The bot is invited to the channel: /invite @YourBotName")
                        logger.warning(f"  3. The bot has 'chat:write' scope for the channel")
                except Exception as e:
                    logger.warning(f"Could not resolve channel name '{channel}' to ID: {e}, using as-is")
            
            response = self.client.chat_postMessage(
                channel=channel_id,
                blocks=blocks
            )
            logger.info(f"Notification sent successfully to channel {channel_id} (name: {channel})")
            return response
        except SlackApiError as e:
            error_code = e.response.get("error", "unknown") if e.response else "unknown"
            logger.error(f"Slack API error sending notification to {channel}: {str(e)}")
            logger.error(f"Error response: {e.response}")
            
            if error_code == "not_in_channel":
                logger.error("=" * 60)
                logger.error("ACTION REQUIRED: Bot is not in the channel!")
                logger.error(f"To fix: Invite your bot to #{channel} in Slack:")
                logger.error(f"  1. Go to #{channel} in Slack")
                logger.error(f"  2. Type: /invite @YourBotName")
                logger.error(f"  3. Or add the bot manually via channel settings")
                logger.error("=" * 60)
            elif error_code == "channel_not_found":
                logger.error(f"Channel '{channel}' does not exist. Check the channel name.")
            elif error_code == "missing_scope":
                logger.error("Bot is missing required OAuth scope. Add 'chat:write' scope in Slack app settings.")
            
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending notification: {str(e)}", exc_info=True)
            raise 