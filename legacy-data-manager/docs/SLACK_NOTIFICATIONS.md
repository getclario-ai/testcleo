# Slack Notification System

## Phase 1 (Current Implementation) ✅

### Trigger Conditions
- ✅ Send notification when **files older than 3 years count > 0**
- ✅ Send notification when **sensitive files count > 0**
- ✅ **Only on new scans** (not from cache)
- ⏸️ Threshold-based notifications → **Phase 2**

### When to Send
- ✅ After every **new scan completes** (fresh scan, not cached)
- ✅ Trigger from any source: Slack command, web dashboard, or API
- ⏸️ Send only when threshold crossed → **Phase 2**

### Where to Send
- ✅ Send to fixed Slack channel: **#legacydata**
- ✅ Works regardless of who initiated the scan
- ⏸️ Per-user notifications based on authentication → **Phase 2**

### Notification Format
- ✅ **Summary only**: Count of old files, count of sensitive files
- ✅ **Actionable button**: "View Dashboard" (deep-linked to directory)
- ⏸️ Detailed file lists → **Phase 2**

### Duplicate Prevention
- ⏸️ Track sent notifications to avoid duplicates → **Phase 2**
- ⏸️ Time-based throttling → **Phase 2**

---

## Phase 2 (Future)

### Trigger Conditions
- 🔄 Threshold-based notifications
  - Example: "Notify when >10 files older than 3 years"
  - Example: "Notify when >5 sensitive files found"
- 🔄 Only send when threshold **crossed** (not just exceeded)
- 🔄 Configurable thresholds per directory/user

### When to Send
- 🔄 Send only when threshold is **crossed** (new issue detected)
- 🔄 Option to suppress notifications if counts unchanged

### Where to Send
- 🔄 Connect Slack user ID to Google Drive authentication
- 🔄 Per-user notifications (each user gets their own alerts)
- 🔄 Option to send to both user DMs and channel

### Notification Format
- 🔄 Detailed file information:
  - List of top risky files
  - File names and risk levels
  - File owners/departments
- 🔄 Multiple action buttons:
  - "View Dashboard"
  - "Review Files"
  - "Dismiss Alert"

### Duplicate Prevention
- 🔄 Track which notifications have been sent per directory
- 🔄 Avoid sending duplicate alerts for same scan
- 🔄 Time-based throttling (e.g., max 1 notification per directory per 24 hours)
- 🔄 User preferences for notification frequency

---

## Implementation Status

**Phase 1**: ✅ Ready to implement  
**Phase 2**: 📝 Planned for future

