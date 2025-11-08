# Slack Improvements & Intelligent Notifications - Implementation Plan

**Date:** 2025-01-XX  
**Status:** Final Plan - Ready for Implementation  
**Last Updated:** Based on feedback discussion

---

## Current State Assessment

### What's Working ✅
1. **Basic Slack Integration**
   - Slash commands: `/zo help`, `/zo connect`, `/zo list`, `/zo scan`
   - Event handling (app mentions)
   - Message templates for status, analyze, summary
   - Health score calculation
   - Urgent items detection

2. **Notification Service (Phase 1)**
   - Sends notifications when old files > 0 or sensitive files > 0
   - Sends to configured Slack channel (`SLACK_NOTIFICATION_CHANNEL`)
   - Basic notification blocks for old files and sensitive files

3. **Message Templates**
   - Status messages with health scores
   - Analysis messages with detailed stats
   - Summary messages
   - Help messages

### Current Limitations 🔴
1. **Authentication**
   - Uses shared Google Drive session (not per-user)
   - Slack users can't authenticate individually
   - No per-user context in Slack commands
   - **SECURITY GAP:** No secure link between SlackUser and WebUser

2. **Notifications**
   - **Reactive only**: Only sends after scans complete
   - **No user attribution**: Notifications don't show who triggered the scan
   - **No thresholds**: Always sends if old files > 0 or sensitive files > 0 (for now, send on all scans)
   - **No duplicate prevention**: Could send same notification multiple times
   - **No per-user notifications**: All notifications go to single channel
   - **No quiet hours/DND**: No way to suppress notifications during specific times
   - **No scheduling**: No automatic/periodic notifications
   - **No trend analysis**: Doesn't compare with previous scans
   - **No priority levels**: All notifications treated equally

3. **Command Structure**
   - Some advanced commands exist but not fully integrated (`analyze`, `summary`, `risks`, `hot`, `suggest`, `automate`)
   - No command aliases or shortcuts
   - Limited error handling and user feedback

4. **Intelligence**
   - No pattern recognition
   - No predictive alerts
   - No learning from user behavior
   - No context-aware recommendations

---

## Proposed Improvements

### Phase 1: Foundation & Smart Notifications (Immediate Focus)

#### 1.1 Slack User to Backend User Mapping (Security & Attribution)
**Goal:** Securely link Slack users to backend users for proper attribution and future per-user features

**Current State:**
- `SlackUser` table exists but not linked to `WebUser` table
- No way to know which backend user triggered a scan from Slack
- Security risk: No verification that Slack user is authorized to access a specific backend user's data

**Proposed Solution:**
- Add optional `web_user_id` foreign key to `SlackUser` table
- Implement secure linking mechanism (email verification + token)
- Support both linked and unlinked Slack users
- For now: All notifications go to shared channel (even if linked)
- Future: Per-user notifications will use this mapping

**Security Considerations:**
- **Email Verification:** Slack user must verify they own the backend user's email
- **Token-Based Linking:** Generate secure token for linking (not just email match)
- **Optional Linking:** Slack users can work without linking (for shared channel notifications)
- **Audit Trail:** Log all linking/unlinking actions

**Implementation:**
```python
# Database schema update
class SlackUser(Base):
    __tablename__ = "slack_users"
    
    id = Column(Integer, primary_key=True, index=True)
    slack_user_id = Column(String, unique=True, index=True)
    email = Column(String)
    
    # Link to WebUser (optional)
    web_user_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    web_user = relationship("WebUser", backref="slack_users")
    
    # Linking verification
    linking_token = Column(String, nullable=True)  # Secure token for email verification
    linking_token_expires_at = Column(DateTime, nullable=True)
    is_linked = Column(Boolean, default=False)
    
    # Legacy fields (deprecated, but keep for migration)
    google_drive_token = Column(String, nullable=True)
    google_drive_refresh_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Linking Flow:**
1. User runs `/zo link` command
2. System generates secure token and sends to user's email
3. User verifies token via web dashboard or Slack command
4. Link is established and verified

**For Now:**
- Slack commands use shared backend Drive service (no per-user auth needed)
- Notifications show backend user info (email) when available
- All notifications go to shared channel regardless of linking status

---

#### 1.2 Intelligent Notification System

**Goal:** Proactive, context-aware notifications that add value without noise

##### A. User Attribution in Notifications
**Current:** Notifications don't show who triggered the scan  
**Proposed:** Show user attribution in all notifications

**Features:**
- Include backend user email in notifications
- Show which user initiated the scan
- Format: "User ABC (user@example.com) scanned drive YYY and here are the results"

**Implementation:**
- Pass `user_id` or `user_email` to notification service
- Update notification templates to include user attribution
- Show user info prominently in notification header

**Example:**
```
🔒 Sensitive Files Detected

