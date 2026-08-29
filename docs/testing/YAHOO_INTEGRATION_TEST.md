# Yahoo Fantasy Integration Testing Guide

## Known, Currently-Blocking Issue — Read This First

**Yahoo's own OAuth server currently rejects this app's real, correctly-constructed authorization request.** This was confirmed independently, twice, while writing this doc:

1. **Direct `curl` to the real constructed auth URL** (from a live `GET /api/v1/leagues/yahoo/auth-url` response):
   ```
   GET https://api.login.yahoo.com/oauth2/request_auth?client_id=<real client_id>&redirect_uri=http://localhost:3001/yahoo/callback&response_type=code&scope=fspt-r
   → HTTP/2 302
   → location: https://api.login.yahoo.com/oauth2/error?client_id=<same client_id>&error=invalid_request&error_description=invalid+redirect+uri
   ```
2. Direct browser navigation to the same URL dead-ends at Yahoo's own OAuth error page the same way.

This is a **Yahoo Developer Console configuration mismatch**, not a bug in this app's code. The redirect URI this app sends — `http://localhost:3001/yahoo/callback` — is real and correct (it matches `frontend/vite.config.ts`'s actual dev port, 3001, and the real route registered in `frontend/src/App.tsx`). Yahoo's console evidently has a different (or no) redirect URI registered for this `YAHOO_CLIENT_ID`. Only whoever owns that Yahoo Developer app can fix this — see the checklist below.

**Practical effect for testing**: you cannot currently complete a full Yahoo OAuth round-trip in this environment. Everything up to and including the popup opening and hitting Yahoo's real login/consent flow is real and was traced end-to-end; it dead-ends at Yahoo's side with the `invalid_request` error above, before any credentials are even entered. Do not write test steps implying a full Yahoo connect currently succeeds here — it does not, and this is an external configuration problem, not something further code changes in this repo can fix on their own.

