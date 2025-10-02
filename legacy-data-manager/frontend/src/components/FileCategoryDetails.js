import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import config from '../config';
import './SensitiveContent.css';

const fileTypeIcons = {
  documents: '📄',
  spreadsheets: '📊',
  presentations: '📈',
  pdfs: '📕',
  images: '🖼️',
  videos: '🎬',
  others: '📁',
};

function getFileIcon(type, mimeType) {
  if (type && fileTypeIcons[type]) return fileTypeIcons[type];
  if (mimeType && mimeType.includes('image')) return fileTypeIcons.images;
  if (mimeType && mimeType.includes('video')) return fileTypeIcons.videos;
  if (mimeType && mimeType.includes('spreadsheet')) return fileTypeIcons.spreadsheets;
  if (mimeType && mimeType.includes('presentation')) return fileTypeIcons.presentations;
  if (mimeType && mimeType.includes('pdf')) return fileTypeIcons.pdfs;
  if (mimeType && mimeType.includes('document')) return fileTypeIcons.documents;
  return fileTypeIcons.others;
}

function getInitials(name) {
  if (!name) return '?';
  return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
}

const FileCategoryDetails = () => {
  const { ageGroup, fileType } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedFiles, setSelectedFiles] = useState(new Set());
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const filesPerPage = 20;

  // Restore state from location or localStorage
  const stats = location.state?.stats || JSON.parse(localStorage.getItem('stats')) || null;
  const selectedDirectory = location.state?.selectedDirectory || JSON.parse(localStorage.getItem('selectedDirectory')) || null;
  const activeTab = location.state?.activeTab || localStorage.getItem('activeTab') || 'moreThanThreeYears';
  const returnTo = location.state?.returnTo || '/';
  const directoryId = location.state?.directoryId || selectedDirectory?.id;

  // Save stats and activeTab to localStorage for back navigation
  useEffect(() => {
    if (stats) localStorage.setItem('stats', JSON.stringify(stats));
    if (activeTab) localStorage.setItem('activeTab', activeTab);
  }, [stats, activeTab]);

  const fetchFiles = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      if (!stats) {
        setError('No analysis data found. Please run analysis first.');
        return;
      }

      let url;
      if (directoryId) {
        url = `${config.apiBaseUrl}/api/v1/drive/directories/${directoryId}/files`;
      } else {
        url = `${config.apiBaseUrl}/api/v1/drive/files`;
      }

      const response = await axios.get(url, {
        params: {
          age_group: ageGroup,
          file_type: fileType,
          page: currentPage,
          per_page: filesPerPage
        }
      });

      if (!response.data || !response.data.files) {
        throw new Error('Invalid response format from server');
      }

      setFiles(response.data.files);
      setTotalPages(Math.ceil(response.data.total / filesPerPage));
    } catch (err) {
      console.error('Error fetching files:', err);
      if (err.response?.status === 404) {
        setError('No files found for this file type. Please run analysis first.');
      } else {
        setError(`Failed to fetch files: ${err.message}`);
      }
    } finally {
      setLoading(false);
    }
  }, [ageGroup, fileType, currentPage, filesPerPage, stats, directoryId]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

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
    if (selectedFiles.size === files.length) {
      setSelectedFiles(new Set());
    } else {
      setSelectedFiles(new Set(files.map(file => file.id)));
    }
  };

  const handleAction = (action) => {
    // Placeholder for action handlers
    console.log(`Action ${action} triggered for files:`, Array.from(selectedFiles));
  };

  const handleBack = () => {
    navigate(returnTo, {
      state: {
        selectedDirectory,
        activeTab,
        stats
      }
    });
  };

  // Breadcrumbs
  const breadcrumbs = [
    selectedDirectory?.name || 'Drive',
    ageGroup.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase()),
    fileType.charAt(0).toUpperCase() + fileType.slice(1)
  ];

  // Summary
  const totalFiles = files.length;
  const totalSize = files.reduce((sum, f) => sum + (parseInt(f.size) || 0), 0);
  const owners = Array.from(new Set(files.map(f => f.owner)));

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
          <button onClick={handleBack} className="back-button">
            Go Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="sensitive-content-container">
      {/* Breadcrumbs */}
      <div className="breadcrumb-bar">
        <button onClick={handleBack} className="back-button" style={{marginRight: '1rem'}}>←</button>
        {breadcrumbs.map((crumb, idx) => (
          <span key={idx} className="breadcrumb">
            {crumb}
            {idx < breadcrumbs.length - 1 && <span className="breadcrumb-sep">›</span>}
          </span>
        ))}
      </div>
      {/* Summary Bar */}
      <div className="summary-bar">
        <span><b>{totalFiles}</b> files</span>
        <span>• <b>{owners.length}</b> owner{owners.length !== 1 ? 's' : ''}</span>
        <span>• <b>{(totalSize / 1024 / 1024).toFixed(2)} MB</b> total</span>
      </div>
      {/* Bulk Actions */}
      {files.length > 0 && (
        <div className="bulk-actions-bar">
          <input
            type="checkbox"
            checked={selectedFiles.size === files.length}
            onChange={handleSelectAll}
          />
          <span style={{marginLeft: 8, marginRight: 16}}>
            {selectedFiles.size} selected
          </span>
          <button className="action-button" onClick={() => handleAction('archive')}>Archive</button>
          <button className="action-button" onClick={() => handleAction('review')}>Schedule Review</button>
          <button className="action-button" onClick={() => handleAction('delete')}>Delete</button>
        </div>
      )}
      {/* File Card Grid */}
      <div className="file-card-grid">
        {files.length === 0 ? (
          <div className="empty-state">
            <div className="empty-illustration">📂</div>
            <div>No files found in this category!</div>
          </div>
        ) : (
          files.map(file => (
            <div
              key={file.id}
              className={`file-card${selectedFiles.has(file.id) ? ' selected' : ''}`}
              onClick={() => handleSelectFile(file.id)}
            >
              <div className="file-card-header">
                <span className="file-icon">{getFileIcon(fileType, file.mimeType)}</span>
                <span className="file-name">{file.name}</span>
              </div>
              <div className="file-card-meta">
                <span className="file-owner-avatar">{getInitials(file.owner)}</span>
                <span className="file-owner">{file.owner}</span>
                <span className="file-date">{new Date(file.modifiedTime).toLocaleDateString()}</span>
              </div>
              <div className="file-card-footer">
                <span className="file-size">{file.size ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : '-'}</span>
                <span className="file-type">{file.mimeType || file.type || '-'}</span>
              </div>
              <input
                type="checkbox"
                className="file-card-checkbox"
                checked={selectedFiles.has(file.id)}
                onChange={e => { e.stopPropagation(); handleSelectFile(file.id); }}
                onClick={e => e.stopPropagation()}
              />
            </div>
          ))
        )}
      </div>
      {/* Pagination */}
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
    </div>
  );
};

export default FileCategoryDetails; 