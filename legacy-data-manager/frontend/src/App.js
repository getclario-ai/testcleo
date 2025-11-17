import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import AuthCallback from './components/AuthCallback';
import Cleo from './components/Cleo';
import SensitiveContent from './components/SensitiveContent';
import FileInsightsDashboard from './components/FileInsightsDashboard';
import RiskCategoryInsightsDashboard from './components/RiskCategoryInsightsDashboard';
import ReviewSensitiveFiles from './components/ReviewSensitiveFiles';
import DepartmentDashboard from './components/DepartmentDashboard';
import AuditTrailDashboard from './components/AuditTrailDashboard';
import FileTypeChart from './components/FileTypeChart';
import RiskCategoryChart from './components/RiskCategoryChart';
import { getFileTypeColor, getRiskCategoryColor } from './constants/colors';
import './App.css';
import config from './config';

function AppContent() {
  const navigate = useNavigate();
  const location = useLocation();
  const [selectedDirectory, setSelectedDirectory] = useState(() => {
    // Try to restore state from location or localStorage
    return location.state?.selectedDirectory || JSON.parse(localStorage.getItem('fid_selectedDirectory')) || null;
  });
  const [activeTab, setActiveTab] = useState(() => {
    return location.state?.activeTab || localStorage.getItem('fid_activeTab') || 'moreThanThreeYears';
  });
  // TODO: Reserved for future use - typeSort state for file type sorting
  // const [typeSort, setTypeSort] = useState('count'); // 'count' or 'size'
  const [stats, setStats] = useState(() => {
    return location.state?.stats || JSON.parse(localStorage.getItem('fid_stats')) || {
      docCount: 0,
      duplicateDocuments: 0,
      sensitiveDocuments: 0,
      files: [],
      riskDistribution: {
        high: 0,
        medium: 0,
        low: 0
      },
      departmentDistribution: {}
    };
  });

  // Save state to localStorage when it changes
  useEffect(() => {
    if (selectedDirectory) {
      localStorage.setItem('fid_selectedDirectory', JSON.stringify(selectedDirectory));
    }
  }, [selectedDirectory]);

  // Save stats to localStorage when they change
  useEffect(() => {
    if (stats) {
      localStorage.setItem('fid_stats', JSON.stringify(stats));
    }
  }, [stats]);

  // Check for directory parameter in URL (from Slack deep link)
  // Only run when URL search changes, not when selectedDirectory changes
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const directoryId = urlParams.get('directory');
    
    // Only process URL parameter if it's different from current selection
    // This prevents overwriting when user scans from Cleo
    if (directoryId && (!selectedDirectory || selectedDirectory.id !== directoryId)) {
      console.log('Loading directory from URL parameter:', directoryId);
      
      // Auto-trigger analysis for this directory
      // First, set it as selected
      setSelectedDirectory({ id: directoryId, name: 'Loading...' });
      
      // Then fetch directory name and trigger analysis
      const analyzeFromUrl = async () => {
        // Capture the directoryId at the start of the request to prevent race conditions
        const requestedDirectoryId = directoryId;
        
        try {
          // First, get directory metadata to get the name
          let directoryName = requestedDirectoryId; // Default to ID if name unavailable
          try {
            const metadataResponse = await fetch(`${config.apiBaseUrl}/api/v1/drive/files/${requestedDirectoryId}`, {
              method: 'GET',
              headers: {
                'Accept': 'application/json'
              },
              credentials: 'include'
            });
            
            if (metadataResponse.ok) {
              const metadata = await metadataResponse.json();
              if (metadata.name) {
                directoryName = metadata.name;
                // Update selectedDirectory with name immediately
                setSelectedDirectory({ id: requestedDirectoryId, name: directoryName });
              }
            }
          } catch (error) {
            console.warn('Could not fetch directory metadata:', error);
          }
          
          // Now trigger the analysis
          const response = await fetch(`${config.apiBaseUrl}/api/v1/drive/directories/${requestedDirectoryId}/analyze`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'application/json'
            },
            credentials: 'include'
          });
          
          if (response.ok) {
            const data = await response.json();
            
            // Use directory from response if available (has name), otherwise use what we fetched
            const responseDirectory = data.directory || {};
            const responseDirectoryId = responseDirectory.id || requestedDirectoryId;
            const finalDirectoryName = responseDirectory.name || directoryName || requestedDirectoryId;
            
            // Guard: Only update stats if this response matches the directory we requested
            // This prevents race conditions where multiple requests complete out of order
            if (responseDirectoryId !== requestedDirectoryId) {
              console.log(`Ignoring response for ${responseDirectoryId} - requested ${requestedDirectoryId}`);
              return;
            }
            
            // Also check if selectedDirectory has changed since we started the request
            // (to prevent overwriting with stale data if user switched directories)
            const currentSelectedId = selectedDirectory?.id;
            if (currentSelectedId && currentSelectedId !== requestedDirectoryId) {
              console.log(`Ignoring response for ${requestedDirectoryId} - user switched to ${currentSelectedId}`);
              return;
            }
            
            // Transform data structure
            const transformedData = {
              directory: { id: responseDirectoryId, name: finalDirectoryName },
              docCount: data.stats?.total_documents || 0,
              duplicateDocuments: data.stats?.total_duplicates || 0,
              sensitiveDocuments: data.stats?.total_sensitive || 0,
              departmentDistribution: data.stats?.by_department || {},
              riskDistribution: data.stats?.by_risk_level || {
                high: 0,
                medium: 0,
                low: 0
              },
              files: data.files || []
            };
            
            setStats(transformedData);
            setSelectedDirectory(transformedData.directory);
            console.log(`Auto-loaded directory analysis from URL for ${responseDirectoryId}`);
          }
        } catch (error) {
          console.error('Error loading directory from URL:', error);
        }
      };
      
      analyzeFromUrl();
    }
    // Only depend on location.search, not selectedDirectory
    // This prevents the effect from running when selectedDirectory changes from Cleo scans
  }, [location.search]);

  const handleCleoCommand = (command) => {
    switch (command.name.toLowerCase()) {
      case 'list directories':
        // Just trigger the directory listing in Cleo
        break;
      case 'analyze':
        // Analysis will be handled by Cleo component
        break;
      case 'clean':
        // Cleaning command will be handled by Cleo component
        break;
      default:
        console.warn('Unknown command:', command.name);
    }
  };

  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    const stored = localStorage.getItem('isAuthenticated') === 'true';
    console.log('Initial auth state from localStorage:', stored);
    return stored;
  });
  const [authChecked, setAuthChecked] = useState(false);
  const [loading, setLoading] = useState(true);

  // Check auth status from backend on mount (important after OAuth redirect)
  useEffect(() => {
    const checkAuthStatus = async () => {
      console.log('Checking auth status from backend...');
      try {
        const response = await fetch(`${config.apiBaseUrl}/api/v1/auth/google/status`, {
          method: 'GET',
          credentials: 'include',
          headers: {
            'Accept': 'application/json',
          }
        });

        if (response.ok) {
          const data = await response.json();
          console.log('Auth status from backend:', data);
          const authenticated = data.isAuthenticated === true;
          
          setIsAuthenticated(authenticated);
          setAuthChecked(true);
          
          if (authenticated) {
            localStorage.setItem('isAuthenticated', 'true');
          } else {
            localStorage.removeItem('isAuthenticated');
          }
        } else {
          console.warn('Auth status check failed:', response.status);
          setIsAuthenticated(false);
          setAuthChecked(true);
          localStorage.removeItem('isAuthenticated');
        }
      } catch (error) {
        console.error('Error checking auth status:', error);
        setIsAuthenticated(false);
        setAuthChecked(true);
        localStorage.removeItem('isAuthenticated');
      } finally {
        setLoading(false);
      }
    };

    checkAuthStatus();
  }, []); // Run once on mount

  const handleStatsUpdate = (newStats) => {
    console.log('Received new stats in App.js:', newStats);
    
    if (newStats.directory) {
      console.log('Updating selectedDirectory to:', newStats.directory);
      setSelectedDirectory(newStats.directory);
    } else {
      console.warn('handleStatsUpdate: newStats.directory is missing!', newStats);
    }
    
    setStats(newStats);
  };

  const handleLogout = async () => {
    console.log('Logging out...');
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/v1/auth/google/logout`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
        }
      });

      if (response.ok) {
        console.log('Logout successful');
        // Clear auth state
        setIsAuthenticated(false);
        localStorage.removeItem('isAuthenticated');
        setSelectedDirectory(null);
        setStats(null);
        // Refresh page to clear all state
        window.location.href = '/';
      } else {
        console.error('Logout failed:', response.status);
        // Still clear local state even if backend call fails
        setIsAuthenticated(false);
        localStorage.removeItem('isAuthenticated');
        window.location.href = '/';
      }
    } catch (error) {
      console.error('Error during logout:', error);
      // Still clear local state even if backend call fails
      setIsAuthenticated(false);
      localStorage.removeItem('isAuthenticated');
      window.location.href = '/';
    }
  };

  // TODO: handleViewDetails and handleViewFileCategoryDetails are reserved for future use
  // const handleViewDetails = (category) => {
  //   navigate(`/sensitive-content/${activeTab}/${category}`, {
  //     state: {
  //       selectedDirectory,
  //       activeTab,
  //       stats,
  //       returnTo: location.pathname,
  //       directoryId: selectedDirectory?.id
  //     }
  //   });
  // };

  // const handleViewFileCategoryDetails = (fileType) => {
  //   navigate(`/file-category/${activeTab}/${fileType}`, {
  //     state: {
  //       selectedDirectory,
  //       activeTab,
  //       stats,
  //       returnTo: location.pathname,
  //       directoryId: selectedDirectory?.id
  //     }
  //   });
  // };

  // Add the sensitive documents click handler
  const handleSensitiveDocumentsClick = () => {
    console.log('Sensitive documents tile clicked!');
    navigate('/sensitive-content', {
      state: {
        selectedDirectory,
        activeTab,
        stats,
        returnTo: location.pathname,
        directoryId: selectedDirectory?.id
      }
    });
  };

  // TODO: Reserved for future use - formatBytes, fileTypeColors, groupFindingsByCategory
  // const formatBytes = (bytes) => {
  //   if (bytes === 0) return '0 B';
  //   const k = 1024;
  //   const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  //   const i = Math.floor(Math.log(bytes) / Math.log(k));
  //   return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  // };

  // const fileTypeColors = {
  //   documents: getFileTypeColor('documents'),
  //   spreadsheets: getFileTypeColor('spreadsheets'),
  //   presentations: getFileTypeColor('presentations'),
  //   pdfs: getFileTypeColor('pdfs'),
  //   images: getFileTypeColor('images'),
  //   others: getFileTypeColor('others')
  // };

  // Helper function to group findings by their primary category
  // const groupFindingsByCategory = (risks) => {
  //   const groupedRisks = {
  //     pii: { count: 0, items: [], confidence: 0 },
  //     financial: { count: 0, items: [], confidence: 0 },
  //     legal: { count: 0, items: [], confidence: 0 },
  //     confidential: { count: 0, items: [], confidence: 0 }
  //   };
  //
  //   Object.entries(risks).forEach(([type, info]) => {
  //     if (!info || !info.count) return;
  //     let category = 'confidential';
  //     if (type.includes('pii') || type.includes('email') || type.includes('phone') || type.includes('address')) {
  //       category = 'pii';
  //     } else if (type.includes('financial') || type.includes('bank') || type.includes('credit')) {
  //       category = 'financial';
  //     } else if (type.includes('legal') || type.includes('contract') || type.includes('agreement')) {
  //       category = 'legal';
  //     }
  //     groupedRisks[category].count += info.count;
  //     groupedRisks[category].items.push({
  //       type: type,
  //       count: info.count,
  //       confidence: info.confidence || 80,
  //       files: info.files || []
  //     });
  //     if (info.confidence) {
  //       groupedRisks[category].confidence = 
  //         (groupedRisks[category].confidence * (groupedRisks[category].items.length - 1) + info.confidence) / 
  //         groupedRisks[category].items.length;
  //     }
  //   });
  //
  //   return groupedRisks;
  // };

  const renderAgeSection = (ageGroup, title) => {
    // Filter files by age group
    const files = stats.files?.filter(file => file.ageGroup === ageGroup) || [];
    
    // Group files by type
    const types = {};
    files.forEach(file => {
      const fileType = file.fileType || 'others';
      if (!types[fileType]) {
        types[fileType] = { count: 0, percentage: 0, files: [] };
      }
      types[fileType].count++;
      types[fileType].files.push(file);
    });
    
    // Calculate percentages for file types
    const totalFiles = files.length;
    Object.values(types).forEach(typeData => {
      typeData.percentage = totalFiles > 0 ? (typeData.count / totalFiles * 100) : 0;
    });
    
    // Group files by sensitivity category
    const risks = {};
    files.filter(file => file.sensitiveCategories?.length > 0).forEach(file => {
      file.sensitiveCategories.forEach(category => {
        if (!risks[category]) {
          risks[category] = { count: 0, percentage: 0, files: [] };
        }
        risks[category].count++;
        risks[category].files.push({ file });
      });
    });
    
    // Calculate percentages for risks
    const totalSensitiveFiles = files.filter(file => file.sensitiveCategories?.length > 0).length;
    Object.values(risks).forEach(riskData => {
      riskData.percentage = totalSensitiveFiles > 0 ? (riskData.count / totalSensitiveFiles * 100) : 0;
    });
    
    if (!selectedDirectory) {
      return (
        <div className="age-section">
          <div className="section-content">
            <div className="info-message">
              Please select a directory to analyze.
            </div>
          </div>
        </div>
      );
    }

    if (!files.length || (!Object.keys(types).length && !Object.keys(risks).length)) {
      return (
        <div className="age-section">
          <div className="section-content">
            <div className="info-message">
              Please run analysis first by using the analyze command in chat.
            </div>
          </div>
        </div>
      );
    }

    // Process risks to deduplicate files across categories
    const processedRisks = {};
    if (risks && Object.keys(risks).length > 0) {
      // First, collect all unique files per category
      const categoryFiles = {};
      Object.entries(risks).forEach(([category, riskData]) => {
        if (riskData && riskData.files && Array.isArray(riskData.files)) {
          const uniqueFiles = new Set();
          riskData.files.forEach(finding => {
            if (finding.file && finding.file.id) {
              uniqueFiles.add(finding.file.id);
            }
          });
          categoryFiles[category] = uniqueFiles.size;
        }
      });

      // Calculate percentages based on total unique files across all categories
      const totalUniqueFiles = new Set();
      Object.values(risks).forEach(riskData => {
        if (riskData && riskData.files && Array.isArray(riskData.files)) {
          riskData.files.forEach(finding => {
            if (finding.file && finding.file.id) {
              totalUniqueFiles.add(finding.file.id);
            }
          });
        }
      });
      const totalFiles = totalUniqueFiles.size;

      // Create processed risks with deduplicated counts
      Object.entries(risks).forEach(([category, riskData]) => {
        if (riskData && riskData.files && Array.isArray(riskData.files)) {
          const uniqueCount = categoryFiles[category] || 0;
          const percentage = totalFiles > 0 ? (uniqueCount / totalFiles * 100) : 0;
          
          processedRisks[category] = {
            count: uniqueCount,
            percentage: percentage,
            files: riskData.files // Keep original files for detailed view
          };
        }
      });
    }
    
    return (
      <div className="age-section">
        <div className="section-header">
          <h3>{title}</h3>
        </div>
        <div className="section-content file-types-card">
          <FileTypeChart files={files} title="File Categories" />
        </div>
        <div className="section-content">
          <RiskCategoryChart files={files} title="Risk Categories" />
        </div>
      </div>
    );
  };

  // TODO: Reserved for future use - RiskCategory component
  // const RiskCategory = ({ category, findings }) => {
  //   const totalFindings = findings.reduce((sum, f) => sum + f.count, 0);
  //   const percentage = Math.min(totalFindings * 10, 100);
  //   const riskColors = {
  //     pii: getRiskCategoryColor('pii'),
  //     financial: getRiskCategoryColor('financial'),
  //     legal: getRiskCategoryColor('legal'),
  //     confidential: getRiskCategoryColor('confidential')
  //   };
  //   return (
  //     <div className="type-bar">
  //       <span className="type-label">
  //         {category.charAt(0).toUpperCase() + category.slice(1)}
  //       </span>
  //       <div className="bar-container">
  //         <div 
  //           className="bar" 
  //           style={{ 
  //             width: `${percentage}%`,
  //             backgroundColor: riskColors[category]
  //           }}
  //         ></div>
  //       </div>
  //       <div className="type-stats">
  //         <span className="type-count">{totalFindings} files</span>
  //         <span className="type-percentage">{percentage.toFixed(1)}%</span>
  //       </div>
  //     </div>
  //   );
  // };

  // TODO: Reserved for future use - RiskCategories component

  const renderTabContent = () => {
    switch (activeTab) {
      case 'moreThanThreeYears':
        return renderAgeSection('moreThanThreeYears', 'Files > 3 years old');
      case 'oneToThreeYears':
        return renderAgeSection('oneToThreeYears', 'Files 1-3 years old');
      case 'lessThanOneYear':
        return renderAgeSection('lessThanOneYear', 'Files < 1 year old');
      //case 'type':
      //  return renderFileTypeContent();
      //case 'owner':
      //  return <div className="tab-content">Ownership analysis coming soon</div>;
      //case 'usage':
      //  return <div className="tab-content">Usage analysis coming soon</div>;
      //case 'risk':
      //  return renderRiskContent();
      default:
        return null;
    }
  };

  // Defensive rendering for missing context
  if (!stats || !('docCount' in stats)) {
    return (
      <div className="sensitive-content-container">
        <div className="error-message">
          <p>Missing dashboard context. Please return to the dashboard and run analysis again.</p>
        </div>
      </div>
    );
  }

  // Show loading state while checking auth
  if (loading || !authChecked) {
    return (
      <div className="app-container">
        <div style={{ padding: '20px', textAlign: 'center' }}>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/sensitive-content" element={<SensitiveContent />} />
      <Route path="/sensitive-content/:ageGroup/:category" element={<RiskCategoryInsightsDashboard />} />
      <Route path="/file-category/:ageGroup/:fileType" element={<FileInsightsDashboard />} />
      <Route path="/review-sensitive-files" element={<ReviewSensitiveFiles />} />
      <Route path="/department/:departmentSlug" element={<DepartmentDashboard />} />
      <Route path="/audit-trail" element={<AuditTrailDashboard />} />
      <Route
        path="/"
        element={
          <div className="app-container">
            <header className="app-header">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                <div>
                  <h1>Clario</h1>
                  <h2>Smart Structured Secure</h2>
                </div>
                {isAuthenticated && (
                  <button
                    onClick={handleLogout}
                    className="logout-button"
                    title="Sign out"
                  >
                    Sign Out
                  </button>
                )}
              </div>
            </header>
            <div className="app-content">
              <div className="dashboard-section">
                <div className="document-overview">
                  <h2>Scanning{selectedDirectory ? `: ${selectedDirectory.name || selectedDirectory.id}` : ''}</h2>
                  <div className="stats-grid">
                    <div className="stat-card" title="Total documents in this drive">
                      <div className="stat-number">
                        {stats?.docCount != null ? stats.docCount.toLocaleString() : 0}
                        {stats.docCount > 0 && <span className="trend-up">↑</span>}
                      </div>
                      <div className="stat-label">Files scanned</div>
                    </div>
                    <div 
                      className="stat-card clickable" 
                      title="Documents that may contain sensitive information"
                      onClick={handleSensitiveDocumentsClick}
                      style={{ cursor: 'pointer' }}
                    >
                      <div className="stat-number">
                        {stats?.sensitiveDocuments != null ? stats.sensitiveDocuments.toLocaleString() : 0}
                        {stats.sensitiveDocuments > 0 && <span className="trend-warning">!</span>}
                      </div>
                      <div className="stat-label">Sensitive documents</div>
                    </div>
                    <div className="stat-card" title="Documents with similar content or identical names">
                      <div className="stat-number">
                        {stats?.duplicateDocuments != null ? stats.duplicateDocuments.toLocaleString() : 0}
                        {stats.duplicateDocuments > 0 && <span className="trend-up">↑</span>}
                      </div>
                      <div className="stat-label">Duplicate documents</div>
                    </div>
                    
                  </div>

                  <div className="age-distribution">
                    <div className="analysis-tabs">
                      <button 
                        className={`tab-button ${activeTab === 'moreThanThreeYears' ? 'active' : ''}`}
                        onClick={() => setActiveTab('moreThanThreeYears')}
                      >
                        &gt; 3 years
                      </button>
                      <button 
                        className={`tab-button ${activeTab === 'oneToThreeYears' ? 'active' : ''}`}
                        onClick={() => setActiveTab('oneToThreeYears')}
                      >
                        1-3 years
                      </button>
                      <button 
                        className={`tab-button ${activeTab === 'lessThanOneYear' ? 'active' : ''}`}
                        onClick={() => setActiveTab('lessThanOneYear')}
                      >
                        &lt; 1 year
                      </button>
                    </div>
                    {renderTabContent()}
                  </div>
                </div>

                <div className="bottom-panels">
                  <div className="categories">
                    <h3>Departments</h3>
                    <div className="category-list">
                      {Object.entries(stats.departmentDistribution)
                        .filter(([_, count]) => count > 0)
                        .sort((a, b) => b[1] - a[1]) // Sort by count descending
                        .map(([department, count]) => (
                          <div key={department} className="category-item">
                            <div className="category-info">
                              <span>{department}</span>
                              <span>{count} files</span>
                            </div>
                            <a 
                              href={`/department/${department.toLowerCase().replace(/&/g, '-and-').replace(/\s+/g, '-').replace(/-+/g, '-')}`}
                              className="review-link"
                              onClick={(e) => {
                                e.preventDefault();
                                navigate(`/department/${department.toLowerCase().replace(/&/g, '-and-').replace(/\s+/g, '-').replace(/-+/g, '-')}`, {
                                  state: {
                                    selectedDirectory,
                                    stats,
                                    activeTab
                                  }
                                });
                              }}
                            >
                              Review →
                            </a>
                          </div>
                        ))}
                    </div>
                  </div>

                  <div className="active-rules">
                    <h3>Active rules</h3>
                    <div className="rules-list">
                      <div className="rule-item">
                        <div className="rule-text">Find stale HR docs 'do *ay'</div>
                        <div className="rule-frequency">Daily →</div>
                      </div>
                      <div className="rule-item">
                        <div className="rule-text">Archive finance documents with Unused in 2 years</div>
                        <div className="rule-frequency">Weekly →</div>
                      </div>
                      <div className="rule-item">
                        <div className="rule-text">Flag sensitive files containing payment* ternatics</div>
                        <div className="rule-frequency">Monthly →</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="cleo-section">
                <Cleo 
                  onCommand={handleCleoCommand}
                  onStatsUpdate={handleStatsUpdate}
                />
              </div>
            </div>
          </div>
        }
      />
    </Routes>
  );
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/sensitive-content" element={<SensitiveContent />} />
        <Route path="/sensitive-content/:ageGroup/:category" element={<RiskCategoryInsightsDashboard />} />
        <Route path="/file-category/:ageGroup/:fileType" element={<FileInsightsDashboard />} />
        <Route path="/review-sensitive-files" element={<ReviewSensitiveFiles />} />
        <Route path="/department/:departmentSlug" element={<DepartmentDashboard />} />
        <Route path="/audit-trail" element={<AuditTrailDashboard />} />
        <Route
          path="/"
          element={<AppContent />}
        />
      </Routes>
    </Router>
  );
}

export default App; 