*Scanned by:* John Doe (john@example.com)
*Directory:* Finance/2020
*Files with sensitive content:* 12

*Results:*
• 5 files contain PII data
• 3 files have expired retention policy
• 4 files need security review
```

##### B. Threshold-Based Notifications (Future - Define as we go)
**Current:** Sends notification on all scans (keeping this for now)  
**Proposed:** Eventually add configurable thresholds (define as we go)

**Features:**
- Configurable thresholds per notification type
- Only notify on threshold changes (not every scan)
- Support for multiple threshold levels (warning, critical)

**Note:** Thresholds will be defined incrementally based on usage patterns. For now, send notifications on all backend scans.

##### C. Duplicate Prevention
**Current:** Could send same notification multiple times  
**Proposed:** Track notification history and prevent duplicates

**Features:**
- Store notification history in database
- Time-based throttling (e.g., don't notify same issue within 24h)
- State-based tracking (only notify on changes)
- For now: Still send on all scans, but track duplicates for future threshold-based notifications

**Implementation:**
```python
# Notification history table
class NotificationHistory(Base):
    __tablename__ = "notification_history"
    
    id = Column(Integer, primary_key=True, index=True)
    directory_id = Column(String, index=True)
    notification_type = Column(String)  # 'old_files', 'sensitive_files', etc.
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    notification_data = Column(String)  # JSON of notification content
    
    # For deduplication
    issue_state_hash = Column(String)  # Hash of issue state (file counts, etc.)
```

##### D. Quiet Hours / Do Not Disturb (DND)
**Current:** No way to suppress notifications during specific times  
**Proposed:** Add quiet hours and DND feature

**Features:**
- Configurable quiet hours (e.g., 10 PM - 8 AM)
- DND mode (suppress all notifications temporarily)
- Critical notifications still sent (optional override)
- Per-channel or global settings

**Implementation:**
```python
# Config settings
SLACK_QUIET_HOURS_START = "22:00"  # 10 PM
SLACK_QUIET_HOURS_END = "08:00"    # 8 AM
SLACK_DND_ENABLED = False
SLACK_DND_OVERRIDE_CRITICAL = True  # Still send critical during DND
```

##### E. Priority-Based Notification Formatting (3 Levels)
**Current:** All notifications look the same  
**Proposed:** Different formatting based on priority (Critical, Warning, Info)

**Features:**
- **Critical**: Red header, urgent emoji, prominent action buttons
- **Warning**: Yellow header, moderate urgency
- **Info**: Blue header, informational

**Priority Calculation:**
- Critical: Sensitive files > 10 OR old files > 50 OR storage > 85%
- Warning: Sensitive files > 5 OR old files > 20 OR storage > 70%
- Info: Everything else

**Example:**
```python
# Priority levels
PRIORITY_CRITICAL = {
    'header_emoji': '🚨',
    'header_color': 'danger',  # Red in Slack
    'action_required': True
}

PRIORITY_WARNING = {
    'header_emoji': '⚠️',
    'header_color': 'warning',  # Yellow in Slack
    'action_required': False
}

PRIORITY_INFO = {
    'header_emoji': 'ℹ️',
    'header_color': 'good',  # Green in Slack
    'action_required': False
}
```

##### F. Trend Analysis in Notifications
**Current:** Only shows current state  
**Proposed:** Compare with previous scans to show trends

**Features:**
- Compare current scan with previous scan
- Show trends (improving, worsening, stable)
- Highlight significant changes

**Example:**
```
🔒 Sensitive Files Detected

