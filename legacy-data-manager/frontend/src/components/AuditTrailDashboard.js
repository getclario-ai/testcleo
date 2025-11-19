import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import config from '../config';
import './AuditTrailDashboard.css';

// User-friendly event type labels
const EVENT_TYPE_LABELS = {
  'scan_initiated': 'Directory Scan Initiated',
  'scan_completed': 'Directory Scan Completed',
  'auth_login': 'User Login',
  'auth_logout': 'User Logout',
  'directories_listed': 'List Directories',
  'file_accessed': 'File Accessed',
  'activity_accessed': 'View Audit Trail',
  'auth_status_check': 'Auth Check'
};

const AuditTrailDashboard = () => {
  const [activities, setActivities] = useState([]);
  const [stats, setStats] = useState({});
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [resourceNames, setResourceNames] = useState({});
  
  // Filters
  const [selectedEventType, setSelectedEventType] = useState('');
  const [selectedUser, setSelectedUser] = useState('');
  const [timePeriod, setTimePeriod] = useState(30);
  
  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(50);
  
  const navigate = useNavigate();

  // Fetch activities
  useEffect(() => {
    const fetchActivities = async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          days: timePeriod,
          limit: 500,
          offset: 0
        });
        
        if (selectedEventType) {
          params.append('event_type', selectedEventType);
        }
        
        const response = await fetch(
          `${config.apiBaseUrl}/api/v1/activity/?${params.toString()}`,
          {
            method: 'GET',
            credentials: 'include',
            headers: {
              'Accept': 'application/json',
            }
          }
        );
        
        if (response.ok) {
          const data = await response.json();
          setActivities(data);
          // Fetch resource names for directories/files
          fetchResourceNames(data);
        } else {
          setError('Failed to fetch activities');
        }
      } catch (err) {
        setError(`Error: ${err.message}`);
      } finally {
        setLoading(false);
      }
    };
    
    fetchActivities();
  }, [selectedEventType, timePeriod]);

  // Fetch resource names from Google Drive
  const fetchResourceNames = async (activities) => {
    const names = {};
    // Map resource IDs to their types for fallback display
    const resourceTypeMap = {};
    const uniqueResources = new Set();
    
    // Collect unique resource IDs and their types
    activities.forEach(activity => {
      if (activity.resource_id && (activity.resource_type === 'directory' || activity.resource_type === 'file')) {
        uniqueResources.add(activity.resource_id);
        resourceTypeMap[activity.resource_id] = activity.resource_type;
      }
    });
    
    // Fetch names for each resource with error handling and retry logic
    for (const resourceId of uniqueResources) {
      let retries = 2; // Retry up to 2 times
      let success = false;
      const resourceType = resourceTypeMap[resourceId] || 'Resource';
      
      while (retries > 0 && !success) {
        try {
          const response = await fetch(
            `${config.apiBaseUrl}/api/v1/drive/files/${resourceId}`,
            {
              method: 'GET',
              credentials: 'include',
              headers: {
                'Accept': 'application/json',
              }
            }
          );
          
          if (response.ok) {
            const data = await response.json();
            names[resourceId] = data.name || resourceId;
            success = true;
          } else if (response.status === 404) {
            // Resource not found - use fallback
            names[resourceId] = `${resourceType}: ${resourceId.substring(0, 12)}...`;
            success = true; // Don't retry for 404
          } else if (response.status >= 500 && retries > 1) {
            // Server error - retry after a short delay
            await new Promise(resolve => setTimeout(resolve, 500));
            retries--;
          } else {
            // Other client errors - use fallback
            names[resourceId] = `${resourceType}: ${resourceId.substring(0, 12)}...`;
            success = true;
          }
        } catch (err) {
          // Network error or other exception
          if (retries > 1) {
            // Retry after a short delay
            await new Promise(resolve => setTimeout(resolve, 500));
            retries--;
          } else {
            // Final attempt failed - use fallback
            console.warn(`Could not fetch name for ${resourceId}:`, err.message);
            names[resourceId] = `${resourceType}: ${resourceId.substring(0, 12)}...`;
            success = true;
          }
        }
      }
    }
    
    setResourceNames(names);
  };

  // Fetch stats
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch(
          `${config.apiBaseUrl}/api/v1/activity/stats?days=${timePeriod}`,
          {
            method: 'GET',
            credentials: 'include',
            headers: {
              'Accept': 'application/json',
            }
          }
        );
        
        if (response.ok) {
          const data = await response.json();
          setStats(data);
        }
      } catch (err) {
        console.error('Error fetching stats:', err);
      }
    };
    
    fetchStats();
  }, [timePeriod]);

  // Fetch users
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const response = await fetch(
          `${config.apiBaseUrl}/api/v1/activity/users?days=${timePeriod}`,
          {
            method: 'GET',
            credentials: 'include',
            headers: {
              'Accept': 'application/json',
            }
          }
        );
        
        if (response.ok) {
          const data = await response.json();
          setUsers(data);
        }
      } catch (err) {
        console.error('Error fetching users:', err);
      }
    };
    
    fetchUsers();
  }, [timePeriod]);

  // Filter activities by selected user (client-side)
  const filteredActivities = selectedUser
    ? activities.filter(a => a.user_email === selectedUser)
    : activities;

  // Paginate
  const indexOfLastItem = currentPage * itemsPerPage;
  const indexOfFirstItem = indexOfLastItem - itemsPerPage;
  const currentActivities = filteredActivities.slice(indexOfFirstItem, indexOfLastItem);
  const totalPages = Math.ceil(filteredActivities.length / itemsPerPage);

  const handlePageChange = (pageNumber) => {
    setCurrentPage(pageNumber);
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    
    // Backend returns UTC timestamp (ISO format without 'Z')
    // Ensure it's treated as UTC by appending 'Z' if not present
    let utcTimestamp = timestamp;
    if (!timestamp.endsWith('Z') && !timestamp.includes('+')) {
      utcTimestamp = timestamp + 'Z';
    }
    
    const date = new Date(utcTimestamp);
    
    // Format with user's local timezone
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });
  };

  const getEventTypeLabel = (eventType) => {
    return EVENT_TYPE_LABELS[eventType] || eventType;
  };

  const getStatusBadge = (status) => {
    if (!status) return null;
    const className = `status-badge status-${status}`;
    return <span className={className}>{status}</span>;
  };

  const getResourceDisplay = (activity) => {
    // For list operations, show "All directories" or similar
    if (!activity.resource_type || !activity.resource_id) {
      if (activity.event_type === 'directories_listed') {
        return 'All directories';
      }
      return 'N/A';
    }
    
    // Try to get resource name from metadata first (faster)
    const metadata = activity.metadata || {};
    if (metadata.directory_name) {
      return metadata.directory_name;
    }
    
    // Fallback to fetched resource names
    const resourceName = resourceNames[activity.resource_id];
    if (resourceName) {
      return resourceName;
    }
    
    // Show resource type and truncated ID
    return `${activity.resource_type}: ${activity.resource_id.substring(0, 12)}...`;
  };

  const getMetadataDisplay = (activity) => {
    const metadata = activity.metadata || {};
    
    // For directory listings, show count
    if (activity.event_type === 'directories_listed' && metadata.directory_count !== undefined) {
      return `${metadata.directory_count} directories`;
    }
    
    // For scan completed, show comprehensive stats
    if (activity.event_type === 'scan_completed') {
      const parts = [];
      if (metadata.file_count !== undefined) {
        parts.push(`${metadata.file_count} files`);
      }
      if (metadata.sensitive_count !== undefined && metadata.sensitive_count > 0) {
        parts.push(`${metadata.sensitive_count} sensitive`);
      }
      if (metadata.duplicate_count !== undefined && metadata.duplicate_count > 0) {
        parts.push(`${metadata.duplicate_count} duplicates`);
      }
      if (parts.length > 0) {
        return parts.join(', ');
      }
      return metadata.directory_name || 'Scan completed';
    }
    
    // For scan initiated, show directory name if available
    if (activity.event_type === 'scan_initiated' && metadata.directory_name) {
      return `Scanning: ${metadata.directory_name}`;
    }
    
    // Show any other meaningful metadata in a readable format
    if (Object.keys(metadata).length > 0) {
      // Try to format common metadata fields
      const formatted = [];
      if (metadata.directory_name) formatted.push(`Dir: ${metadata.directory_name}`);
      if (metadata.file_count !== undefined) formatted.push(`Files: ${metadata.file_count}`);
      if (metadata.directory_count !== undefined) formatted.push(`Dirs: ${metadata.directory_count}`);
      
      if (formatted.length > 0) {
        return formatted.join(', ');
      }
      
      // Fallback to JSON for complex metadata
      return JSON.stringify(metadata);
    }
    
    return '-';
  };

  if (loading) {
    return (
      <div className="audit-trail-container">
        <div className="loading">Loading audit trail...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="audit-trail-container">
        <div className="error">{error}</div>
      </div>
    );
  }

  return (
    <div className="audit-trail-container">
      <header className="audit-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button
            onClick={() => navigate('/')}
            className="back-button-icon"
            title="Back to Dashboard"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15,18 9,12 15,6"/>
            </svg>
          </button>
          <div>
            <h1>Audit Trail</h1>
            <p className="subtitle">Track all user activities and system events</p>
          </div>
        </div>
      </header>

      <div className="stats-summary">
        <div className="stat-box">
          <div className="stat-value">{stats.total_activities || 0}</div>
          <div className="stat-label">Total Activities</div>
        </div>
        <div className="stat-box">
          <div className="stat-value">{users.length}</div>
          <div className="stat-label">Active Users</div>
        </div>
        <div className="stat-box">
          <div className="stat-value">{Object.keys(stats.event_type_counts || {}).length}</div>
          <div className="stat-label">Event Types</div>
        </div>
        <div className="stat-box">
          <div className="stat-value">{timePeriod}</div>
          <div className="stat-label">Days</div>
        </div>
      </div>


      <div className="activities-table-container">
        <table className="activities-table">
          <thead>
            <tr>
              <th>
                <div className="th-content">
                  <span>Timestamp</span>
                  <div className="filter-wrapper">
                    <button
                      className={`filter-button ${timePeriod !== 30 ? 'active' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        const select = e.currentTarget.nextElementSibling;
                        if (select) {
                          // Create a temporary event to trigger the select
                          const event = new MouseEvent('mousedown', {
                            view: window,
                            bubbles: true,
                            cancelable: true
                          });
                          select.dispatchEvent(event);
                          setTimeout(() => {
                            select.focus();
                            select.click();
                          }, 10);
                        }
                      }}
                      title={timePeriod === 30 ? "Filter by Time Period" : `Time Period: ${timePeriod === 1 ? '24 hours' : timePeriod === 7 ? '7 days' : timePeriod === 90 ? '90 days' : timePeriod === 365 ? '1 year' : `${timePeriod} days`}`}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
                      </svg>
                    </button>
                    <select
                      className="header-filter-select"
                      value={timePeriod}
                      onChange={(e) => {
                        setTimePeriod(parseInt(e.target.value));
                        setCurrentPage(1);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      title={`Time Period: ${timePeriod === 1 ? '24 hours' : timePeriod === 7 ? '7 days' : timePeriod === 90 ? '90 days' : timePeriod === 365 ? '1 year' : `${timePeriod} days`}`}
                    >
                      <option value="1">Last 24 hours</option>
                      <option value="7">Last 7 days</option>
                      <option value="30">Last 30 days</option>
                      <option value="90">Last 90 days</option>
                      <option value="365">Last year</option>
                    </select>
                  </div>
                </div>
              </th>
              <th>
                <div className="th-content">
                  <span>User</span>
                  <div className="filter-wrapper">
                    <button
                      className={`filter-button ${selectedUser ? 'active' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        const select = e.currentTarget.nextElementSibling;
                        if (select) {
                          // Create a temporary event to trigger the select
                          const event = new MouseEvent('mousedown', {
                            view: window,
                            bubbles: true,
                            cancelable: true
                          });
                          select.dispatchEvent(event);
                          setTimeout(() => {
                            select.focus();
                            select.click();
                          }, 10);
                        }
                      }}
                      title={selectedUser ? `Filtered: ${selectedUser}` : "Filter by User"}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
                      </svg>
                    </button>
                    <select
                      className="header-filter-select"
                      value={selectedUser}
                      onChange={(e) => {
                        setSelectedUser(e.target.value);
                        setCurrentPage(1);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      title={selectedUser ? `Filtered: ${selectedUser}` : "Filter by User"}
                    >
                      <option value="">All Users</option>
                      {users.map(user => (
                        <option key={user} value={user}>{user}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </th>
              <th>
                <div className="th-content">
                  <span>Event Type</span>
                  <div className="filter-wrapper">
                    <button
                      className={`filter-button ${selectedEventType ? 'active' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        const select = e.currentTarget.nextElementSibling;
                        if (select) {
                          // Create a temporary event to trigger the select
                          const event = new MouseEvent('mousedown', {
                            view: window,
                            bubbles: true,
                            cancelable: true
                          });
                          select.dispatchEvent(event);
                          setTimeout(() => {
                            select.focus();
                            select.click();
                          }, 10);
                        }
                      }}
                      title={selectedEventType ? `Filtered: ${getEventTypeLabel(selectedEventType)}` : "Filter by Event Type"}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
                      </svg>
                    </button>
                    <select
                      className="header-filter-select"
                      value={selectedEventType}
                      onChange={(e) => {
                        setSelectedEventType(e.target.value);
                        setCurrentPage(1);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      title={selectedEventType ? `Filtered: ${getEventTypeLabel(selectedEventType)}` : "Filter by Event Type"}
                    >
                      <option value="">All Events</option>
                      {Object.keys(stats.event_type_counts || {}).map(eventType => (
                        <option key={eventType} value={eventType}>
                          {getEventTypeLabel(eventType)} ({stats.event_type_counts[eventType]})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </th>
              <th>
                <div className="th-content">
                  <span>Action</span>
                </div>
              </th>
              <th>
                <div className="th-content">
                  <span>Resource</span>
                </div>
              </th>
              <th>
                <div className="th-content">
                  <span>Details</span>
                </div>
              </th>
              <th>
                <div className="th-content">
                  <span>Source</span>
                </div>
              </th>
              <th>
                <div className="th-content">
                  <span>Status</span>
                </div>
              </th>
              <th>
                <div className="th-content">
                  <span>Duration (ms)</span>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            {currentActivities.length === 0 ? (
              <tr>
                <td colSpan="9" className="no-data">No activities found</td>
              </tr>
            ) : (
              currentActivities.map((activity) => (
                <tr key={activity.id}>
                  <td>{formatTimestamp(activity.created_at)}</td>
                  <td>{activity.user_email}</td>
                  <td>{getEventTypeLabel(activity.event_type)}</td>
                  <td>{activity.action}</td>
                  <td>{getResourceDisplay(activity)}</td>
                  <td className="metadata-cell">{getMetadataDisplay(activity)}</td>
                  <td>{activity.source || 'N/A'}</td>
                  <td>{getStatusBadge(activity.status)}</td>
                  <td>{activity.duration_ms || 'N/A'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button
            onClick={() => handlePageChange(currentPage - 1)}
            disabled={currentPage === 1}
          >
            Previous
          </button>
          <span className="page-info">
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => handlePageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};

export default AuditTrailDashboard;