### Checklist for whoever owns the Yahoo Developer app (fixing this)
1. Log into [https://developer.yahoo.com/apps/](https://developer.yahoo.com/apps/) with the account that owns the `YAHOO_CLIENT_ID` configured in `backend/.env`.
2. Open that app's settings and check its registered **Redirect URI(s)**.
3. Confirm it contains **exactly** `http://localhost:3001/yahoo/callback` — protocol, host, port, and path all have to match byte-for-byte; Yahoo does exact matching, not prefix or wildcard matching. If the frontend's dev port in `frontend/vite.config.ts` ever changes from 3001, this must be updated in Yahoo's console too, or the same error will return.
4. Confirm the app requests **Fantasy Sports (Read)** API permission, matching this app's requested `scope=fspt-r`.
5. Confirm `YAHOO_CLIENT_ID`/`YAHOO_CLIENT_SECRET` in `backend/.env` actually belong to *that* app — a stale/regenerated secret pointed at a differently-configured app produces the same symptom.
6. After changing anything in Yahoo's console, re-test by pasting a fresh `auth_url` (from `GET /api/v1/leagues/yahoo/auth-url`) directly into a browser. Success looks like Yahoo's real login/consent screen; failure looks like an immediate redirect to `https://api.login.yahoo.com/oauth2/error?...`.
7. Also double check for a production redirect URI if/when this app is deployed somewhere other than `localhost:3001` — that will need its own registered entry in the same console.

## Overview
This guide covers the real, current Yahoo Fantasy Sports OAuth connect flow: a popup-based OAuth2 authorization-code flow, a `postMessage` handshake back to the opener window, and per-user token persistence (no shared/global token state — every user's Yahoo access/refresh token lives on their own `UserLeague` rows).

## Prerequisites
1. Backend running on `http://localhost:8000`, frontend on `http://localhost:3001`.
2. `YAHOO_CLIENT_ID` / `YAHOO_CLIENT_SECRET` set in `backend/.env`. Verify with:
   ```bash
   curl http://localhost:8000/api/v1/leagues/yahoo/test-credentials
   ```
   **Verified live**: this returns `{"credentials_configured": true, "client_id_set": true, "client_secret_set": true, "client_id_preview": "..."}` in the current environment — the credentials being *configured* is not the problem; the problem is what's registered against them in Yahoo's own console (see above).
3. A registered/logged-in app user (`POST /api/v1/auth/register`, then `/auth/login`) — the connect endpoint requires a bearer token.

## The Real Connect Flow (code-verified up to the blocker above)

1. **User clicks "Yahoo" on `/leagues`.** `LeaguesPage.tsx`'s `connectYahooLeague()` calls `GET /api/v1/leagues/yahoo/auth-url`, which returns:
   ```json
   {
     "auth_url": "https://api.login.yahoo.com/oauth2/request_auth?client_id=...&redirect_uri=http://localhost:3001/yahoo/callback&response_type=code&scope=fspt-r",
     "redirect_uri": "http://localhost:3001/yahoo/callback"
   }
   ```
2. **A popup window opens** to that `auth_url` (`window.open(authUrl, 'yahooAuth', 'width=600,height=700')`). If the browser blocks the popup, the UI now shows a clear "browser blocked the Yahoo sign-in popup" error instead of hanging (a real, recent fix).
3. **Normal path (once Yahoo's console is fixed)**: user logs into Yahoo, grants Fantasy Sports Read access, Yahoo redirects the popup to `http://localhost:3001/yahoo/callback?code=...`.
4. **`YahooCallbackPage.tsx`** reads the `code` query param and does `window.opener.postMessage({type: 'YAHOO_AUTH_SUCCESS', code: authorizationCode}, window.location.origin)`, then closes itself. On an `error` query param instead, it posts `YAHOO_AUTH_ERROR` and closes.
5. **Back in the opener window**, `LeaguesPage.tsx`'s `message` listener catches `YAHOO_AUTH_SUCCESS` and calls `POST /api/v1/leagues/yahoo/connect` with the authorization code.
6. **Backend** (`leagues.py::connect_yahoo_league`) exchanges the code for a real access/refresh token pair (`yahoo_service.authenticate`), fetches the user's real Yahoo leagues (`yahoo_service.get_user_leagues`), and persists one `UserLeague` row per league — scoped to the calling user, carrying `yahoo_access_token`, `yahoo_refresh_token`, and `yahoo_token_expires_at` (tokens live ~1 hour; there's no background refresh, only an explicit "reconnect" path once expired).
7. **Popup-stuck fix**: if the popup is closed by the user (or dead-ends on a Yahoo error page that never reaches `/yahoo/callback`, exactly the failure mode above), a polling check (`popup.closed`) resets the "Connecting..." button state with an error message, instead of leaving the Yahoo/ESPN buttons permanently disabled the way it used to before this was fixed.

### What you can currently verify, end-to-end, without a working Yahoo app registration
- `GET /api/v1/leagues/yahoo/auth-url` returns a real, correctly-shaped URL (verified live).
- `GET /api/v1/leagues/yahoo/test-credentials` confirms client credentials are configured (verified live).
- The popup opens and reaches Yahoo's real domain — confirmed reaching `api.login.yahoo.com`, which then 302s to its own error page for the reason above (verified live via direct `curl`).
- The "popup blocked" and "popup closed before completing" UI states work (code-verified in `LeaguesPage.tsx`).

### What you cannot currently verify, because of the blocker above
- Actually signing into Yahoo and granting consent.
- The `postMessage` handshake firing with a real authorization code.
- `POST /api/v1/leagues/yahoo/connect` succeeding with a real code (its logic was code-reviewed, not live-exercised, since no real code can currently be obtained).
- Any Yahoo-backed league appearing in `/leagues` or being used to start a Live Draft session (see `LIVE_DRAFT_TEST.md`).

## API Endpoints

### Get Yahoo Auth URL
```bash
curl http://localhost:8000/api/v1/leagues/yahoo/auth-url
```
```json
{
  "auth_url": "https://api.login.yahoo.com/oauth2/request_auth?client_id=...&redirect_uri=http://localhost:3001/yahoo/callback&response_type=code&scope=fspt-r",
  "redirect_uri": "http://localhost:3001/yahoo/callback"
}
```

### Test Yahoo Credentials Configuration
```bash
curl http://localhost:8000/api/v1/leagues/yahoo/test-credentials
```

### Connect Yahoo League (requires a real authorization code, and a bearer token)
```bash
curl -X POST http://localhost:8000/api/v1/leagues/yahoo/connect \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"authorization_code": "YAHOO_AUTH_CODE", "redirect_uri": "http://localhost:3001/yahoo/callback"}'
```
Note: `authorization_code` is required; `redirect_uri` is optional and defaults to `http://localhost:3001/yahoo/callback` if omitted — it must match whatever redirect URI was used to obtain the code, per OAuth2 rules.

### Get User's Connected Leagues (any platform, requires bearer token)
```bash
curl http://localhost:8000/api/v1/leagues/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Troubleshooting

1. **Yahoo popup redirects straight to an error page / never reaches `/yahoo/callback`** — this is the known blocker above. Check the Yahoo Developer Console redirect-URI configuration.
2. **"Yahoo API credentials not configured"** (400 from `auth-url` or `connect`) — set `YAHOO_CLIENT_ID`/`YAHOO_CLIENT_SECRET` in `backend/.env` and restart the backend.
3. **Popup blocked by browser** — allow popups for `localhost`, or use a non-incognito window with popups allowed.
4. **"Your Yahoo connection has expired"** on later calls (draft sessions, league analysis, matchups) — Yahoo access tokens last ~1 hour and this app does not silently refresh them; reconnect from `/leagues`.
5. **CORS errors** — confirm both servers are running on their expected ports (backend 8000, frontend 3001) and CORS allows the frontend origin.

## Expected Flow (once the Yahoo console issue is fixed)
1. User clicks "Yahoo" on `/leagues`.
2. Frontend calls `GET /api/v1/leagues/yahoo/auth-url`.
3. Frontend opens a popup to the real Yahoo OAuth URL.
4. User authenticates and grants Fantasy Sports Read access on Yahoo's real site.
5. Yahoo redirects the popup to `/yahoo/callback` with a real authorization code.
6. `YahooCallbackPage` posts the code back to the opener and closes itself.
7. Opener calls `POST /api/v1/leagues/yahoo/connect` with the code.
8. Backend exchanges the code for tokens, fetches and persists the user's real Yahoo leagues.
9. `/leagues` refreshes and shows the newly-connected Yahoo league(s).
10. Those leagues become usable for Live Draft sessions and league analysis (see `LIVE_DRAFT_TEST.md`), until their token expires (~1 hour) and a reconnect is needed.

## File Structure
- Frontend routes: `frontend/src/App.tsx` (`/yahoo/callback`, `/leagues`)
- Leagues page: `frontend/src/pages/LeaguesPage.tsx`
- OAuth callback: `frontend/src/pages/YahooCallbackPage.tsx`
- API services: `frontend/src/services/api.ts` (`leagues.getYahooAuthUrl`, `leagues.connectYahoo`)
- Backend endpoints: `backend/app/api/v1/endpoints/leagues.py` (`/yahoo/auth-url`, `/yahoo/test-credentials`, `/yahoo/connect`)
- Yahoo service: `backend/app/services/yahoo_service.py`
- Live-draft consumer of a connected Yahoo league: `backend/app/services/draft_assistant_service.py` (`_get_yahoo_draft_state`)
