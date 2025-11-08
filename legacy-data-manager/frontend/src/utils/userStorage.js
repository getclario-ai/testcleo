/**
 * User-specific localStorage utility
 * Prefixes all keys with the current user's email to prevent cross-user data leakage
 */

let currentUserEmail = null;

/**
 * Initialize user email from auth status
 * Should be called on app mount after auth check
 */
export async function initUserStorage(apiBaseUrl) {
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/auth/google/status`, {
      method: 'GET',
      credentials: 'include',
      headers: {
        'Accept': 'application/json',
      }
    });

    if (response.ok) {
      const data = await response.json();
      if (data.isAuthenticated && data.email) {
        const newEmail = data.email;
        
        // If user changed, clear old localStorage
        if (currentUserEmail && currentUserEmail !== newEmail) {
          clearUserStorage(currentUserEmail);
        }
        
        currentUserEmail = newEmail;
        return newEmail;
      }
    }
  } catch (error) {
    console.error('Error initializing user storage:', error);
  }
  
  // If not authenticated, clear any existing user storage
  if (currentUserEmail) {
    clearUserStorage(currentUserEmail);
    currentUserEmail = null;
  }
  
  return null;
}

/**
 * Set current user email (for testing or manual override)
 */
export function setUserEmail(email) {
  if (currentUserEmail && currentUserEmail !== email) {
    clearUserStorage(currentUserEmail);
  }
  currentUserEmail = email;
}

/**
 * Get current user email
 */
export function getUserEmail() {
  return currentUserEmail;
}

/**
 * Get user-specific localStorage key
 */
function getUserKey(key) {
  if (!currentUserEmail) {
    // Fallback to non-prefixed key if no user email (shouldn't happen in production)
    console.warn('getUserKey called without user email, using non-prefixed key:', key);
    return key;
  }
  // Use email hash to avoid special characters in localStorage keys
  const emailHash = currentUserEmail.replace(/[@.]/g, '_');
  return `user_${emailHash}_${key}`;
}

/**
 * Clear all localStorage entries for a specific user
 */
function clearUserStorage(email) {
  if (!email) return;
  
  const emailHash = email.replace(/[@.]/g, '_');
  const prefix = `user_${emailHash}_`;
  
  const keysToRemove = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && key.startsWith(prefix)) {
      keysToRemove.push(key);
    }
  }
  
  keysToRemove.forEach(key => localStorage.removeItem(key));
  console.log(`Cleared ${keysToRemove.length} localStorage entries for user: ${email}`);
}

/**
 * User-specific localStorage wrapper
 */
export const userStorage = {
  getItem(key) {
    const userKey = getUserKey(key);
    return localStorage.getItem(userKey);
  },
  
  setItem(key, value) {
    const userKey = getUserKey(key);
    localStorage.setItem(userKey, value);
  },
  
  removeItem(key) {
    const userKey = getUserKey(key);
    localStorage.removeItem(userKey);
  },
  
  clear() {
    if (currentUserEmail) {
      clearUserStorage(currentUserEmail);
    }
  }
};

