import React, { useState, useEffect } from 'react';
import axios from 'axios';
import config from '../config';
import './DirectoryExplorer.css';

const DirectoryExplorer = ({ dashboardState, selectedDirectory }) => {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [analysisResults, setAnalysisResults] = useState(null);

  useEffect(() => {
    if (selectedDirectory) {
      fetchDirectoryContents(selectedDirectory.id);
    }
  }, [selectedDirectory]);

  useEffect(() => {
    if (selectedDirectory) {
      localStorage.setItem('fid_selectedDirectory', JSON.stringify(selectedDirectory));
    }
  }, [selectedDirectory]);

  const fetchDirectoryContents = async (folderId) => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get(`${config.apiBaseUrl}/api/v1/drive/directories/${folderId}/files`);
      setFiles(response.data.files || []);
    } catch (error) {
      console.error('Error fetching directory contents:', error);
      setError('Failed to fetch directory contents');
    } finally {
      setLoading(false);
    }
  };

  const analyzeDirectory = async () => {
    if (!selectedDirectory) return;
    
    setLoading(true);
    setError(null);
    try {
      const response = await axios.post(`${config.apiBaseUrl}/api/v1/drive/directories/${selectedDirectory.id}/analyze`);
      setAnalysisResults(response.data);
    } catch (error) {
      console.error('Error analyzing directory:', error);
      setError('Failed to analyze directory');
    } finally {
      setLoading(false);
    }
  };

  const getFileIcon = (mimeType) => {
    if (mimeType.includes('folder')) return '📁';
    if (mimeType.includes('pdf')) return '📄';
    if (mimeType.includes('image')) return '🖼️';
    if (mimeType.includes('video')) return '🎥';
    if (mimeType.includes('audio')) return '🎵';
    if (mimeType.includes('spreadsheet')) return '📊';
    if (mimeType.includes('document')) return '📝';
    return '📄';
  };

  const renderTextView = () => {
    if (!dashboardState.data) return null;
    
    let content = '';
    if (typeof dashboardState.data === 'string') {
      content = dashboardState.data;
    } else if (typeof dashboardState.data === 'object') {
      content = dashboardState.data.message || JSON.stringify(dashboardState.data, null, 2);
    }

    return (
      <div className="response-card">
        <div className="response-content">
          {content}
        </div>
      </div>
    );
  };

  const renderDirectoryView = () => {
    if (!selectedDirectory) return null;

    return (
      <div className="directory-view">
        <div className="explorer-header">
          <h2>{selectedDirectory.name}</h2>
          <button 
            className="analyze-button"
            onClick={analyzeDirectory}
            disabled={loading}
          >
            Analyze Directory
          </button>
        </div>

        {loading && (
          <div className="loading-card">
            <div className="loading-spinner"></div>
            <p>Loading...</p>
          </div>
        )}
        
        {error && (
          <div className="error-card">
            <div className="error-icon">⚠️</div>
            <div className="error-message">{error}</div>
          </div>
        )}

        {!loading && !error && files.length > 0 && (
          <div className="files-grid">
            {files.map((file) => (
              <div key={file.id} className="file-card">
                <div className="file-icon">{getFileIcon(file.mimeType)}</div>
                <div className="file-info">
                  <h3>{file.name}</h3>
                  <p>Last modified: {new Date(file.modifiedTime).toLocaleDateString()}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && !error && files.length === 0 && (
          <div className="empty-card">
            <p>No files found in this directory.</p>
          </div>
        )}
      </div>
    );
  };

  const renderAnalysisView = () => {
    if (!analysisResults) return null;

    return (
      <div className="analysis-card">
        <h2>Analysis Results</h2>
        <div className="analysis-content">
          <pre>{JSON.stringify(analysisResults, null, 2)}</pre>
        </div>
      </div>
    );
  };

  const renderErrorView = () => {
    if (!dashboardState.error) return null;

    return (
      <div className="error-card">
        <div className="error-icon">⚠️</div>
        <div className="error-message">
          {dashboardState.error}
        </div>
      </div>
    );
  };

  return (
    <div className="directory-explorer">
      {dashboardState.currentView === 'text' && renderTextView()}
      {dashboardState.currentView === 'directory' && renderDirectoryView()}
      {dashboardState.currentView === 'analysis' && renderAnalysisView()}
      {dashboardState.currentView === 'error' && renderErrorView()}
    </div>
  );
};

export default DirectoryExplorer; 