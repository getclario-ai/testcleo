# Debug Checklist: Netlify Frontend → Render Backend

## Current Situation
✅ **Backend scans work** (via Slack or previously authenticated session)
❌ **Frontend on Netlify can't authenticate** with Google Drive

## Issues to Check

### 1. Render Backend Environment Variables

**Go to Render Dashboard → Your Web Service → Environment**

Check/Set:
- `BACKEND_CORS_ORIGINS` = `["https://testcleo.netlify.app"]` (JSON array as string)
  OR set as: `https://testcleo.netlify.app` (comma-separated string)
  
- `GOOGLE_REDIRECT_URI` = `https://testcleo-backend.onrender.com/api/v1/auth/google/callback`
  ⚠️ **CRITICAL:** Must match Google Cloud Console redirect URI!

- `FRONTEND_URL` = `https://testcleo.netlify.app`

### 2. Google Cloud Console OAuth Settings

**Go to: Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client**

**Authorized JavaScript origins:**
- `https://testcleo-backend.onrender.com`
- `https://testcleo.netlify.app` (if needed)

**Authorized redirect URIs:**
- `https://testcleo-backend.onrender.com/api/v1/auth/google/callback`
- ⚠️ **Must match exactly** what's in Render `GOOGLE_REDIRECT_URI`

### 3. Netlify Environment Variables

**Go to: Netlify Dashboard → Site Settings → Environment Variables**

Check/Set:
- `REACT_APP_API_BASE_URL` = `https://testcleo-backend.onrender.com`
  ⚠️ **Must NOT have trailing slash!**

### 4. Browser Console Debugging

**On Netlify site (`testcleo.netlify.app`):**
1. Open DevTools (F12)
2. Go to Console tab
3. Look for:
   - "Frontend API Base URL: ..." - Should show Render URL
   - CORS errors
   - Failed fetch errors
   - Network errors

**Go to Network tab:**
1. Click "Connect Google Drive"
2. Look for:
   - Request to `/api/v1/auth/google/login`
   - Check if it goes to Render URL
   - Check response status
   - Check CORS headers

### 5. Render Backend Logs

**Go to: Render Dashboard → Your Web Service → Logs**

Look for:
- CORS errors
- OAuth callback errors
- Request logs when clicking "Connect Google Drive"

## Quick Test Steps

1. **Test if frontend can reach backend:**
   - Open `https://testcleo.netlify.app` in browser
   - Open DevTools → Console
   - Type: `fetch('https://testcleo-backend.onrender.com/api/v1/auth/google/status')`
   - Check for CORS errors

2. **Test Google OAuth redirect:**
   - Click "Connect Google Drive" on Netlify site
   - Check if redirect URL in browser includes Render backend URL
   - After Google auth, check redirect back - should go to Render, then Netlify

3. **Test CORS:**
   - Check Network tab in DevTools
   - Look at OPTIONS preflight request
   - Check `Access-Control-Allow-Origin` header - should include `https://testcleo.netlify.app`

## Common Issues

### Issue 1: CORS Error
**Symptom:** "Failed to fetch" or CORS error in console
**Fix:** 
- Set `BACKEND_CORS_ORIGINS` in Render to include `https://testcleo.netlify.app`
- Redeploy Render service

### Issue 2: OAuth Redirect URI Mismatch
**Symptom:** Google shows "redirect_uri_mismatch" error
**Fix:**
- Update Google Cloud Console redirect URI to Render URL
- Update Render `GOOGLE_REDIRECT_URI` env var
- Match exactly!

### Issue 3: Frontend points to wrong backend
**Symptom:** Requests going to localhost or wrong URL
**Fix:**
- Check Netlify `REACT_APP_API_BASE_URL` env var
- Redeploy Netlify site (rebuild with correct env var)

### Issue 4: Authentication works but no data
**Symptom:** Can authenticate but dashboard shows 0 files
**Fix:**
- This might be multi-user issue - each browser session needs its own auth
- Check if `token.pickle` is shared or per-user
