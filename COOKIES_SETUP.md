# YouTube Cookies Setup for Render

This guide explains how to add YouTube authentication cookies to your Render deployment.

## Why You Need Cookies

YouTube has restrictions on:
- Age-restricted content
- Premium content
- Viewing certain videos without authentication

Adding your authentication cookies allows yt-dlp to bypass these restrictions by using your authenticated session.

## Setup Instructions

### Step 1: Prepare Your Cookies

You should have a Netscape-format cookies file (typically from browser automation or extracted from a browser).

### Step 2: Add to Render Environment

1. Go to your Render Dashboard
2. Navigate to your service (vdrop)
3. Click **Settings** → **Environment**
4. Click **Add Environment Variable**
5. Set the following:
   - **Key**: `YT_DLP_COOKIES`
   - **Value**: Paste your entire cookies file content (multiline is fine)
6. Click **Save**

### Step 3: Redeploy

1. In Render Dashboard, go to **Deployments**
2. Click **Clear build cache & deploy** to force a new deployment
3. This will create the cookies.txt file from the environment variable during startup

## How It Works

- The `entrypoint.sh` script reads the `YT_DLP_COOKIES` environment variable at startup
- It writes the cookies to `/app/cookies.txt` inside the container
- Both the `/analyze` and `/download` endpoints use the cookies when available
- Cookies are kept in memory only (not persisted to Render storage)

## Important Security Notes

- **Never commit cookies to Git** - they contain authentication tokens
- Render environment variables are encrypted and secure
- Anyone with access to your Render dashboard can see the cookies
- Keep your cookies file private and secure
- YouTube cookies expire after ~2 years; you'll need to refresh them periodically

## Refreshing Cookies

When your cookies expire:
1. Extract fresh cookies from your browser
2. Update the `YT_DLP_COOKIES` environment variable in Render
3. Redeploy the service

## Local Testing

To test locally with cookies:

```bash
# Create a local cookies.txt file
# Set the environment variable
export YT_DLP_COOKIES=$(cat cookies.txt)

# Run the application
docker build -t vdrop .
docker run -e YT_DLP_COOKIES="$YT_DLP_COOKIES" -p 8080:8080 vdrop
```

Or use docker-compose:

```bash
docker-compose up
```

Create a `.env` file:
```
YT_DLP_COOKIES=<your-cookies-content>
```
