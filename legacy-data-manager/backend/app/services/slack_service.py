from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from ..core.config import settings
from .chat_service import ChatService
from ..db.models import SlackUser
from sqlalchemy.orm import Session
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

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
    def analyze_message(directory: str, summary: Dict[str, Any], dashboard_url: str) -> Dict:
        """Create a detailed analysis message for Slack."""
        # Create the header
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Analysis Results: {directory} 📊"}
            }
        ]
        
        # Add cache status if applicable
        if summary.get('is_cached'):
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "ℹ️ Showing cached results from previous analysis"
                    }
                ]
            })
        
        # Add basic statistics
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": 
                f"*Basic Statistics:*\n" +
                f"• Total Files: {summary['total_files']}\n" +
                f"• Sensitive Files: {summary['sensitive_files']}\n" +
                f"• Old Files (>3y): {summary['old_files']}\n" +
                f"• Storage Used: {summary['storage_used']}%"
            }
        })
        
        # Add file type distribution
        if summary.get('file_types'):
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": 
                    "*File Type Distribution:*\n" +
                    "\n".join(f"• {file_type}: {count}" for file_type, count in summary['file_types'].items() if count > 0)
                }
            })
        
        # Add age distribution
        if summary.get('age_distribution'):
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": 
                    "*Age Distribution:*\n" +
                    "\n".join(f"• {age}: {count}" for age, count in summary['age_distribution'].items() if count > 0)
                }
            })
        
        # Add risk assessment
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": 
                f"*Risk Assessment:*\n" +
                f"• Risk Level: {summary['risk_level']}\n" +
                f"• Risk Score: {summary['risk_score']}/100"
            }
        })
        
        # Add key findings
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": 
                "*Key Findings:*\n" + 
                "\n".join(f"• {finding}" for finding in summary['key_findings'])
            }
        })
        
        # Add action button
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Detailed Analysis"},
                    "url": dashboard_url
                }
            ]
        })
        
        return {"blocks": blocks}

    @staticmethod
    def summary_message(stats: Dict[str, Any], dashboard_url: str) -> Dict:
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Drive Summary 📈"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": 
                        f"*Total Files:* {stats['total_files']}\n" +
                        f"*Storage Used:* {stats['storage_used_percentage']}%\n" +
                        f"*Sensitive Files:* {stats['sensitive_files']}\n" +
                        f"*Old Files:* {stats['old_files']}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open Dashboard"},
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
                    "text": {"type": "plain_text", "text": "Available Commands 🤖"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": 
                        "*Immediate Insights:*\n" +
                        "• `/grbg status` - Quick health score and urgent items\n" +
                        "• `/grbg hot` - Show highest priority items right now\n\n" +
                        "*Analysis Commands:*\n" +
                        "• `/grbg analyze [dir] --quick` - Fast surface scan\n" +
                        "• `/grbg analyze [dir] --deep` - Comprehensive analysis in dashboard\n" +
                        "• `/grbg summary [dir] --risks` - Security-focused summary\n" +
                        "• `/grbg summary [dir] --storage` - Storage-focused summary\n" +
                        "• `/grbg summary [dir] --access` - Access patterns summary\n\n" +
                        "*Intelligent Actions:*\n" +
                        "• `/grbg suggest` - Get AI-powered recommendations\n" +
                        "• `/grbg automate` - View/configure automatic actions"
                    }
                }
            ]
        }

