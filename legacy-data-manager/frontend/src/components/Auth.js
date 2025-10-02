import React, { useEffect } from 'react';
import axios from 'axios';
import config from '../config';
import './Auth.css';

const Auth = ({ onAuthSuccess }) => {
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await axios.get(`${config.apiBaseUrl}/api/v1/auth/google/status`);
        if (response.data.authenticated) {
          onAuthSuccess();
        }
      } catch (error) {
        console.error('Error checking auth status:', error);
      }
    };
    checkAuth();
  }, [onAuthSuccess]);

  const handleAuth = async () => {
    try {
      const response = await axios.get(`${config.apiBaseUrl}/api/v1/auth/google/login`);
      window.location.href = response.data.auth_url;
    } catch (error) {
      console.error('Error getting auth URL:', error);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-content">
        <h1>Hi, I am Cleo</h1>
        <p>How can I assist you with your legacy data today?</p>
        <button onClick={handleAuth} className="auth-button">
          Connect with Google Drive
        </button>
        <p className="auth-note">
          Cleo needs access to your Google Drive to help you manage and analyze your files.
        </p>
      </div>
    </div>
  );
};

export default Auth;

export const checkAuthStatus = async () => {
    try {
        const response = await axios.get(`${config.apiBaseUrl}/api/v1/auth/google/status`);
        return response.data;
    } catch (error) {
        console.error('Error checking auth status:', error);
        return { isAuthenticated: false };
    }
};

export const getAuthUrl = async () => {
    try {
        const response = await axios.get(`${config.apiBaseUrl}/api/v1/auth/google/login`);
        return response.data.auth_url;
    } catch (error) {
        console.error('Error getting auth URL:', error);
        throw error;
    }
}; 