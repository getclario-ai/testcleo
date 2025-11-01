# Render Environment Variables Configuration

## Required Environment Variables for Backend

Go to: **Render Dashboard → Your Web Service → Environment → Add Environment Variable**

### Critical Variables:

1. **`BACKEND_CORS_ORIGINS`**
   - **Value:** `https://testcleo.netlify.app`
   - **Format:** Can be comma-separated string OR JSON array as string
   - **Purpose:** Allows Netlify frontend to make requests to Render backend
   - **⚠️ CRITICAL:** Without this, you'll see CORS errors!

2. **`GOOGLE_REDIRECT_URI`**
   - **Value:** `https://testcleo-backend.onrender.com/api/v1/auth/google/callback`
   - **Purpose:** Where Google redirects after authentication
   - **⚠️ MUST MATCH:** Google Cloud Console OAuth redirect URI exactly!

3. **`FRONTEND_URL`**
   - **Value:** `https://testcleo.netlify.app`
   - **Purpose:** Where to redirect users after authentication

### Other Required Variables (should already be set):
- `DATABASE_URL` - Your database connection string
- `GOOGLE_CLIENT_ID` - Your Google OAuth client ID
- `GOOGLE_CLIENT_SECRET` - Your Google OAuth client secret
- `SLACK_BOT_TOKEN` - Your Slack bot token
- `SLACK_SIGNING_SECRET` - Your Slack signing secret

## After Setting Variables:

1. **Redeploy Render Service:**
   - Go to Render Dashboard → Your Web Service
   - Click "Manual Deploy" → "Deploy latest commit"
   - OR just save the env vars (will auto-redeploy)

2. **Verify CORS is Working:**
   - Go to Netlify site
   - Open DevTools → Network tab
   - Click "Connect Google Drive"
   - Check if request succeeds (no CORS error)

## Testing:

1. Set `BACKEND_CORS_ORIGINS` = `https://testcleo.netlify.app`
2. Redeploy Render
3. Test on Netlify - should see 401 instead of CORS error (401 means CORS works, but needs auth)
4. Then authenticate via Google Drive on Netlify site
