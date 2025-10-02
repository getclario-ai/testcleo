import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import config from '../config';
import './SensitiveContent.css';

const defaultStats = {
  docCount: 0,
  duplicateDocuments: 0,
  sensitiveDocuments: 0,
  ageDistribution: {
    moreThanThreeYears: { types: {}, risks: {} },
    oneToThreeYears: { types: {}, risks: {} },
    lessThanOneYear: { types: {}, risks: {} }
  }
};

const ReviewSensitiveFiles = () => {
  const navigate = useNavigate();
  const location = useLocation();
  // Route context restoration
  useEffect(() => {
    // Save the current route and state to localStorage
    localStorage.setItem('fid_lastRoute', JSON.stringify({
      pathname: location.pathname,
      state: location.state
    }));
  }, [location.pathname, location.state]);

  // On mount, add more detailed logging
  useEffect(() => {
    // Do not attempt to restore context or navigate if we're already on the page
    // This prevents infinite loops of redirects when context is missing
    // eslint-disable-next-line
  }, []);

  // Parse stats safely with defensive default values
  let parsedStats = defaultStats;
  try {
    if (location.state?.stats) {
      parsedStats = location.state.stats;
    } else if (localStorage.getItem('fid_stats')) {
      parsedStats = JSON.parse(localStorage.getItem('fid_stats'));
    }
  } catch (e) {
    console.error('Error parsing stats from localStorage:', e);
  }
  
  // Parse selectedDirectory safely
  let parsedSelectedDirectory = null;
  try {
    if (location.state?.selectedDirectory) {
      parsedSelectedDirectory = location.state.selectedDirectory;
    } else if (localStorage.getItem('fid_selectedDirectory')) {
      parsedSelectedDirectory = JSON.parse(localStorage.getItem('fid_selectedDirectory'));
    }
  } catch (e) {
    console.error('Error parsing selectedDirectory from localStorage:', e);
  }
  
  // Use the safely parsed values
  const stats = parsedStats;
  const selectedDirectory = parsedSelectedDirectory;
  const directoryId = location.state?.directoryId || selectedDirectory?.id;
  const returnTo = location.state?.returnTo || '/';
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedFiles, setSelectedFiles] = useState(new Set());
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const filesPerPage = 20;

  useEffect(() => {
    if (stats) localStorage.setItem('fid_stats', JSON.stringify(stats));
    if (selectedDirectory) localStorage.setItem('fid_selectedDirectory', JSON.stringify(selectedDirectory));
  }, [stats, selectedDirectory]);

  useEffect(() => {
    if (!directoryId) {
      setError('No directory context found. Please select a directory and run analysis.');
      setLoading(false);
      return;
    }
    const fetchAllSensitiveFiles = async () => {
      setLoading(true);
      setError(null);
      try {
        let url;
        if (directoryId) {
          url = `${config.apiBaseUrl}/api/v1/drive/directories/${directoryId}/analyze`;
        } else {
          url = `${config.apiBaseUrl}/api/v1/drive/analyze`;
        }
        
        console.log('Fetching analysis data from:', url);
        const response = await axios.post(url);
        console.log('Analysis response:', response.status, response.statusText);
        
        if (!response.data) {
          throw new Error('Empty response from server');
        }
        
        const data = response.data;
        console.log('Analysis data structure:', Object.keys(data));
        
        // Collect all sensitive files across all age groups and categories
        const ageGroups = ['moreThanThreeYears', 'oneToThreeYears', 'lessThanOneYear'];
        let allFiles = [];
        ageGroups.forEach(group => {
          const groupData = data[group];
          if (!groupData || !groupData.sensitive_info) return;
          Object.entries(groupData.sensitive_info).forEach(([category, findings]) => {
            if (!Array.isArray(findings)) return;
            findings.forEach(finding => {
              if (finding.file) {
                allFiles.push({
                  ...finding.file,
                  sensitivityReason: category,
                  riskLevel: finding.confidence || 0.8
                });
              }
            });
          });
        });
        // Remove duplicates by file id
        const uniqueFiles = Array.from(new Map(allFiles.map(f => [f.id, f])).values());
        setFiles(uniqueFiles);
        setTotalPages(Math.max(1, Math.ceil(uniqueFiles.length / filesPerPage)));
      } catch (err) {
        setError('Failed to load sensitive files.');
      } finally {
        setLoading(false);
      }
    };
    fetchAllSensitiveFiles();
  }, [directoryId]);

  const handleSelectFile = (fileId) => {
    setSelectedFiles(prev => {
      const newSelected = new Set(prev);
      if (newSelected.has(fileId)) {
        newSelected.delete(fileId);
      } else {
        newSelected.add(fileId);
      }
      return newSelected;
    });
  };

  const handleSelectAll = () => {
    const pageFiles = paginatedFiles();
    if (selectedFiles.size === pageFiles.length) {
      setSelectedFiles(new Set());
    } else {
      setSelectedFiles(new Set(pageFiles.map(file => file.id)));
    }
  };

  const handleAction = (action) => {
    // Placeholder for action handlers
    alert(`Action '${action}' triggered for files: ${Array.from(selectedFiles).join(', ')}`);
  };

  const handleBack = () => {
    // Use lastRoute if available
    const lastRoute = localStorage.getItem('fid_lastRoute');
    if (lastRoute) {
      const { pathname, state } = JSON.parse(lastRoute);
      if (pathname && state) {
        navigate(pathname, { state });
        return;
      }
    }
    navigate(returnTo, {
      state: {
        selectedDirectory,
        stats
      }
    });
  };

  const paginatedFiles = () => {
    const start = (currentPage - 1) * filesPerPage;
    return files.slice(start, start + filesPerPage);
  };

  // MODIFY this block to render differently if context is missing
  // Instead of blocking rendering, show warning with dashboard link
  const missingContext = !stats || !('docCount' in stats);
  
  if (loading) {
    return (
      <div className="sensitive-content-container">
        <div className="loading-spinner">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sensitive-content-container">
        <div className="error-message">
          <p>{error}</p>
          <button onClick={() => navigate('/')} className="back-button">
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="sensitive-content-container">
      {missingContext && (
        <div className="warning-banner">
          <p>Missing dashboard context. Please return to the dashboard and run analysis again.</p>
          <button 
            onClick={() => {
              // Clear attempted flag before returning
              window.attemptedContextRestore = false;
              navigate('/', { replace: true });
            }} 
            className="dashboard-button"
          >
            Return to Dashboard
          </button>
        </div>
      )}
      
      <div className="sensitive-content-header">
        <div className="header-left">
          <button onClick={handleBack} className="back-button">
            ← Back
          </button>
          <h2>Review Sensitive Files</h2>
        </div>
        <div className="action-buttons">
          <button
            className="action-button delete"
            disabled={selectedFiles.size === 0}
            onClick={() => handleAction('delete')}
          >
            Delete
          </button>
          <button
            className="action-button archive"
            disabled={selectedFiles.size === 0}
            onClick={() => handleAction('archive')}
          >
            Archive
          </button>
          <button
            className="action-button review"
            disabled={selectedFiles.size === 0}
            onClick={() => handleAction('review')}
          >
            Schedule Review
          </button>
        </div>
      </div>

      {files.length === 0 ? (
        <div className="empty-card">
          <p>No sensitive files found to review.</p>
        </div>
      ) : (
        <div className="sensitive-content-table">
          <table>
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    checked={selectedFiles.size === paginatedFiles().length && paginatedFiles().length > 0}
                    onChange={handleSelectAll}
                  />
                </th>
                <th>File Name</th>
                <th>Location</th>
                <th>Last Modified</th>
                <th>Owner</th>
                <th>Sensitivity Reason</th>
                <th>Risk Level</th>
              </tr>
            </thead>
            <tbody>
              {paginatedFiles().map(file => (
                <tr key={file.id} className={selectedFiles.has(file.id) ? 'selected' : ''}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedFiles.has(file.id)}
                      onChange={() => handleSelectFile(file.id)}
                    />
                  </td>
                  <td>{file.name}</td>
                  <td>{file.location || '-'}</td>
                  <td>{file.modifiedTime ? new Date(file.modifiedTime).toLocaleDateString() : '-'}</td>
                  <td>{file.owner || '-'}</td>
                  <td>{file.sensitivityReason}</td>
                  <td>{file.riskLevel}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {files.length > 0 && (
        <div className="pagination">
          <button
            onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
            disabled={currentPage === 1}
          >
            Previous
          </button>
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
            disabled={currentPage === totalPages}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};

export default ReviewSensitiveFiles; 