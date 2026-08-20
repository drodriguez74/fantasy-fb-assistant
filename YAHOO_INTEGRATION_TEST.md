# Yahoo Fantasy Integration Testing Guide

## Overview
This guide explains how to test the Yahoo Fantasy Sports integration in the Fantasy Football Assistant application.

## Prerequisites
1. Backend is running on `http://localhost:8000`
2. Frontend is running on `http://localhost:3001`
3. Yahoo API credentials are configured in `backend/.env`
4. User account is registered and logged in

## Testing Steps

### 1. Navigate to Leagues Page
- Go to `http://localhost:3001`
- Log in with your account
- Click on "Leagues" in the navigation bar
- You should see the "My Fantasy Leagues" page

### 2. Test Yahoo OAuth Flow
- Click the "Connect Yahoo League" button
- A popup window should open with Yahoo's OAuth login page
- The URL should look like: `https://api.login.yahoo.com/oauth2/request_auth?client_id=...&redirect_uri=http://localhost:3001/yahoo/callback&response_type=code&scope=fspt-r`

### 3. Complete OAuth Authentication
- Sign in with your Yahoo account in the popup
- Grant permissions for Fantasy Sports access
- You should be redirected to `http://localhost:3001/yahoo/callback`
- The callback page should show "Authentication Successful!" message
- The popup should close automatically

### 4. Verify League Import
- Back on the main leagues page, your Yahoo leagues should appear
- Each league card should show:
  - League name
  - Platform (Yahoo)
  - Season year
  - Team count
  - Scoring format
  - Commissioner badge (if applicable)

### 5. Test League Actions
- "View Analysis" button should be functional (may show placeholder content)
- "Standings" button should be functional (may show placeholder content)
- "✕" (disconnect) button should show confirmation dialog

## API Endpoints

### Get Yahoo Auth URL
```bash
curl -X GET http://localhost:8000/api/v1/leagues/yahoo/auth-url
```

Expected response:
```json
{
  "auth_url": "https://api.login.yahoo.com/oauth2/request_auth?...",
  "redirect_uri": "http://localhost:3001/yahoo/callback"
}
```

### Connect Yahoo League (requires authentication token)
```bash
curl -X POST http://localhost:8000/api/v1/leagues/yahoo/connect \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"authorization_code": "YAHOO_AUTH_CODE"}'
```

### Get User Leagues (requires authentication token)
```bash
curl -X GET http://localhost:8000/api/v1/leagues/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Troubleshooting

### Common Issues

1. **"Port 3001 is already in use"**
   - The frontend is already running. Access it at `http://localhost:3001`

2. **OAuth popup blocked by browser**
   - Allow popups for localhost in browser settings
   - Try using incognito/private mode

3. **CORS errors**
   - Ensure backend CORS is configured to allow frontend origin
   - Check that both servers are running on correct ports

4. **"Not authenticated" errors**
   - Ensure you're logged in before accessing protected routes
   - Check that JWT token is stored in localStorage

5. **Yahoo API errors**
   - Verify Yahoo API credentials in backend `.env` file
   - Check that redirect URI matches exactly: `http://localhost:3001/yahoo/callback`

## Expected Flow
1. User clicks "Connect Yahoo League"
2. Frontend calls `/api/v1/leagues/yahoo/auth-url`
3. Frontend opens Yahoo OAuth popup
4. User authenticates with Yahoo
5. Yahoo redirects to `/yahoo/callback` with authorization code
6. Frontend callback page sends message to parent window
7. Frontend calls `/api/v1/leagues/yahoo/connect` with auth code
8. Backend exchanges code for access token and imports leagues
9. Frontend refreshes league list and displays imported leagues

## File Structure
- Frontend routes: `frontend/src/App.tsx`
- Leagues page: `frontend/src/pages/LeaguesPage.tsx`  
- OAuth callback: `frontend/src/pages/YahooCallbackPage.tsx`
- API services: `frontend/src/services/api.ts`
- Backend endpoints: `backend/app/api/v1/endpoints/leagues.py`
- Yahoo service: `backend/app/services/yahoo_service.py`