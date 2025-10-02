import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// Clear potentially corrupted localStorage data
// This helps avoid issues with changing key names and structure
console.log('Cleaning localStorage to ensure fresh state');
const keysToKeep = ['isAuthenticated']; // Don't clear authentication
Object.keys(localStorage).forEach(key => {
  if (!keysToKeep.includes(key)) {
    localStorage.removeItem(key);
  }
});

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
); 