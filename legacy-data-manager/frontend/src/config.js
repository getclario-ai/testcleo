const config = {
  apiBaseUrl: process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000'
};

// Log the config in development to help debug
if (process.env.NODE_ENV === 'development') {
  console.log('Frontend API Base URL:', config.apiBaseUrl);
  console.log('REACT_APP_API_BASE_URL env var:', process.env.REACT_APP_API_BASE_URL);
}

export default config; 