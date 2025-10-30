"""
Notification Service for scan results.

Phase 1: Sends notifications when old files > 0 or sensitive files > 0
Phase 2: Will extend with thresholds, duplicate prevention, per-user notifications
"""
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from ..core.config import settings
from .slack_service import SlackService
from .chat_service import ChatService
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service for handling notifications when scans complete.
    
    Phase 1: Simple notifications to #legacydata channel
    Phase 2: Will extend with thresholds, duplicate prevention, user mapping
    """
    
    def __init__(self, slack_service: SlackService):
        """
        Initialize notification service.
        
        Args:
            slack_service: SlackService instance for sending Slack notifications
        """
        self.slack_service = slack_service
        self.notification_channel = settings.SLACK_NOTIFICATION_CHANNEL
    
    def should_send_notification(self, scan_results: Dict) -> Dict[str, bool]:
        """
        Determine if notifications should be sent based on scan results.
        
        Phase 1: Simple check - old files > 0 or sensitive files > 0
        Phase 2: Will add threshold checking, duplicate prevention, etc.
        
        Args:
            scan_results: The scan results dictionary
            
        Returns:
            Dictionary with notification flags: {
                'old_files': bool,
                'sensitive_files': bool
            }
        """
        stats = scan_results.get('stats', {})
        
        old_files_count = stats.get('by_age_group', {}).get('moreThanThreeYears', 0)
        sensitive_files_count = stats.get('total_sensitive', 0)
        
        return {
            'old_files': old_files_count > 0,
            'sensitive_files': sensitive_files_count > 0
        }
    
    async def send_scan_notifications(
        self, 
        directory_id: str, 
        directory_name: str, 
        scan_results: Dict
    ) -> None:
        """
        Send notifications based on scan results.
        
        Phase 1: Sends to #legacydata channel if issues found
        Phase 2: Will add per-user notifications, duplicate prevention, thresholds
        
        Args:
            directory_id: The directory ID that was scanned
            directory_name: Display name of the directory
            scan_results: The full scan results dictionary
        """
        try:
            logger.info(f"NotificationService.send_scan_notifications called for {directory_name} (ID: {directory_id})")
            logger.info(f"Notification channel: {self.notification_channel}")
            
            # Determine what notifications to send
            notification_flags = self.should_send_notification(scan_results)
            logger.info(f"Notification flags after should_send_notification: {notification_flags}")
            
            if not any(notification_flags.values()):
                logger.info(f"No notifications needed for {directory_name} - flags: {notification_flags}")
                return
            
            stats = scan_results.get('stats', {})
            old_files_count = stats.get('by_age_group', {}).get('moreThanThreeYears', 0)
            sensitive_files_count = stats.get('total_sensitive', 0)
            
            logger.info(f"Stats summary - Old files: {old_files_count}, Sensitive files: {sensitive_files_count}")
            
            notifications = []
            
            # Notification 1: Old files (>3 years)
            if notification_flags['old_files']:
                logger.info(f"Creating old files notification for {old_files_count} files")
                notifications.append(self._create_old_files_notification(
                    directory_id=directory_id,
                    directory_name=directory_name,
                    old_files_count=old_files_count
                ))
            
            # Notification 2: Sensitive files
            if notification_flags['sensitive_files']:
                logger.info(f"Creating sensitive files notification for {sensitive_files_count} files")
                notifications.append(self._create_sensitive_files_notification(
                    directory_id=directory_id,
                    directory_name=directory_name,
                    sensitive_files_count=sensitive_files_count
                ))
            
            logger.info(f"Sending {len(notifications)} notification(s) to channel {self.notification_channel}")
            
            # Send all notifications
            for notification in notifications:
                logger.info(f"Sending {notification['type']} notification...")
                await self.slack_service.send_notification_blocks(
                    channel=self.notification_channel,
                    blocks=notification['blocks']
                )
                logger.info(f"Successfully sent {notification['type']} notification for {directory_name} to {self.notification_channel}")
                
        except Exception as e:
            logger.error(f"Error sending scan notifications: {str(e)}", exc_info=True)
    
    def _create_old_files_notification(
        self, 
        directory_id: str, 
        directory_name: str, 
        old_files_count: int
    ) -> Dict:
        """
        Create notification blocks for old files.
        
        Phase 2: Will add detailed file lists, risk levels, etc.
        """
        return {
            "type": "old_files",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "📅 Old Files Detected"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": 
                        f"*Directory:* {directory_name}\n" +
                        f"*Files older than 3 years:* {old_files_count}\n\n" +
                        "These files may contain stale data and should be reviewed."
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Dashboard"},
                            "url": f"{self.slack_service.dashboard_base_url}?directory={directory_id}"
                        }
                    ]
                }
            ]
        }
    
    def _create_sensitive_files_notification(
        self, 
        directory_id: str, 
        directory_name: str, 
        sensitive_files_count: int
    ) -> Dict:
        """
        Create notification blocks for sensitive files.
        
        Phase 2: Will add detailed file information, categories, risk levels
        """
        return {
            "type": "sensitive_files",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "🔒 Sensitive Files Detected"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": 
                        f"*Directory:* {directory_name}\n" +
                        f"*Files with sensitive content:* {sensitive_files_count}\n\n" +
                        "These files contain PII, financial data, legal, or confidential information."
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Dashboard"},
                            "url": f"{self.slack_service.dashboard_base_url}?directory={directory_id}"
                        }
                    ]
                }
            ]
        }
    
    # Phase 2 methods (placeholders for future implementation)
    
    def check_thresholds(self, directory_id: str, scan_results: Dict) -> Dict[str, bool]:
        """
        Phase 2: Check if thresholds are crossed.
        
        Will check configured thresholds per directory/user and determine
        if notifications should be sent based on threshold changes.
        
        Returns: Dictionary indicating which thresholds were crossed
        """
        # TODO: Phase 2 implementation
        # - Load threshold config for directory
        # - Get previous scan state
        # - Compare current vs previous
        # - Return which thresholds were crossed
        pass
    
    def get_notification_recipients(self, directory_id: str) -> List[str]:
        """
        Phase 2: Get list of Slack channels/users to notify.
        
        Will map Google Drive authentication to Slack user IDs
        and return appropriate notification targets.
        
        Returns: List of Slack channel IDs or user IDs
        """
        # TODO: Phase 2 implementation
        # - Lookup Slack user ID from Google Drive auth
        # - Get user preferences (channel vs DM)
        # - Return list of recipients
        pass
    
    def has_already_notified(self, directory_id: str, notification_type: str) -> bool:
        """
        Phase 2: Check if notification was already sent.
        
        Prevents duplicate notifications for the same scan.
        
        Returns: True if notification was already sent
        """
        # TODO: Phase 2 implementation
        # - Query database for notification history
        # - Check time-based throttling rules
        # - Return True if should skip
        pass

