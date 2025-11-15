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
        scan_results: Dict,
        triggered_by_email: Optional[str] = None
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
            logger.debug(f"NotificationService.send_scan_notifications called for {directory_name} (ID: {directory_id})")
            logger.debug(f"Notification channel: {self.notification_channel}")
            
            # Determine what notifications to send
            notification_flags = self.should_send_notification(scan_results)
            logger.debug(f"Notification flags after should_send_notification: {notification_flags}")
            
            if not any(notification_flags.values()):
                logger.info(f"No notifications needed for {directory_name} - flags: {notification_flags}")
                return
            
            stats = scan_results.get('stats', {})
            old_files_count = stats.get('by_age_group', {}).get('moreThanThreeYears', 0)
            sensitive_files_count = stats.get('total_sensitive', 0)
            
            logger.debug(f"Stats summary - Old files: {old_files_count}, Sensitive files: {sensitive_files_count}")
            
            notifications = []
            
            # Notification 1: Old files (>3 years)
            if notification_flags['old_files']:
                logger.debug(f"Creating old files notification for {old_files_count} files")
                notifications.append(self._create_old_files_notification(
                    directory_id=directory_id,
                    directory_name=directory_name,
                    old_files_count=old_files_count,
                    triggered_by_email=triggered_by_email
                ))
            
            # Notification 2: Sensitive files
            if notification_flags['sensitive_files']:
                logger.debug(f"Creating sensitive files notification for {sensitive_files_count} files")
                notifications.append(self._create_sensitive_files_notification(
                    directory_id=directory_id,
                    directory_name=directory_name,
                    sensitive_files_count=sensitive_files_count,
                    scan_results=scan_results,
                    triggered_by_email=triggered_by_email
                ))
            
            logger.debug(f"Sending {len(notifications)} notification(s) to channel {self.notification_channel}")
            
            # Send all notifications
            for notification in notifications:
                logger.debug(f"Sending {notification['type']} notification...")
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
        old_files_count: int,
        triggered_by_email: Optional[str] = None
    ) -> Dict:
        """
        Create notification blocks for old files.
        
        Phase 2: Will add detailed file lists, risk levels, etc.
        """
        user_info = f"*👤 User:* {triggered_by_email}\n" if triggered_by_email else ""
        
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
                        user_info +
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
        sensitive_files_count: int,
        scan_results: Dict,
        triggered_by_email: Optional[str] = None
    ) -> Dict:
        """
        Create notification blocks for sensitive files.
        
        Includes user info and sensitivity breakdown by category and risk level.
        """
        stats = scan_results.get('stats', {})
        
        # Get sensitivity breakdown by category
        by_sensitivity = stats.get('by_sensitivity', {})
        pii_count = by_sensitivity.get('pii', 0)
        financial_count = by_sensitivity.get('financial', 0)
        legal_count = by_sensitivity.get('legal', 0)
        confidential_count = by_sensitivity.get('confidential', 0)
        
        # Get risk level breakdown
        by_risk_level = stats.get('by_risk_level', {})
        high_risk = by_risk_level.get('high', 0)
        medium_risk = by_risk_level.get('medium', 0)
        low_risk = by_risk_level.get('low', 0)
        
        # Build sensitivity breakdown text
        sensitivity_breakdown = []
        if pii_count > 0:
            sensitivity_breakdown.append(f"• 🆔 PII: {pii_count}")
        if financial_count > 0:
            sensitivity_breakdown.append(f"• 💰 Financial: {financial_count}")
        if legal_count > 0:
            sensitivity_breakdown.append(f"• ⚖️ Legal: {legal_count}")
        if confidential_count > 0:
            sensitivity_breakdown.append(f"• 🔐 Confidential: {confidential_count}")
        
        sensitivity_text = "\n".join(sensitivity_breakdown) if sensitivity_breakdown else "• No category breakdown available"
        
        # Build risk level breakdown text
        risk_breakdown = []
        if high_risk > 0:
            risk_breakdown.append(f"• 🔴 High: {high_risk}")
        if medium_risk > 0:
            risk_breakdown.append(f"• 🟡 Medium: {medium_risk}")
        if low_risk > 0:
            risk_breakdown.append(f"• 🟢 Low: {low_risk}")
        
        risk_text = "\n".join(risk_breakdown) if risk_breakdown else "• No risk breakdown available"
        
        user_info = f"*👤 User:* {triggered_by_email}\n" if triggered_by_email else ""
        
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
                        user_info +
                        f"*Directory:* {directory_name}\n" +
                        f"*Files with sensitive content:* {sensitive_files_count}\n\n" +
                        "*Sensitivity Breakdown:*\n" +
                        sensitivity_text + "\n\n" +
                        "*Risk Level Breakdown:*\n" +
                        risk_text + "\n\n" +
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

