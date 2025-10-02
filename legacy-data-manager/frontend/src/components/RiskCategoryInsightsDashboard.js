import React, { useEffect, useState } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import config from '../config';
import './FileInsightsDashboard.css';

const defaultStats = {
  totalSensitive: 0,
  topOwners: [],
  recentFlagged: 0,
  highRiskFiles: [],
};

const RiskCategoryInsightsDashboard = () => {
  const { ageGroup, category } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const directoryId = location.state?.directoryId || localStorage.getItem('rcid_directoryId') || 'root';
  const [stats, setStats] = useState(() => {
    const stateStats = location.state?.stats;
    if (stateStats) return stateStats;
    const lsStats = localStorage.getItem('rcid_stats');
    return lsStats ? JSON.parse(lsStats) : defaultStats;
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (location.state) {
      if (location.state.directoryId) localStorage.setItem('rcid_directoryId', location.state.directoryId);
      if (location.state.selectedDirectory) localStorage.setItem('rcid_selectedDirectory', JSON.stringify(location.state.selectedDirectory));
      if (location.state.activeTab) localStorage.setItem('rcid_activeTab', location.state.activeTab);
      if (location.state.stats) localStorage.setItem('rcid_stats', JSON.stringify(location.state.stats));
    }
  }, [location.state]);

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
        // Aggregate stats for this risk category
        let totalSensitive = 0;
        let topOwnersMap = {};
        let recentFlagged = 0;
        let highRiskFiles = [];
        if (data[ageGroup] && data[ageGroup].sensitive_info && data[ageGroup].sensitive_info[category]) {
          const files = data[ageGroup].sensitive_info[category];
          totalSensitive = files.length;
          files.forEach(file => {
            if (file.owner) {
              topOwnersMap[file.owner] = (topOwnersMap[file.owner] || 0) + 1;
            }
            // Example: flagged in last 30 days
            if (file.flaggedTime && new Date(file.flaggedTime) > new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)) {
              recentFlagged++;
            }
          });
          // Top 3 high-risk files (by confidence or any available metric)
          highRiskFiles = files
            .sort((a, b) => (b.confidence || 0) - (a.confidence || 0))
            .slice(0, 3);
        }
        const topOwners = Object.entries(topOwnersMap)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([name, count]) => ({ name, count }));
        setStats({
          totalSensitive,
          topOwners,
          recentFlagged,
          highRiskFiles,
        });
      } catch (err) {
        setError('Failed to load risk category data.');
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, [directoryId, ageGroup, category]);

  const handleBack = () => {
    const returnTo = location.state?.returnTo || '/';
    const navState = {
      selectedDirectory: location.state?.selectedDirectory || JSON.parse(localStorage.getItem('rcid_selectedDirectory') || 'null'),
      activeTab: location.state?.activeTab || localStorage.getItem('rcid_activeTab'),
      stats: location.state?.stats || JSON.parse(localStorage.getItem('rcid_stats') || 'null'),
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
          <div className="insight-icon">🔒</div>
          <div className="insight-title">Total {category.charAt(0).toUpperCase() + category.slice(1)} Files</div>
          <div className="insight-value">{stats.totalSensitive.toLocaleString()}</div>
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
        <div className="insight-card">
          <div className="insight-icon">🆕</div>
          <div className="insight-title">Recently Flagged</div>
          <div className="insight-value">{stats.recentFlagged}</div>
        </div>
      </div>
      {/* Actionable Suggestions */}
      <div className="suggestions-row">
        <div className="suggestion-card">
          <span>💡 Review all {category} files for compliance and risk mitigation.</span>
          <button className="insight-action">Review All</button>
        </div>
        <div className="suggestion-card">
          <span>📧 Contact top owners to review their files.</span>
          <button className="insight-action">Contact Owners</button>
        </div>
      </div>
      {/* High-Risk File Cards */}
      {stats.highRiskFiles.length > 0 && (
        <div className="file-card-grid">
          {stats.highRiskFiles.map(file => (
            <div key={file.id || file.name} className="file-card">
              <div className="file-card-header">
                <span className="file-icon">🔒</span>
                <span className="file-name">{file.name}</span>
              </div>
              <div className="file-card-meta">
                <span className="file-owner-avatar">{file.owner ? file.owner[0] : '?'}</span>
                <span className="file-owner">{file.owner}</span>
                <span className="file-date">{file.modifiedTime ? new Date(file.modifiedTime).toLocaleDateString() : ''}</span>
              </div>
              <div className="file-card-footer">
                <span className="file-type">{file.sensitivityReason || category}</span>
                <span className="file-size">Confidence: {file.confidence ? Math.round(file.confidence * 100) + '%' : '-'}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {/* Floating Back Button */}
      <button className="insight-fab-back" onClick={handleBack} title="Back">
        <span>&larr;</span>
      </button>
    </div>
  );
};

export default RiskCategoryInsightsDashboard; 