*Directory:* Finance/2020
*Files with sensitive content:* 12

*Trend:* ⬆️ Increased by 3 files since last scan (9 → 12)
*Priority:* HIGH - Action required
```

##### G. Actionable Notifications
**Current:** Basic "View Dashboard" button  
**Proposed:** Multiple action options per notification

**Features:**
- Quick actions (Archive, Schedule Review, Dismiss)
- Deep links to specific dashboard sections
- Context-aware actions based on issue type

**Example:**
```python
# Action buttons in notifications
[
    {"type": "button", "text": "View Files", "url": "...", "style": "primary"},
    {"type": "button", "text": "Schedule Review", "action_id": "schedule_review"},
    {"type": "button", "text": "Dismiss", "action_id": "dismiss_notification", "style": "danger"}
]
```

---

#### 1.3 Enhanced Command Structure

**Goal:** Make Slack commands more intuitive and powerful

##### A. Command Consolidation
**Current:** `/zo help`, `/zo connect`, `/zo list`, `/zo scan`  
**Proposed:** Expand to match web dashboard capabilities

**Commands (Both `/zo` and `/zohra` prefixes supported):**
- `/zo` or `/zohra` `status` - Quick health score and urgent items
- `/zo` or `/zohra` `hot` - Highest priority items right now
- `/zo` or `/zohra` `analyze [directory] [--quick|--deep]` - Analyze directory
- `/zo` or `/zohra` `summary [directory] [--risks|--storage|--access]` - Get summary
- `/zo` or `/zohra` `risks [directory]` - Security-focused analysis
- `/zo` or `/zohra` `suggest` - AI-powered recommendations
- `/zo` or `/zohra` `automate` - View/configure automation
- `/zo` or `/zohra` `link` - Link Slack user to backend user (email verification)
- `/zo` or `/zohra` `unlink` - Unlink Slack user from backend user

**Note:** Some of these already exist in code but aren't registered in handler!

##### B. Command Aliases & Shortcuts
**Proposed:** Add shortcuts for common commands

**Examples:**
- `/zo s` → `/zo status`
- `/zo h` → `/zo hot`
- `/zo a [dir]` → `/zo analyze [dir]`

##### C. Interactive Command Responses
**Proposed:** Use Slack's interactive components for better UX

**Features:**
- Dropdown menus for directory selection
- Date pickers for time-based queries
- Multi-select for filtering options

---

### Phase 2: Proactive Intelligence (Future Enhancement)

#### 2.1 Scheduled Notifications
**Goal:** Automatic periodic notifications

**Features:**
- Daily/weekly summaries
- Scheduled health checks
- Proactive alerts before issues become critical

**Example:**
```python
# Scheduled notifications
SCHEDULED_NOTIFICATIONS = {
    'daily_summary': {
        'schedule': '09:00',  # 9 AM daily
        'type': 'summary',
        'recipients': ['#legacydata']
    },
    'weekly_report': {
        'schedule': 'Monday 09:00',  # Every Monday at 9 AM
        'type': 'weekly_report',
        'recipients': ['#legacydata']
    }
}
```

#### 2.2 Predictive Alerts
**Goal:** Predict issues before they happen

**Features:**
- Analyze patterns (e.g., storage growth rate)
- Predict when storage will be full
- Alert before critical thresholds

**Example:**
```
🔮 Predictive Alert