class SlackService:
    def __init__(self, chat_service: ChatService, db: Session):
        self.client = WebClient(token=settings.SLACK_BOT_TOKEN)
        self.chat_service = chat_service
        self.db = db
        self.templates = SlackMessageTemplates()
        self.dashboard_base_url = settings.FRONTEND_URL
        
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

            # Command handlers for /grbg commands
            handlers = {
                "help": self._handle_help,
                "status": self._handle_status,
                "hot": self._handle_hot,
                "analyze": self._handle_analyze,
                "summary": self._handle_summary,
                "suggest": self._handle_suggest,
                "automate": self._handle_automate,
                # Legacy commands for backward compatibility
                "list": self._handle_list,
                "risks": self._handle_risks
            }

            handler = handlers.get(command)
            if not handler:
                return {
                    "response_type": "ephemeral",
                    "text": f"Unknown command: {command}. Try `/grbg help` for available commands."
                }

            return await handler(args, user_id, channel_id)

        except Exception as e:
            logger.error(f"Error handling slash command: {str(e)}", exc_info=True)
            return {
                "response_type": "ephemeral",
                "text": f"Sorry, I encountered an error processing your command: {str(e)}"
            }

    async def _handle_help(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        return self.templates.help_message()

    async def _handle_status(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        try:
            # Get drive statistics from chat service
            stats = await self.chat_service.get_drive_stats()
            
            # Calculate health score (implement this logic)
            health_score = self._calculate_health_score(stats)
            
            # Determine urgent items
            urgent_items = self._get_urgent_items(stats)
            
            # Just point to the main dashboard
            dashboard_url = f"{self.dashboard_base_url}"
            
            return self.templates.status_message(health_score, urgent_items, dashboard_url)
        except Exception as e:
            logger.error(f"Error in status command: {str(e)}", exc_info=True)
            return {"response_type": "ephemeral", "text": f"Error getting status: {str(e)}"}

    async def _handle_analyze(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please specify a directory to analyze. Usage: `/grbg analyze [directory] [--quick|--deep]`"
            }

        # Parse directory and flags
        directory_parts = []
        flags = []
        
        for arg in args:
            if arg.startswith('--'):
                flags.append(arg)
            else:
                directory_parts.append(arg)
        
        if not directory_parts:
            return {
                "response_type": "ephemeral",
                "text": "Please specify a directory to analyze. Usage: `/grbg analyze [directory] [--quick|--deep]`"
            }
        
        directory = " ".join(directory_parts)
        is_quick = '--quick' in flags
        is_deep = '--deep' in flags
        
        try:
            if is_quick:
                # Quick surface scan - return basic stats only
                stats = await self.chat_service.get_drive_stats()
                return {
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": f"Quick Analysis: {directory} ⚡"}
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": 
                                f"*Quick Stats:*\n" +
                                f"• Total Files: {stats.get('total_files', 0)}\n" +
                                f"• Sensitive Files: {stats.get('sensitive_files', 0)}\n" +
                                f"• Old Files: {stats.get('old_files', 0)}\n" +
                                f"• Storage Used: {stats.get('storage_used_percentage', 0)}%"
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Run Deep Analysis"},
                                    "url": f"{self.dashboard_base_url}"
                                }
                            ]
                        }
                    ]
                }
            else:
                # Full analysis (default or --deep)
                analysis_results = await self.chat_service.analyze_directory(directory)
                summary = self._create_analysis_summary(analysis_results)
                dashboard_url = f"{self.dashboard_base_url}"
                
                if is_deep:
                    # For deep analysis, emphasize dashboard
                    summary['is_cached'] = False  # Force fresh analysis
                
                return self.templates.analyze_message(directory, summary, dashboard_url)
                
        except ValueError as e:
            logger.error(f"Value error in analyze command: {str(e)}")
            return {
                "response_type": "ephemeral",
                "text": f"Error: {str(e)}\nPlease make sure the directory ID is valid and you have access to it."
            }
        except Exception as e:
            error_msg = str(e)
            if "File not found" in error_msg or "notFound" in error_msg:
                logger.error(f"Directory not found error: {error_msg}")
                return {
                    "response_type": "ephemeral",
                    "text": f"Error: Directory not found. Please check if the directory ID '{directory}' is correct and you have access to it."
                }
            else:
                logger.error(f"Error in analyze command: {error_msg}", exc_info=True)
                return {
                    "response_type": "ephemeral",
                    "text": f"An error occurred while analyzing the directory. Please try again later or contact support if the issue persists."
                }

    async def _handle_summary(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        try:
            # Parse directory and flags
            directory_parts = []
            flags = []
            
            for arg in args:
                if arg.startswith('--'):
                    flags.append(arg)
                else:
                    directory_parts.append(arg)
            
            directory = " ".join(directory_parts) if directory_parts else None
            summary_type = None
            
            # Determine summary type based on flags
            if '--risks' in flags:
                summary_type = 'risks'
            elif '--storage' in flags:
                summary_type = 'storage'
            elif '--access' in flags:
                summary_type = 'access'
            
            # Get summary statistics
            stats = await self.chat_service.get_summary_stats(directory)
            dashboard_url = f"{self.dashboard_base_url}"
            
            # Create specialized summary based on type
            if summary_type == 'risks':
                return self._create_risks_summary(stats, dashboard_url)
            elif summary_type == 'storage':
                return self._create_storage_summary(stats, dashboard_url)
            elif summary_type == 'access':
                return self._create_access_summary(stats, dashboard_url)
            else:
                # Default summary
                return self.templates.summary_message(stats, dashboard_url)
                
        except Exception as e:
            logger.error(f"Error in summary command: {str(e)}", exc_info=True)
            return {"response_type": "ephemeral", "text": f"Error getting summary: {str(e)}"}

    async def _handle_list(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        try:
            # Use the chat service's list handler
            response = await self.chat_service._handle_list("")
            
            # Convert the response to Slack format
            return {
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "Available Directories 📁"}
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

    async def _handle_risks(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please specify a directory. Usage: `/testlegacy risks [directory]`"
            }

        directory = " ".join(args)
        try:
            # Get risk analysis
            risks = await self.chat_service.analyze_risks(directory)
            
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

    async def _handle_hot(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        """Handle /grbg hot command - Show highest priority items right now"""
        try:
            # Get drive statistics from chat service
            stats = await self.chat_service.get_drive_stats()
            
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

    async def _handle_suggest(self, args: List[str], user_id: str, channel_id: str) -> Dict:
        """Handle /grbg suggest command - Get AI-powered recommendations"""
        try:
            # Get drive statistics for recommendations
            stats = await self.chat_service.get_drive_stats()
            
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

    def _create_analysis_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Create a detailed summary from analysis results."""
        # Basic statistics
        total_files = results.get('total_files', 0)
        sensitive_files = results.get('sensitive_files', 0)
        old_files = results.get('old_files', 0)
        storage_used = results.get('storage_used', 0)
        
        # File type distribution
        file_types = results.get('file_types', {})
        file_type_summary = []
        for file_type, count in file_types.items():
            if count > 0:
                percentage = (count / total_files * 100) if total_files > 0 else 0
                file_type_summary.append(f"{file_type}: {count} ({percentage:.1f}%)")
        
        # Age distribution
        age_distribution = results.get('age_distribution', {})
        age_summary = []
        for age, count in age_distribution.items():
            if count > 0:
                percentage = (count / total_files * 100) if total_files > 0 else 0
                age_summary.append(f"{age}: {count} ({percentage:.1f}%)")
        
        # Risk assessment
        risk_level = results.get('risk_level', 'Unknown')
        risk_score = results.get('risk_score', 0)
        
        # Key findings
        key_findings = []
        if sensitive_files > 0:
            key_findings.append(f"🔒 Found {sensitive_files} sensitive files")
        if old_files > 0:
            key_findings.append(f"📅 {old_files} files are over 3 years old")
        if storage_used > 80:
            key_findings.append(f"⚠️ High storage usage: {storage_used}%")
        elif storage_used > 60:
            key_findings.append(f"📊 Moderate storage usage: {storage_used}%")
        
        # Add file type insights
        if file_type_summary:
            key_findings.append(f"📁 File types: {', '.join(file_type_summary)}")
        
        # Add age distribution insights
        if age_summary:
            key_findings.append(f"⏳ Age distribution: {', '.join(age_summary)}")
        
        # Add risk assessment
        key_findings.append(f"🚨 Risk level: {risk_level} (Score: {risk_score}/100)")
        
        return {
            'total_files': total_files,
            'sensitive_files': sensitive_files,
            'old_files': old_files,
            'storage_used': storage_used,
            'file_types': file_types,
            'age_distribution': age_distribution,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'key_findings': key_findings,
            'is_cached': results.get('is_cached', False)
        }

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

    def _create_storage_summary(self, stats: Dict[str, Any], dashboard_url: str) -> Dict:
        """Create a storage-focused summary"""
        storage_used = stats.get('storage_used_percentage', 0)
        total_files = stats.get('total_files', 0)
        
        storage_status = "Good"
        if storage_used > 80:
            storage_status = "Critical"
        elif storage_used > 60:
            storage_status = "Warning"
        
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Storage Summary 💾"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": 
                        f"*Storage Status:* {storage_status}\n" +
                        f"*Storage Used:* {storage_used}%\n" +
                        f"*Total Files:* {total_files}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Storage Details"},
                            "url": dashboard_url
                        }
                    ]
                }
            ]
        }

    def _create_access_summary(self, stats: Dict[str, Any], dashboard_url: str) -> Dict:
        """Create an access patterns summary"""
        total_files = stats.get('total_files', 0)
        old_files = stats.get('old_files', 0)
        
        # Calculate access patterns (placeholder logic)
        recent_access = total_files - old_files
        access_ratio = (recent_access / total_files * 100) if total_files > 0 else 0
        
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Access Patterns Summary 📊"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": 
                        f"*Recent Access:* {recent_access} files\n" +
                        f"*Access Ratio:* {access_ratio:.1f}%\n" +
                        f"*Total Files:* {total_files}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Access Details"},
                            "url": dashboard_url
                        }
                    ]
                }
            ]
        }

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