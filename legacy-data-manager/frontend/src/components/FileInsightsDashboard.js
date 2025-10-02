import React, { useEffect, useState } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import config from '../config';
import './FileInsightsDashboard.css';

const defaultStats = {
  totalFiles: 0,
  totalStorage: 0,
  totalStorageBytes: 0,
  staleFiles: 0,
  sensitiveFiles: 0,
  topOwners: [],
  docCount: 0,
  ageDistribution: {
    moreThanThreeYears: { types: {}, risks: {} },
    oneToThreeYears: { types: {}, risks: {} },
    lessThanOneYear: { types: {}, risks: {} }
  }
};

// Add a helper function to format bytes to the largest unit
function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  // Show 2 decimals for MB and above, 0 for B/KB
  const decimals = i < 2 ? 0 : 2;
  return value.toFixed(decimals) + ' ' + sizes[i];
}

const FileInsightsDashboard = () => {
  const { ageGroup, fileType } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  // Restore context from state or localStorage
  const directoryId = location.state?.directoryId || localStorage.getItem('fid_directoryId') || 'root';
  const [stats, setStats] = useState(() => {
    const stateStats = location.state?.stats;
    if (stateStats) return stateStats;
    const lsStats = localStorage.getItem('fid_stats');
    return lsStats ? JSON.parse(lsStats) : defaultStats;
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // Save context to localStorage on navigation
  useEffect(() => {
    if (location.state) {
      if (location.state.directoryId) localStorage.setItem('fid_directoryId', location.state.directoryId);
      if (location.state.selectedDirectory) localStorage.setItem('fid_selectedDirectory', JSON.stringify(location.state.selectedDirectory));
      if (location.state.activeTab) localStorage.setItem('fid_activeTab', location.state.activeTab);
      if (location.state.stats) localStorage.setItem('fid_stats', JSON.stringify(location.state.stats));
    }
  }, [location.state]);

  // Save stats to localStorage when they change
  useEffect(() => {
    if (stats && stats.totalFiles > 0) {
      console.log('Saving updated stats to localStorage:', stats);
      localStorage.setItem('fid_stats', JSON.stringify(stats));
      // Also clear any restoration flag to ensure fresh navigation
      window.attemptedContextRestore = false;
    }
  }, [stats]);

  useEffect(() => {
    const fetchStats = async () => {
      setLoading(true);
      setError(null);
      try {
        // Fetch analysis data for the directory (or root)
        const res = await axios.post(
          `${config.apiBaseUrl}/api/v1/drive/directories/${directoryId}/analyze`
        );
        const data = res.data;
        // Aggregate stats for cards
        let totalFiles = 0;
        let totalStorage = 0;
        let staleFiles = 0;
        let sensitiveFiles = 0;
        let topOwnersMap = {};
        let debugSizes = [];
        // Age groups
        const ageGroups = ['moreThanThreeYears', 'oneToThreeYears', 'lessThanOneYear'];
        ageGroups.forEach(group => {
          const groupData = data[group];
          if (!groupData) return;
          if (ageGroup && group !== ageGroup) return;

          // Build a set of all sensitive file IDs for this age group
          const sensitiveFileIds = new Set();
          Object.values(groupData.sensitive_info || {}).forEach(findings => {
            findings.forEach(finding => {
              if (finding.file && finding.file.id) {
                sensitiveFileIds.add(finding.file.id);
              }
            });
          });

          Object.entries(groupData.file_types || {}).forEach(([type, files]) => {
            if (fileType && type !== fileType) return;
            totalFiles += files.length;
            files.forEach(file => {
              debugSizes.push({ name: file.name, size: file.size, type });
              totalStorage += Number(file.size) || 0;
              if (file.lastAccessed && new Date(file.lastAccessed) < new Date(Date.now() - 2 * 365 * 24 * 60 * 60 * 1000)) {
                staleFiles++;
              }
              if (file.owner) {
                topOwnersMap[file.owner] = (topOwnersMap[file.owner] || 0) + 1;
              }
              // Count sensitive files per type
              if (sensitiveFileIds.has(file.id)) {
                sensitiveFiles++;
              }
            });
          });
        });
        // Debug: print all file sizes being summed
        // eslint-disable-next-line no-console
        console.log('File sizes for disk usage:', debugSizes);
        // Debug: print all sensitive file sizes by risk category
        ageGroups.forEach(group => {
          const groupData = data[group];
          if (!groupData || !groupData.sensitive_info) return;
          Object.entries(groupData.sensitive_info).forEach(([category, findings]) => {
            if (!Array.isArray(findings)) return;
            findings.forEach(finding => {
              const file = finding.file;
              if (file) {
                // eslint-disable-next-line no-console
                console.log(`[DEBUG] Sensitive file - Age group: ${group}, Category: ${category}, Name: ${file.name}, Size: ${file.size}`);
              }
            });
          });
        });
        // Top owners sorted
        const topOwners = Object.entries(topOwnersMap)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([name, count]) => ({ name, count }));
        setStats({
          totalFiles,
          totalStorageBytes: totalStorage,
          staleFiles,
          sensitiveFiles,
          topOwners,
        });
      } catch (err) {
        setError('Failed to load dashboard data.');
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, [directoryId, ageGroup, fileType]);

  // Back navigation with context restoration
  const handleBack = () => {
    const returnTo = location.state?.returnTo || '/';
    const navState = {
      selectedDirectory: location.state?.selectedDirectory || JSON.parse(localStorage.getItem('fid_selectedDirectory') || 'null'),
      activeTab: location.state?.activeTab || localStorage.getItem('fid_activeTab'),
      stats: location.state?.stats || JSON.parse(localStorage.getItem('fid_stats') || 'null'),
    };
    navigate(returnTo, { state: navState });
  };

  if (loading) {
    return <div className="insights-dashboard-container"><div>Loading...</div></div>;
  }
  if (error) {
    return <div className="insights-dashboard-container"><div>{error}</div></div>;
  }

  return (
    <div className="insights-dashboard-container">
      {/* Insight Cards */}
      <div className="insight-cards-row">
        <div className="insight-card">
          <div className="insight-icon">📁</div>
          <div className="insight-title">Total Files</div>
          <div className="insight-value">{stats.totalFiles.toLocaleString()}</div>
          <div className="insight-sub">{formatBytes(stats.totalStorageBytes)} used</div>
        </div>
        <div className="insight-card">
          <div className="insight-icon">🕒</div>
          <div className="insight-title">Stale Files</div>
          <div className="insight-value">{stats.staleFiles.toLocaleString()}</div>
          <button className="insight-action">Archive All</button>
        </div>
        <div className="insight-card">
          <div className="insight-icon">🔒</div>
          <div className="insight-title">Sensitive Files</div>
          <div className="insight-value">{stats.sensitiveFiles.toLocaleString()}</div>
          <button
            className="insight-action"
            disabled={stats.sensitiveFiles === 0}
            onClick={() => {
              // Debug: Log context before navigation
              console.log('=== DEBUG: Navigation to review-sensitive-files ===');
              console.log('Stats before navigation:', stats);
              console.log('Selected directory:', location.state?.selectedDirectory || JSON.parse(localStorage.getItem('fid_selectedDirectory') || 'null'));
              
              // Always ensure context is in localStorage before navigation
              localStorage.setItem('fid_stats', JSON.stringify(stats));
              if (location.state?.selectedDirectory) {
                localStorage.setItem('fid_selectedDirectory', JSON.stringify(location.state.selectedDirectory));
              }
              
              // Save the current route with state for later restoration
              localStorage.setItem('fid_lastRoute', JSON.stringify({
                pathname: '/review-sensitive-files',
                state: {
                  selectedDirectory: location.state?.selectedDirectory || JSON.parse(localStorage.getItem('fid_selectedDirectory') || 'null'),
                  activeTab: ageGroup || (location.state?.activeTab) || 'moreThanThreeYears',
                  stats: stats,
                  directoryId: directoryId,
                  returnTo: location.pathname
                }
              }));
              
              // Navigate to review page
              navigate('/review-sensitive-files', {
                state: {
                  selectedDirectory: location.state?.selectedDirectory || JSON.parse(localStorage.getItem('fid_selectedDirectory') || 'null'),
                  activeTab: ageGroup || (location.state?.activeTab) || 'moreThanThreeYears',
                  stats: stats,
                  directoryId: directoryId,
                  returnTo: location.pathname
                }
              });
            }}
          >
            Review Now
          </button>
        </div>
        <div className="insight-card">
          <div className="insight-icon">👤</div>
          <div className="insight-title">Top Owners</div>
          <div className="insight-value">
            {stats.topOwners.length === 0 ? (
              <span className="owner-none">No ownership data available</span>
            ) : (
              stats.topOwners.map(owner => (
                <div key={owner.name} className="owner-row">
                  <span className="owner-avatar">{owner.name[0]}</span>
                  <span>{owner.name}</span>
                  <span className="owner-count">{owner.count}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
      {/* Actionable Suggestions */}
      <div className="suggestions-row">
        <div className="suggestion-card">
          <span>💡 You can save up to <b>{(stats.staleFiles * 0.125).toFixed(1)}GB</b> by archiving stale files.</span>
          <button className="insight-action">Archive Stale Files</button>
        </div>
        <div className="suggestion-card">
          <span>🔔 <b>{stats.sensitiveFiles}</b> sensitive files need review.</span>
          <button className="insight-action">Review Sensitive Files</button>
        </div>
      </div>
      {/* Floating Back Button */}
      <button className="insight-fab-back" onClick={handleBack} title="Back">
        <span>&larr;</span>
      </button>
    </div>
  );
};

export default FileInsightsDashboard; 