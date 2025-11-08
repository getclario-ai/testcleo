from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class SlackUser(Base):
    __tablename__ = "slack_users"
    
    id = Column(Integer, primary_key=True, index=True)
    slack_user_id = Column(String, unique=True, index=True)
    email = Column(String, nullable=True)  # Slack user's email (from Slack API)
    
    # Link to WebUser (optional - for attribution)
    web_user_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    web_user = relationship("WebUser", backref="slack_users")
    is_linked = Column(Boolean, default=False)
    linked_at = Column(DateTime, nullable=True)  # When linking happened
    last_reminder_sent_at = Column(DateTime, nullable=True)  # Last reminder sent (for throttling)
    
    # Legacy fields (deprecated, keep for migration - make nullable)
    google_drive_token = Column(String, nullable=True)
    google_drive_refresh_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WebUser(Base):
    __tablename__ = "web_users"
    
    # Database PRIMARY KEY (for foreign keys, joins)
    id = Column(Integer, primary_key=True, index=True)
    
    # Business identifier (UNIQUE, NOT NULL - no duplicates allowed)
    email = Column(String, unique=True, nullable=False, index=True)
    
    # Session identifier (nullable, unique - one session per user for now)
    # Later: Can be extended to support multiple sessions via separate table
    session_id = Column(String, unique=True, nullable=True, index=True)
    
    # Google Drive credentials - storing only refresh_token
    google_refresh_token = Column(String)  # Refresh token only (access token regenerated on demand)
    token_expires_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    session_expires_at = Column(DateTime, nullable=True)  # When session expires (typically 30 days)


class SlackLinkingAudit(Base):
    """Audit log for Slack user linking actions"""
    __tablename__ = "slack_linking_audit"
    
    id = Column(Integer, primary_key=True, index=True)
    slack_user_id = Column(String, index=True)
    web_user_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    
    action = Column(String)  # 'link_attempted', 'link_success', 'link_failed', 'link_unlinked'
    slack_email = Column(String, nullable=True)  # Email from Slack
    web_email = Column(String, nullable=True)  # Email from WebUser
    reason = Column(String, nullable=True)  # Why linking failed (if applicable)
    
    created_at = Column(DateTime, default=datetime.utcnow) 