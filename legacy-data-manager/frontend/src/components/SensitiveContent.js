import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import config from '../config';
import { getRiskCategoryColor } from '../constants/colors';
import './SensitiveContent.css';

const SensitiveContent = () => {
  // Restore state from location or localStorage (move to top)
  const { ageGroup, category } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
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

  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedFiles, setSelectedFiles] = useState(new Set());
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  // No department assignment state variables needed
  const filesPerPage = 20;

  // --- Extract all sensitive files from the stats ---
  const allSensitiveFiles = React.useMemo(() => {
    if (!stats || !stats.files) return [];
    
    // Send debug info to backend to see in terminal
    fetch('http://localhost:8000/api/v1/debug/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        component: 'SensitiveContent',
        message: 'Processing stats structure',
        data: { stats }
      })
    }).catch(() => {}); // Ignore errors
    
    // Filter only sensitive files (files with sensitiveCategories)
    const sensitiveFiles = stats.files.filter(file => 
      file.sensitiveCategories && 
      Array.isArray(file.sensitiveCategories) && 
      file.sensitiveCategories.length > 0
    );
    
    console.log('Found', sensitiveFiles.length, 'sensitive files');
    return sensitiveFiles;

  }, [stats]);

  // --- Group files by sensitivity category ---
  const groupedFiles = useMemo(() => {
    const groups = {};
    allSensitiveFiles.forEach(file => {
      const category = file.sensitivityReason || 'Unknown';
      if (!groups[category]) groups[category] = [];
      groups[category].push(file);
    });
    return groups;
  }, [allSensitiveFiles]);

  // --- Collapsible state for each group ---
  const [collapsedGroups, setCollapsedGroups] = useState({});
  const toggleGroup = (category) => {
    setCollapsedGroups(prev => ({ ...prev, [category]: !prev[category] }));
  };

  // --- Selection logic per group ---
  const isGroupAllSelected = (category) => {
    const group = groupedFiles[category] || [];
    return group.length > 0 && group.every(file => selectedFiles.has(file.id));
  };
  const handleSelectAllGroup = (category) => {
    const group = groupedFiles[category] || [];
    const groupIds = group.map(file => file.id);
    setSelectedFiles(prev => {
      const newSelected = new Set(prev);
      if (isGroupAllSelected(category)) {
        groupIds.forEach(id => newSelected.delete(id));
      } else {
        groupIds.forEach(id => newSelected.add(id));
      }
      return newSelected;
    });
  };

  // --- Action bar enabled state ---
  const isAnySelected = selectedFiles.size > 0;

  // --- Executive summary metrics and pie chart data from all sensitive files ---
  // Updated to use the new weighted risk scoring system from backend
  const executiveMetrics = React.useMemo(() => {
    if (!allSensitiveFiles.length) return null;
    const totalFiles = allSensitiveFiles.length;
    
    // DEBUG: Log the risk level data being processed
    console.log('=== DEBUG: SensitiveContent processing allSensitiveFiles ===');
    console.log('Total files:', totalFiles);
    allSensitiveFiles.forEach((file, index) => {
      console.log(`File ${index + 1}: ${file.name} - RiskLevel: ${file.riskLevel}, RiskLevelLabel: ${file.riskLevelLabel}`);
    });
    
    // Use the new riskLevelLabel field from the weighted scoring system
    // This provides more accurate risk distribution based on content, age, and access patterns
    const highRiskFiles = allSensitiveFiles.filter(f => f.riskLevelLabel === 'high').length;
    const mediumRiskFiles = allSensitiveFiles.filter(f => f.riskLevelLabel === 'medium').length;
    const lowRiskFiles = allSensitiveFiles.filter(f => f.riskLevelLabel === 'low').length;
        
    // Send debug info to backend to see in terminal
    fetch('http://localhost:8000/api/v1/debug/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        component: 'SensitiveContent',
        message: 'Risk distribution calculation',
        data: { 
          totalFiles, 
          highRiskFiles, 
          mediumRiskFiles, 
          lowRiskFiles,
          allSensitiveFiles: allSensitiveFiles.map(f => ({
            name: f.name,
            riskLevel: f.riskLevel,
            riskLevelLabel: f.riskLevelLabel
          }))
        }
      })
    }).catch(() => {}); // Ignore errors
    const sensitivityBreakdown = allSensitiveFiles.reduce((acc, file) => {
      // Count the file in ALL categories it belongs to, not just the primary one
      if (file.sensitiveCategories && Array.isArray(file.sensitiveCategories)) {
        file.sensitiveCategories.forEach(category => {
          acc[category] = (acc[category] || 0) + 1;
        });
      } else if (file.allSensitiveCategories && Array.isArray(file.allSensitiveCategories)) {
        // Legacy support for old field name
        file.allSensitiveCategories.forEach(category => {
          acc[category] = (acc[category] || 0) + 1;
        });
      } else {
        // Fallback to sensitivityReason if categories array is not available
        const reason = file.sensitivityReason || 'Unknown';
        acc[reason] = (acc[reason] || 0) + 1;
      }
      return acc;
    }, {});
    const hasPII = sensitivityBreakdown.pii > 0;
    const hasFinancial = sensitivityBreakdown.financial > 0;
    const hasLegal = sensitivityBreakdown.legal > 0;
    const hasConfidential = sensitivityBreakdown.confidential > 0;
    return {
      totalFiles,
      highRiskFiles,
      mediumRiskFiles,
      lowRiskFiles,
      sensitivityBreakdown,
      compliance: {
        gdpr: hasPII,
        hipaa: hasPII,
        sox: hasFinancial,
        pci: hasFinancial
      }
    };
  }, [allSensitiveFiles]);

  // --- Paginate files for the table only ---
  useEffect(() => {
    if (!allSensitiveFiles.length) {
      setFiles([]);
      setTotalPages(1);
      return;
    }
    const startIndex = (currentPage - 1) * filesPerPage;
    const endIndex = startIndex + filesPerPage;
    const paginatedFiles = allSensitiveFiles.slice(startIndex, endIndex);
    setFiles(paginatedFiles);
    setTotalPages(Math.ceil(allSensitiveFiles.length / filesPerPage));
    if (allSensitiveFiles.length === 0) {
      setError('No sensitive files found. Please run analysis first.');
    } else {
      setError(null);
    }
  }, [allSensitiveFiles, currentPage, filesPerPage]);

  const fetchSensitiveFiles = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      if (!stats || !stats.files) {
        setError('No analysis data found. Please run analysis first.');
        return;
      }

      // Apply pagination directly to allSensitiveFiles
      const startIndex = (currentPage - 1) * filesPerPage;
      const endIndex = startIndex + filesPerPage;
      const paginatedFiles = allSensitiveFiles.slice(startIndex, endIndex);

      setFiles(paginatedFiles);
      setTotalPages(Math.ceil(allSensitiveFiles.length / filesPerPage));
      
      if (allSensitiveFiles.length === 0) {
        setError('No sensitive files found. Please run analysis first.');
      }
    } catch (err) {
      console.error('Error processing sensitive files:', err);
      setError(`Failed to process sensitive files: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [stats, currentPage, filesPerPage, allSensitiveFiles]);

  useEffect(() => {
    fetchSensitiveFiles();
  }, [fetchSensitiveFiles]);

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

  // No department assignment functions needed
  
  const handleBack = () => {
    navigate(returnTo, {
      state: {
        selectedDirectory,
        activeTab,
        stats
      }
    });
  };

  const handleHome = () => {
    navigate('/', {
      state: {
        selectedDirectory,
        activeTab,
        stats
      }
    });
  };

  // Calculate pie chart styles for risk and sensitivity (inside component, before return)
  let pieStyle = {};
  let sensitivityPieStyle = {};
  if (executiveMetrics) {
    // Risk pie
    const high = (executiveMetrics.highRiskFiles / executiveMetrics.totalFiles) * 100;
    const medium = (executiveMetrics.mediumRiskFiles / executiveMetrics.totalFiles) * 100;
    const low = 100 - high - medium;
    pieStyle = {
      background: `conic-gradient(
        #1e40af 0% ${high}%,
        #3b82f6 ${high}% ${high + medium}%,
        #60a5fa ${high + medium}% 100%
      )`
    };
    // Sensitivity pie with weighted distribution
    // Define category weights (same as in backend)
    const categoryWeights = {
      'confidential': 0.4, // Highest risk
      'pii': 0.3,          // High risk
      'financial': 0.2,    // Medium-high risk
      'legal': 0.1         // Medium risk
    };
    
    // Calculate total weight for normalization
    const sensitivityCategories = Object.entries(executiveMetrics.sensitivityBreakdown);
    const totalWeight = sensitivityCategories.reduce((sum, [category, count]) => {
      return sum + (count * (categoryWeights[category] || 0.1));
    }, 0);
    
    // Generate pie segments based on weighted importance
    let currentPercent = 0;
    const sensitivitySegments = sensitivityCategories
      // Sort by weight (highest first) to ensure consistent segment order
      .sort(([catA], [catB]) => (categoryWeights[catB] || 0) - (categoryWeights[catA] || 0))
      .map(([category, count]) => {
        // Use centralized color system
        const categoryColors = {
          'confidential': getRiskCategoryColor('confidential'),
          'pii': getRiskCategoryColor('pii'),
          'financial': getRiskCategoryColor('financial'),
          'legal': getRiskCategoryColor('legal')
        };
        
        // Calculate weighted percentage (category count * weight / total weight)
        const weight = categoryWeights[category] || 0.1;
        const weightedValue = count * weight;
        const percent = totalWeight > 0 ? (weightedValue / totalWeight * 100) : 0;
        
        const segment = `${categoryColors[category] || '#757575'} ${currentPercent}% ${currentPercent + percent}%`;
      currentPercent += percent;
      return segment;
    });
    sensitivityPieStyle = {
      background: `conic-gradient(${sensitivitySegments.join(', ')})`
    };
  }

  // --- Category icon helper ---
  const iconForCategory = (category) => {
    switch (category.toLowerCase()) {
      case 'pii': return '👤';
      case 'financial': return '💰';
      case 'legal': return '⚖️';
      case 'confidential': return '🔒';
      default: return '📄';
    }
  };

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
      <div className="sensitive-content-header">
        <div className="header-left">
          <div className="navigation-buttons">
            <button onClick={handleHome} className="nav-button home-button" title="Go to Home">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                <polyline points="9,22 9,12 15,12 15,22"/>
              </svg>
            </button>
            <button onClick={handleBack} className="nav-button back1-button" title="Go Back">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="15,18 9,12 15,6"/>
              </svg>
            </button>
          </div>
          <h2>
            {category 
              ? `${category} Files - ${ageGroup}` 
              : 'Sensitive Content Overview'
            }
          </h2>
        </div>
        <div className="action-buttons">
          {/* Action buttons moved to table header */}
        </div>
      </div>

      {/* Executive Summary Section */}
      {executiveMetrics && (
        <div className="executive-summary">
          <div className="summary-header">
            <h3>Executive Summary</h3>
            <div className="summary-timestamp">
              Last Updated: {new Date().toLocaleDateString()}
            </div>
          </div>
          
          <div className="summary-metrics">
            <div className="metric-card total-files">
              <div className="metric-icon" style={{background: '#eff6ff', color: '#1e40af'}}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="12" width="4" height="8"/><rect x="9" y="8" width="4" height="12"/><rect x="15" y="4" width="4" height="16"/></svg>
              </div>
              <div className="metric-content">
                <div className="metric-value">{executiveMetrics.totalFiles}</div>
                <div className="metric-label">Total Sensitive Files</div>
              </div>
            </div>
            
            <div className="metric-card high-risk">
              <div className="metric-icon" style={{background: '#eff6ff', color: '#1e40af'}}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="#1e40af" stroke="none"><circle cx="12" cy="12" r="10"/></svg>
              </div>
              <div className="metric-content">
                <div className="metric-value">{executiveMetrics.highRiskFiles}</div>
                <div className="metric-label">High Risk Files</div>
              </div>
            </div>
            
            <div className="metric-card medium-risk">
              <div className="metric-icon" style={{background: '#f0f9ff', color: '#3b82f6'}}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="#3b82f6" stroke="none"><circle cx="12" cy="12" r="10"/></svg>
              </div>
              <div className="metric-content">
                <div className="metric-value">{executiveMetrics.mediumRiskFiles}</div>
                <div className="metric-label">Medium Risk Files</div>
              </div>
            </div>
            
            <div className="metric-card low-risk">
              <div className="metric-icon" style={{background: '#f8fafc', color: '#60a5fa'}}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="#60a5fa" stroke="none"><circle cx="12" cy="12" r="10"/></svg>
              </div>
              <div className="metric-content">
                <div className="metric-value">{executiveMetrics.lowRiskFiles}</div>
                <div className="metric-label">Low Risk Files</div>
              </div>
            </div>
          </div>
          
          <div className="compliance-section">
            <h4>Compliance Status</h4>
            <div className="compliance-grid">
              <div className={`compliance-item ${executiveMetrics.compliance.gdpr ? 'non-compliant' : 'compliant'}`}>
                <div className="compliance-icon">🇪🇺</div>
                <div className="compliance-label">GDPR</div>
                <div className="compliance-status">
                  {executiveMetrics.compliance.gdpr ? '⚠️ Requires Review' : '✅ Compliant'}
                </div>
              </div>
              
              <div className={`compliance-item ${executiveMetrics.compliance.hipaa ? 'non-compliant' : 'compliant'}`}>
                <div className="compliance-icon">🏥</div>
                <div className="compliance-label">HIPAA</div>
                <div className="compliance-status">
                  {executiveMetrics.compliance.hipaa ? '⚠️ Requires Review' : '✅ Compliant'}
                </div>
              </div>
              
              <div className={`compliance-item ${executiveMetrics.compliance.sox ? 'non-compliant' : 'compliant'}`}>
                <div className="compliance-icon">📈</div>
                <div className="compliance-label">SOX</div>
                <div className="compliance-status">
                  {executiveMetrics.compliance.sox ? '⚠️ Requires Review' : '✅ Compliant'}
                </div>
              </div>
              
              <div className={`compliance-item ${executiveMetrics.compliance.pci ? 'non-compliant' : 'compliant'}`}>
                <div className="compliance-icon">💳</div>
                <div className="compliance-label">PCI-DSS</div>
                <div className="compliance-status">
                  {executiveMetrics.compliance.pci ? '⚠️ Requires Review' : '✅ Compliant'}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Risk Visualization Section */}
      {executiveMetrics && (
        <div className="risk-visualization">
          <div className="visualization-header">
            <h3>Risk Distribution Analysis</h3>
          </div>
          <div className="visualization-content">
            <div className="risk-chart">
              <h4>Risk Distribution</h4>
              <div className="pie-chart-container">
                <div className="pie-chart" style={pieStyle}>
                  <div className="pie-center">
                    <div className="total-files">{executiveMetrics.totalFiles}</div>
                    <div className="total-label">Total Files</div>
                  </div>
                </div>
                <div className="pie-legend">
                  <div className="legend-item">
                    <div className="legend-color high-risk"></div>
                    <div className="legend-text">
                      <span className="legend-label">High Risk</span>
                      <span className="legend-value">{executiveMetrics.highRiskFiles} ({Math.round((executiveMetrics.highRiskFiles / executiveMetrics.totalFiles) * 100)}%)</span>
                    </div>
                  </div>
                  <div className="legend-item">
                    <div className="legend-color medium-risk"></div>
                    <div className="legend-text">
                      <span className="legend-label">Medium Risk</span>
                      <span className="legend-value">{executiveMetrics.mediumRiskFiles} ({Math.round((executiveMetrics.mediumRiskFiles / executiveMetrics.totalFiles) * 100)}%)</span>
                    </div>
                  </div>
                  <div className="legend-item">
                    <div className="legend-color low-risk"></div>
                    <div className="legend-text">
                      <span className="legend-label">Low Risk</span>
                      <span className="legend-value">{executiveMetrics.lowRiskFiles} ({Math.round((executiveMetrics.lowRiskFiles / executiveMetrics.totalFiles) * 100)}%)</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="sensitivity-chart">
              <h4>Risk Categories</h4>
              <div className="pie-chart-container">
                <div className="pie-chart" style={sensitivityPieStyle}>
                  <div className="pie-center">
                    <div className="total-files">{executiveMetrics.totalFiles}</div>
                    <div className="total-label">Total Files</div>
                  </div>
                </div>
                <div className="pie-legend">
                  {Object.entries(executiveMetrics.sensitivityBreakdown)
                    .sort(([catA], [catB]) => {
                      // Sort by weight (highest first) to match pie chart order
                      const categoryWeights = {
                        'confidential': 0.4,
                        'pii': 0.3,
                        'financial': 0.2,
                        'legal': 0.1
                      };
                      return (categoryWeights[catB] || 0) - (categoryWeights[catA] || 0);
                    })
                    .map(([category, count]) => {
                      // Use centralized color system
                      const categoryColors = {
                        'confidential': getRiskCategoryColor('confidential'),
                        'pii': getRiskCategoryColor('pii'),
                        'financial': getRiskCategoryColor('financial'),
                        'legal': getRiskCategoryColor('legal')
                      };
                    const icons = {
                      'pii': '👤',
                      'financial': '💰',
                      'legal': '⚖️',
                      'confidential': '🔒'
                    };
                      
                      // Calculate weighted percentage for this category
                      const categoryWeights = {
                        'confidential': 0.4,
                        'pii': 0.3,
                        'financial': 0.2,
                        'legal': 0.1
                      };
                      const weight = categoryWeights[category] || 0.1;
                      
                      // Calculate total weighted value for normalization
                      const totalWeight = Object.entries(executiveMetrics.sensitivityBreakdown).reduce((sum, [cat, cnt]) => {
                        return sum + (cnt * (categoryWeights[cat] || 0.1));
                      }, 0);
                      
                      // Calculate weighted percentage
                      const weightedValue = count * weight;
                      const weightedPercent = totalWeight > 0 ? Math.round((weightedValue / totalWeight) * 100) : 0;
                      
                    return (
                      <div key={category} className="legend-item">
                          <div className="legend-color" style={{background: categoryColors[category] || '#757575'}}></div>
                        <div className="legend-text">
                          <span className="legend-label">
                            {icons[category] || '📄'} {category.toUpperCase()}
                          </span>
                            <span className="legend-value">
                              {count} ({weightedPercent}% weighted)
                            </span>
                          </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Grouped, collapsible file tables */}
      <div className="grouped-file-list">
        {Object.entries(groupedFiles).map(([category, groupFiles]) => {
          const groupSelected = groupFiles.some(file => selectedFiles.has(file.id));
          const showActionBar = groupSelected;
          const isScrollable = groupFiles.length > 20;
          return (
            <div key={category} className="file-group-card">
              <div className="file-group-header">
                <div className="header-left" onClick={() => toggleGroup(category)}>
                  <span className="category-icon">{iconForCategory(category)}</span>
                  <span className="file-group-title">{category.toUpperCase()}</span>
                  <span className="file-group-count">{groupFiles.length} files</span>
                </div>
                <div className="header-right">
                  <div className="header-action-buttons">
                    <button 
                      className="header-action-btn archive-btn" 
                      onClick={(e) => {
                        e.stopPropagation();
                        handleAction('archive');
                      }}
                      title="Archive"
                      disabled={!isAnySelected}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="21 8 21 21 3 21 3 8"></polyline>
                        <rect x="1" y="3" width="22" height="5"></rect>
                        <line x1="10" y1="12" x2="14" y2="12"></line>
                      </svg>
                    </button>
                    <button 
                      className="header-action-btn delete-btn" 
                      onClick={(e) => {
                        e.stopPropagation();
                        handleAction('delete');
                      }}
                      title="Delete"
                      disabled={!isAnySelected}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                      </svg>
                    </button>
                    <button 
                      className="header-action-btn review-btn" 
                      onClick={(e) => {
                        e.stopPropagation();
                        handleAction('review');
                      }}
                      title="Schedule Review"
                      disabled={!isAnySelected}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polyline points="12 6 12 12 16 14"></polyline>
                      </svg>
                    </button>
                    <button 
                      className="header-action-btn remind-btn" 
                      onClick={(e) => {
                        e.stopPropagation();
                        handleAction('remind');
                      }}
                      title="Remind Me"
                      disabled={!isAnySelected}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                        <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
                      </svg>
                    </button>
                  </div>
                  <span className="chevron-svg" aria-label="Expand/collapse" onClick={() => toggleGroup(category)}>
                    {collapsedGroups[category] ? (
                      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M7 8l3 3 3-3" stroke="#64748b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    ) : (
                      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M8 7l3 3-3 3" stroke="#64748b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    )}
                  </span>
                </div>
              </div>
              {!collapsedGroups[category] && (
                <div className="file-group-content">
                  {/* Action buttons moved to header */}
                  <div className="file-group-table-wrapper" style={isScrollable ? {maxHeight: '400px', overflowY: 'auto'} : {}}>
                    <table className="file-group-table">
                      <thead>
                        <tr>
                          <th>
                            <div className="table-header-actions">
                              <input 
                                type="checkbox" 
                                checked={isGroupAllSelected(category)} 
                                onChange={() => handleSelectAllGroup(category)} 
                              />
                            </div>
                          </th>
                          <th>File Name</th>
                          <th>File Age</th>
                          <th>Last Modified</th>
                          <th>Risk Categories</th>
                          <th>Risk Level</th>
                        </tr>
                      </thead>
                      <tbody>
                        {groupFiles.map(file => (
                          <tr key={file.id} className={selectedFiles.has(file.id) ? 'selected' : ''}>
                            <td><input type="checkbox" checked={selectedFiles.has(file.id)} onChange={() => handleSelectFile(file.id)} /></td>
                            <td>{file.name}</td>
                            <td>
                              {file.ageGroup === 'moreThanThreeYears' && '>3 years'}
                              {file.ageGroup === 'oneToThreeYears' && '1-3 years'}
                              {file.ageGroup === 'lessThanOneYear' && '<1 year'}
                              {!['moreThanThreeYears', 'oneToThreeYears', 'lessThanOneYear'].includes(file.ageGroup) && file.ageGroup}
                            </td>
                            <td>{new Date(file.modifiedTime).toLocaleDateString()}</td>
                            <td>
                              {file.sensitivityExplanation ? 
                                <div 
                                  className="keywords-found"
                                  title={file.sensitivityExplanation.split(';')
                                    .map(explanation => {
                                      const keywordsMatch = explanation.match(/Found (.*?) in/);
                                      return keywordsMatch ? keywordsMatch[1] : explanation;
                                    }).join(', ')}
                                >
                                  {file.sensitivityExplanation.split(';')
                                    .map(explanation => {
                                      // Extract category and keywords
                                      const categoryMatch = explanation.match(/in (.*?) category/);
                                      const keywordsMatch = explanation.match(/Found (.*?) in/);
                                      
                                      const category = categoryMatch ? categoryMatch[1] : '';
                                      const keywords = keywordsMatch ? keywordsMatch[1] : explanation;
                                      
                                      // Assign weight based on category for sorting
                                      let weight = 0;
                                      if (category === 'confidential') weight = 4;
                                      else if (category === 'pii') weight = 3;
                                      else if (category === 'financial') weight = 2;
                                      else if (category === 'legal') weight = 1;
                                      
                                      return { keywords, category, weight };
                                    })
                                    .sort((a, b) => b.weight - a.weight) // Sort by weight (highest first)
                                    .slice(0, 5) // Take top 5 by impact
                                    .map((item, i) => (
                                      <span key={i} className={`keyword-chip ${item.category}`} title={`Category: ${item.category}`}>
                                        {item.keywords}
                                      </span>
                                    ))}
                                  {file.sensitivityExplanation.split(';').length > 5 && 
                                    <span className="keyword-chip more-chip">
                                      +{file.sensitivityExplanation.split(';').length - 5} more
                                    </span>
                                  }
                                </div>
                                : 
                                <span className={`sensitivity-badge blue-badge ${file.sensitivityReason}`}>{file.sensitivityReason?.toUpperCase()}</span>
                              }
                            </td>
                            <td>
                              <span className={`risk-level blue-badge risk-${file.riskLevelLabel || 'unknown'}`}>
                                {file.riskLevelLabel ? file.riskLevelLabel.toUpperCase() : 'UNKNOWN'}
                              </span>
                              {file.riskLevel && (
                                <span className="risk-score">({Math.round(file.riskLevel * 100)}%)</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

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
      
      {/* No department assignment modal needed */}
    </div>
  );
};

export default SensitiveContent; 