Based on your storage growth rate:
• Storage will reach 90% in ~15 days
• Current growth: +2.5GB/week
• Recommendation: Schedule cleanup now
```

#### 2.3 Context-Aware Recommendations
**Goal:** Smart, personalized recommendations

**Features:**
- Learn from user behavior
- Suggest actions based on patterns
- Seasonal recommendations (e.g., year-end cleanup)

---

### Phase 3: Advanced Features (Future)

#### 3.1 Per-User Notifications
- Map Slack users to Google Drive accounts
- Send personalized notifications via DM
- User preference settings

#### 3.2 Rich Dashboard Links
- Deep links to specific dashboard sections
- Pre-filtered views
- Context preservation

#### 3.3 Notification Preferences
- User-configurable notification settings
- Notification frequency controls
- Channel preferences

---

## Implementation Plan

### Phase 1: Foundation & Smart Notifications (Detailed Tasks)

#### Task 1.1: Slack User to Backend User Mapping (3-4 hours)
**Goal:** Securely link Slack users to backend users for attribution

**Steps:**
1. **Database Migration**
   - [ ] Add `web_user_id` foreign key to `SlackUser` table
   - [ ] Add `linking_token`, `linking_token_expires_at`, `is_linked` fields
   - [ ] Create migration script
   - [ ] Test migration

2. **Linking Service**
   - [ ] Create `SlackLinkingService` class
   - [ ] Implement `generate_linking_token()` method
   - [ ] Implement `verify_linking_token()` method
   - [ ] Implement `link_slack_to_web_user()` method
   - [ ] Implement `unlink_slack_user()` method
   - [ ] Add email verification flow

3. **Command Handlers**
   - [ ] Add `/zo link` command handler
   - [ ] Add `/zo unlink` command handler
   - [ ] Add `/zo link-status` command handler
   - [ ] Test linking flow

4. **Security & Audit**
   - [ ] Add audit logging for linking/unlinking
   - [ ] Implement token expiration (24 hours)
   - [ ] Add rate limiting for linking attempts
   - [ ] Test security measures

**Deliverables:**
- Database migration
- Linking service with email verification
- Command handlers for linking/unlinking
- Security audit logging

---

#### Task 1.2: User Attribution in Notifications (2-3 hours)
**Goal:** Show which user triggered the scan in notifications

**Steps:**
1. **Update Notification Service**
   - [ ] Modify `send_scan_notifications()` to accept `user_id` or `user_email`
   - [ ] Update notification templates to include user attribution
   - [ ] Add user info to notification header

2. **Update Scan Callers**
   - [ ] Find all places where scans are triggered
   - [ ] Pass user context to notification service
   - [ ] Handle case where user info is not available

3. **Template Updates**
   - [ ] Update `_create_old_files_notification()` to include user
   - [ ] Update `_create_sensitive_files_notification()` to include user
   - [ ] Format: "Scanned by: User Name (email@example.com)"

4. **Testing**
   - [ ] Test notifications with user attribution
   - [ ] Test notifications without user info (fallback)
   - [ ] Verify formatting looks good

**Deliverables:**
- Updated notification templates with user attribution
- All scan callers pass user context
- Graceful fallback when user info unavailable

---

#### Task 1.3: Duplicate Prevention & Notification History (3-4 hours)
**Goal:** Track notification history and prevent duplicates

**Steps:**
1. **Database Schema**
   - [ ] Create `NotificationHistory` table
   - [ ] Add fields: `directory_id`, `notification_type`, `user_id`, `sent_at`, `notification_data`, `issue_state_hash`
   - [ ] Create migration script
   - [ ] Add indexes for queries

2. **Notification History Service**
   - [ ] Create `NotificationHistoryService` class
   - [ ] Implement `record_notification()` method
   - [ ] Implement `has_already_notified()` method
   - [ ] Implement `get_recent_notifications()` method
   - [ ] Add state hash calculation

3. **Integration**
   - [ ] Update `NotificationService` to use history service
   - [ ] Add duplicate check before sending
   - [ ] Record notification after sending
   - [ ] Add time-based throttling (24h cooldown)

4. **Testing**
   - [ ] Test duplicate prevention
   - [ ] Test state change detection
   - [ ] Test time-based throttling

**Deliverables:**
- Notification history table
- History service with duplicate detection
- Integration with notification service
- Tests for duplicate prevention

---

#### Task 1.4: Quiet Hours / Do Not Disturb (2-3 hours)
**Goal:** Suppress notifications during quiet hours

**Steps:**
1. **Configuration**
   - [ ] Add `SLACK_QUIET_HOURS_START` to config
   - [ ] Add `SLACK_QUIET_HOURS_END` to config
   - [ ] Add `SLACK_DND_ENABLED` to config
   - [ ] Add `SLACK_DND_OVERRIDE_CRITICAL` to config

2. **Quiet Hours Service**
   - [ ] Create `QuietHoursService` class
   - [ ] Implement `is_quiet_hours()` method
   - [ ] Implement `is_dnd_enabled()` method
   - [ ] Implement `should_send_notification()` method (check quiet hours + DND)
   - [ ] Handle timezone considerations

3. **Integration**
   - [ ] Update `NotificationService` to check quiet hours before sending
   - [ ] Respect critical override setting
   - [ ] Add logging when notifications suppressed

4. **Testing**
   - [ ] Test quiet hours logic
   - [ ] Test DND mode
   - [ ] Test critical override
   - [ ] Test timezone handling

**Deliverables:**
- Quiet hours configuration
- Quiet hours service
- Integration with notification service
- Tests for quiet hours/DND

---

#### Task 1.5: Priority-Based Formatting (2-3 hours)
**Goal:** Format notifications based on priority (Critical, Warning, Info)

**Steps:**
1. **Priority Calculation**
   - [ ] Create `PriorityCalculator` class
   - [ ] Implement `calculate_priority()` method
   - [ ] Define priority rules (Critical, Warning, Info)
   - [ ] Add priority to notification data

2. **Template Updates**
   - [ ] Update templates to accept priority parameter
   - [ ] Add priority-specific formatting (emoji, color)
   - [ ] Update `_create_old_files_notification()` with priority
   - [ ] Update `_create_sensitive_files_notification()` with priority

3. **Slack Block Formatting**
   - [ ] Use Slack's `danger` style for Critical
   - [ ] Use Slack's `warning` style for Warning
   - [ ] Use Slack's `good` style for Info
   - [ ] Update header emojis based on priority

4. **Testing**
   - [ ] Test priority calculation
   - [ ] Test formatting for each priority level
   - [ ] Verify Slack rendering looks correct

**Deliverables:**
- Priority calculation logic
- Updated notification templates with priority formatting
- Tests for all priority levels

---

#### Task 1.6: Trend Analysis in Notifications (3-4 hours)
**Goal:** Compare with previous scans to show trends

**Steps:**
1. **Previous Scan Storage**
   - [ ] Store previous scan results in database or cache
   - [ ] Create `PreviousScanService` class
   - [ ] Implement `store_scan_results()` method
   - [ ] Implement `get_previous_scan()` method

2. **Trend Calculation**
   - [ ] Create `TrendCalculator` class
   - [ ] Implement `calculate_trend()` method (improving, worsening, stable)
   - [ ] Calculate change deltas (e.g., +3 files, -5 files)
   - [ ] Determine trend significance

3. **Template Updates**
   - [ ] Add trend section to notification templates
   - [ ] Show trend emoji (⬆️, ⬇️, ➡️)
   - [ ] Show change deltas
   - [ ] Format: "Trend: ⬆️ Increased by 3 files since last scan (9 → 12)"

4. **Testing**
   - [ ] Test trend calculation
   - [ ] Test with no previous scan (graceful fallback)
   - [ ] Test formatting

**Deliverables:**
- Previous scan storage service
- Trend calculation logic
- Updated templates with trend information
- Tests for trend detection

---

#### Task 1.7: Actionable Notifications (2-3 hours)
**Goal:** Add multiple action buttons to notifications

**Steps:**
1. **Action Button Design**
   - [ ] Design action buttons for each notification type
   - [ ] Define actions: "View Files", "Schedule Review", "Dismiss"
   - [ ] Create deep links to dashboard

2. **Template Updates**
   - [ ] Update notification templates with action buttons
   - [ ] Add primary action button (View Files)
   - [ ] Add secondary actions
   - [ ] Add deep links to specific dashboard sections

3. **Deep Link Generation**
   - [ ] Create `DeepLinkService` class
   - [ ] Generate dashboard URLs with filters
   - [ ] Generate URLs for specific directories
   - [ ] Generate URLs for specific file types

4. **Testing**
   - [ ] Test action button rendering
   - [ ] Test deep links work correctly
   - [ ] Verify buttons are actionable

**Deliverables:**
- Updated templates with action buttons
- Deep link generation service
- Tests for action buttons

---

#### Task 1.8: Enhanced Commands (3-4 hours)
**Goal:** Register all command handlers and support both `/zo` and `/zohra` prefixes

**Steps:**
1. **Command Handler Registration**
   - [ ] Update `handle_slash_command()` to register all handlers
   - [ ] Register `analyze`, `summary`, `risks`, `hot`, `suggest`, `automate`
   - [ ] Support both `/zo` and `/zohra` prefixes
   - [ ] Add command aliases if needed

2. **Command Handler Updates**
   - [ ] Ensure all handlers use backend Drive service
   - [ ] Add user context to commands (for attribution)
   - [ ] Improve error handling
   - [ ] Add helpful error messages

3. **Testing**
   - [ ] Test all commands with `/zo` prefix
   - [ ] Test all commands with `/zohra` prefix
   - [ ] Test error handling
   - [ ] Test user attribution in command responses

**Deliverables:**
- All command handlers registered
- Both `/zo` and `/zohra` prefixes supported
- Improved error handling
- Tests for all commands

---

**Phase 1 Total Estimated Time: 20-28 hours**

---

### Phase 2: Proactive Intelligence (Detailed Tasks)

#### Task 2.1: Scheduled Notifications (4-5 hours)
**Goal:** Automatic periodic notifications

**Steps:**
1. **Scheduler Setup**
   - [ ] Choose scheduler library (APScheduler or Celery)
   - [ ] Set up scheduler service
   - [ ] Configure schedule persistence

2. **Notification Jobs**
   - [ ] Create daily summary job
   - [ ] Create weekly report job
   - [ ] Create health check job
   - [ ] Add job configuration

3. **Job Implementation**
   - [ ] Implement `send_daily_summary()` method
   - [ ] Implement `send_weekly_report()` method
   - [ ] Implement `send_health_check()` method
   - [ ] Aggregate data from all users

4. **Configuration**
   - [ ] Add schedule configuration to config
   - [ ] Make schedules configurable
   - [ ] Add enable/disable flags

5. **Testing**
   - [ ] Test scheduler setup
   - [ ] Test notification jobs
   - [ ] Test schedule persistence

**Deliverables:**
- Scheduler service
- Scheduled notification jobs
- Configuration system
- Tests for scheduled notifications

---

#### Task 2.2: Predictive Alerts (4-5 hours)
**Goal:** Predict issues before they happen

**Steps:**
1. **Pattern Analysis**
   - [ ] Create `PatternAnalysisService` class
   - [ ] Implement storage growth rate calculation
   - [ ] Implement trend projection
   - [ ] Add pattern detection for file counts

2. **Prediction Logic**
   - [ ] Implement `predict_storage_full_date()` method
   - [ ] Implement `predict_threshold_crossing()` method
   - [ ] Add confidence intervals

3. **Predictive Notifications**
   - [ ] Create predictive notification templates
   - [ ] Add prediction data to notifications
   - [ ] Format: "Storage will reach 90% in ~15 days"

4. **Testing**
   - [ ] Test pattern analysis
   - [ ] Test prediction logic
   - [ ] Test predictive notifications

**Deliverables:**
- Pattern analysis service
- Prediction logic
- Predictive notification templates
- Tests for predictions

---

#### Task 2.3: Context-Aware Recommendations (3-4 hours)
**Goal:** Smart, personalized recommendations

**Steps:**
1. **Recommendation Engine**
   - [ ] Create `RecommendationService` class
   - [ ] Implement recommendation algorithms
   - [ ] Add seasonal recommendations (year-end cleanup)
   - [ ] Add pattern-based recommendations

2. **Recommendation Templates**
   - [ ] Create recommendation notification templates
   - [ ] Format recommendations clearly
   - [ ] Add action buttons for recommendations

3. **Integration**
   - [ ] Add recommendations to `/zo suggest` command
   - [ ] Add recommendations to scheduled summaries
   - [ ] Show recommendations in notifications

4. **Testing**
   - [ ] Test recommendation generation
   - [ ] Test recommendation formatting
   - [ ] Test integration points

**Deliverables:**
- Recommendation engine
- Recommendation templates
- Integration with commands and notifications
- Tests for recommendations

---

**Phase 2 Total Estimated Time: 11-14 hours**

---

**Grand Total Estimated Time: 31-42 hours**

---

## Success Metrics

### Phase 1 Success Criteria
- ✅ Slack commands work without individual Google auth
- ✅ Notifications only send when thresholds crossed
- ✅ No duplicate notifications within 24h
- ✅ Notifications show priority levels clearly
- ✅ Notifications include trend information
- ✅ Notifications have actionable buttons
- ✅ All enhanced commands work correctly

### User Experience Goals
- **Reduced Noise:** Only receive notifications when action is needed
- **Clear Priority:** Easily identify urgent vs. informational
- **Actionable:** Can take action directly from notification
- **Context-Aware:** Understand trends and changes
- **Frictionless:** No authentication hassles in Slack

---

## Decisions Made ✅

1. **Authentication Approach:**
   - ✅ Use shared backend auth for now (Slack commands work without individual auth)
   - ✅ Add optional SlackUser → WebUser linking for attribution
   - ✅ Secure linking via email verification + token
   - ✅ Future: Per-user notifications will use this mapping

2. **Notification Thresholds:**
   - ✅ For now: Send notifications on all backend scans
   - ✅ Thresholds will be defined incrementally as we go
   - ✅ Future: Configurable per user/directory

3. **Notification Frequency:**
   - ✅ Duplicate prevention: 24h cooldown
   - ✅ Quiet hours/DND: Implemented in Phase 1
   - ✅ Critical notifications can override DND (configurable)

4. **Priority Levels:**
   - ✅ 3 levels: Critical, Warning, Info
   - ✅ Priority calculation defined in plan

5. **Command Structure:**
   - ✅ Support both `/zo` and `/zohra` prefixes
   - ✅ All enhanced commands will support both

6. **User Attribution:**
   - ✅ Add user attribution to all notifications
   - ✅ Format: "User ABC (email) scanned drive YYY and here are the results"

7. **Phase Implementation:**
   - ✅ Detailed Phase 1 and Phase 2 plans created
   - ✅ Tackle one task at a time
   - ✅ Phase 1: Foundation & Smart Notifications
   - ✅ Phase 2: Proactive Intelligence

---

## Security Considerations 🔒

### Slack User to Backend User Linking
- **Email Verification Required:** Users must verify email ownership via token
- **Token Expiration:** Linking tokens expire after 24 hours
- **Rate Limiting:** Prevent brute force linking attempts
- **Audit Trail:** All linking/unlinking actions are logged
- **Optional Linking:** Slack users can work without linking (for shared notifications)
- **Future Separation:** Linking prepares for future per-user notifications

### Notification Security
- **User Attribution:** Only show user info for scans they initiated
- **No Data Leakage:** Notifications don't expose sensitive file details
- **Access Control:** Ensure users can only see their own scan results (future)

### Command Security
- **Shared Backend Auth:** Commands use shared backend Drive service
- **No Credential Exposure:** Slack users don't store Google Drive tokens
- **Future:** Per-user commands will use secure linking

---

## Next Steps

1. ✅ **Plan Documented** - This document
2. **Start Implementation** - Begin with Task 1.1 (Slack User Mapping)
3. **One Task at a Time** - Complete each task fully before moving to next
4. **Test Thoroughly** - Test each feature before moving on
5. **Iterate** - Adjust plan based on implementation learnings

---

## References

- Current Slack Service: `legacy-data-manager/backend/app/services/slack_service.py`
- Current Notification Service: `legacy-data-manager/backend/app/services/notification_service.py`
- Slack API Documentation: https://api.slack.com/
- Slack Block Kit: https://api.slack.com/block-kit

