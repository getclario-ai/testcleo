import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import '../App.css';
import AgeGroupSection from './AgeGroupSection';

function DepartmentDashboard() {
  const { departmentSlug } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  
  // Convert slug back to department name
  const getDepartmentName = (slug) => {
    const slugMap = {
      'sales-and-marketing': 'Sales & Marketing',
      'operations': 'Operations',
      'r-and-d': 'R&D',
      'others': 'Others'
    };
    return slugMap[slug] || 'Unknown Department';
  };

  const departmentName = getDepartmentName(departmentSlug);
  
  // Get data from navigation state or localStorage
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

  const [selectedDirectory, setSelectedDirectory] = useState(() => {
    return location.state?.selectedDirectory || JSON.parse(localStorage.getItem('fid_selectedDirectory')) || null;
  });

  const [activeTab, setActiveTab] = useState('moreThanThreeYears');

  // Filter files by department
  const departmentFiles = stats.files.filter(file => file.department === departmentName);
  
  // Calculate department-specific stats
  const departmentStats = {
    totalFiles: departmentFiles.length,
    sensitiveFiles: departmentFiles.filter(file => file.sensitiveCategories && file.sensitiveCategories.length > 0).length,
    riskDistribution: {
      high: departmentFiles.filter(file => file.riskLevelLabel === 'high').length,
      medium: departmentFiles.filter(file => file.riskLevelLabel === 'medium').length,
      low: departmentFiles.filter(file => file.riskLevelLabel === 'low').length
    }
  };

  const handleBackToMain = () => {
    navigate('/', { 
      state: { 
        selectedDirectory,
        stats,
        activeTab: 'moreThanThreeYears'
      }
    });
  };

  const renderAgeSection = (ageGroup, ageLabel) => {
    const ageFiles = departmentFiles.filter(file => file.ageGroup === ageGroup);
    return <AgeGroupSection files={ageFiles} ageLabel={ageLabel} />;
  };

  return (
    <div className="app-container">
      <div className="department-header">
        <div className="header-left">
          <button 
            className="back-button"
            onClick={handleBackToMain}
          >
            ←
          </button>
          <h1>{selectedDirectory?.name || 'Unknown Directory'}  {departmentName}</h1>
        </div>
      </div>

      <div className="dashboard-content">
        {/* Department Summary */}
        <div className="summary-section">
          <div className="summary-card">
            <h3>Department Summary</h3>
            <div className="summary-stats">
              <div className="stat-item">
                <span className="stat-value">{departmentStats.totalFiles}</span>
                <span className="stat-label">Total Files</span>
              </div>
              <div className="stat-item">
                <span className="stat-value">{departmentStats.sensitiveFiles}</span>
                <span className="stat-label">Sensitive Files</span>
              </div>
              <div className="stat-item">
                <span className="stat-value">{departmentStats.riskDistribution.high}</span>
                <span className="stat-label">High Risk</span>
              </div>
              <div className="stat-item">
                <span className="stat-value">{departmentStats.riskDistribution.medium}</span>
                <span className="stat-label">Medium Risk</span>
              </div>
              <div className="stat-item">
                <span className="stat-value">{departmentStats.riskDistribution.low}</span>
                <span className="stat-label">Low Risk</span>
              </div>
            </div>
          </div>
        </div>

        {/* Age Groups */}
        <div className="age-groups-section">
          <div className="age-tabs">
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
          
          <div className="tab-content">
            {activeTab === 'moreThanThreeYears' && renderAgeSection('moreThanThreeYears', 'Files > 3 years old')}
            {activeTab === 'oneToThreeYears' && renderAgeSection('oneToThreeYears', 'Files 1-3 years old')}
            {activeTab === 'lessThanOneYear' && renderAgeSection('lessThanOneYear', 'Files < 1 year old')}
          </div>
        </div>
      </div>
    </div>
  );
}

export default DepartmentDashboard;
