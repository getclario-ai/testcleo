import React from 'react';
import '../styles/Dashboard.css';

const Dashboard = ({ selectedDirectory, dashboardState, setDashboardState }) => {
  const renderView = () => {
    switch (dashboardState.currentView) {
      case 'welcome':
        return (
          <div className="welcome-message">
            <h2>Welcome to Cleo</h2>
            <p>Use the command interface to interact with your data.</p>
          </div>
        );
      case 'loading':
        return (
          <div className="loading-message">
            <div className="spinner"></div>
            <p>Processing your request...</p>
          </div>
        );
      case 'text':
        return (
          <div className="response-message">
            <div className="message-content">
              {typeof dashboardState.data === 'string' 
                ? dashboardState.data 
                : JSON.stringify(dashboardState.data, null, 2)}
            </div>
          </div>
        );
      case 'error':
        return (
          <div className="error-message">
            <div className="message-content">
              {dashboardState.error}
            </div>
          </div>
        );
      default:
        return (
          <div className="welcome-message">
            <h2>Welcome to Cleo</h2>
            <p>Use the command interface to interact with your data.</p>
          </div>
        );
    }
  };

  return (
    <div className="dashboard-container">
      <div className="dashboard-content">
        {renderView()}
      </div>
    </div>
  );
};

export default Dashboard; 