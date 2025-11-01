const config = {
  apiBaseUrl: process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000',
  // Default fetch options for all API requests
  fetchOptions: {
    credentials: 'include', // Include cookies (for session)
    headers: {
      'Accept': 'application/json',
    }
  }
};

// Log the config in development to help debug
if (process.env.NODE_ENV === 'development') {
  console.log('Frontend API Base URL:', config.apiBaseUrl);
  console.log('REACT_APP_API_BASE_URL env var:', process.env.REACT_APP_API_BASE_URL);
}

export default config; 