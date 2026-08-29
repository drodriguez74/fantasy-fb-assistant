# User Authentication System Guide

## Overview

The Fantasy Football Assistant has a JWT-based authentication system: `backend/app/api/v1/endpoints/auth.py` (routes), `backend/app/core/security.py` (token/hash primitives), `backend/app/services/user_service.py` (`UserService`, business logic), and `backend/app/api/deps.py` (`get_current_user` and friends — the dependency every protected route uses). This guide describes what that code actually does today, verified by reading it and by live-testing `/auth/register` and `/auth/login` against a running instance.

## Features

### Authentication & Security
- **JWT-based authentication** with access and refresh tokens (`python-jose`, HS256)
- **Password hashing** with bcrypt (`passlib`)
- **Account lockout** after 5 failed login attempts (15 minutes) — fixed this session from a real crash bug (see below)
- **Password reset** with secure, time-limited tokens
- **Email verification** tokens/endpoints exist and work, but new accounts are auto-verified at registration (see "Email Verification" below) — this is intentional demo-mode behavior, not a gap
- **Real, honestly-degrading email delivery**: `email_service.py` sends via real SMTP when configured, and logs the email instead of crashing when it isn't (see "Email Delivery" below)

### User Management
- **User registration** with password-strength/username validation
- **Profile management** with preferences (`PUT /api/v1/users/me`)
- **League connections** across platforms, including per-league scoring overrides
- **Draft session history**
- **Account deactivation** (soft-delete via `is_active`)

### Fantasy Integration
- **Multi-platform league management** (ESPN, Yahoo, Sleeper) — see `DRAFT_ASSISTANT_GUIDE.md`
- **Draft session tracking** with AI analysis
- **User preferences** for scoring format and teams

There is no `is_premium` field or premium-tier logic anywhere in the codebase (checked `User` model, `UserResponse` schema, and a full grep of `backend/app`). If earlier versions of this guide implied one, that was aspirational, not real — don't build against it.

## API Endpoints

All routes below are mounted under `/api/v1` (see `backend/app/api/v1/router.py`: `api_router.include_router(auth.router, prefix="/auth", ...)`).

### Authentication

#### Register User
```bash
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "username": "fantasyfan123",
  "password": "SecurePass123!",
  "full_name": "John Smith"
}
```

Password must be 8+ characters with at least one uppercase, one lowercase, and one digit (`UserCreate.password_strength` in `backend/app/schemas/user.py`). Username must be 3–20 alphanumeric/`-`/`_` characters.

**Response** (live-tested against a running instance — real shape, not illustrative):
```json
{
  "id": 57,
  "email": "user@example.com",
  "username": "fantasyfan123",
  "full_name": "John Smith",
  "is_active": true,
  "is_verified": true,
  "avatar_url": null,
  "bio": null,
  "timezone": "UTC",
  "preferred_scoring": "PPR",
  "favorite_teams": null,
  "notifications_enabled": true,
  "created_at": "2026-08-23T05:11:00.381273-04:00",
  "last_login": null
}
```

Note `"is_verified": true` on a brand-new account. `auth.py::register` builds the `User` row directly with `is_verified=True` and the comment "Skip verification for demo" — it does **not** call `UserService.create_user()` (which still defaults `is_verified=False` but is effectively dead code for this endpoint). In this app, registering an account does not currently gate anything behind email verification; the verify-email flow exists and functions (see below) but isn't required to log in or use the app.

#### Login
```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

The `email` field accepts either an email address or a username — `UserService.authenticate_user` tries `get_user_by_email` first, then falls back to `get_user_by_username` with the same value. The frontend relies on this: `frontend/src/services/api.ts`'s `auth.login()` takes a `username` field from its caller and posts it as `email`.

**Response** (live-tested):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 691200,
  "user": {
    "id": 57,
    "email": "user@example.com",
    "username": "fantasyfan123",
    "full_name": "John Smith",
    "is_active": true,
    "is_verified": true,
    "avatar_url": null,
    "bio": null,
    "timezone": "UTC",
    "preferred_scoring": "PPR",
    "favorite_teams": null,
    "notifications_enabled": true,
    "created_at": "2026-08-23T05:11:00.381273-04:00",
    "last_login": "2026-08-23T05:11:00.914534-04:00"
  }
}
```

`expires_in` is `691200` seconds — 8 **days**, not 8 hours (see "Token Lifetimes" below; this corrects a previous version of this doc).

Invalid credentials return a flat 401 in both the "wrong password" and "account locked" cases:
```json
{"detail": "Incorrect email/username or password"}
```
There is no separate "account locked" error message — confirmed live by tripping the lockout (5 wrong passwords) and then retrying with the *correct* password: it's still rejected with the exact same generic message, because `UserService.authenticate_user` returns `None` before ever checking the password once `locked_until` is in the future.

#### Refresh Token
```bash
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```
Returns a new access/refresh token pair in the same shape as `/login`. Note the frontend (`api.ts`, `useAuth.tsx`) does not currently call this endpoint anywhere — only `access_token` is persisted to `localStorage`, and a 401 just clears it and redirects to `/auth` (see "Frontend Integration" below). The endpoint is real and functional; it's just not wired into the SPA's session-refresh flow yet.

#### Get Current User
```bash
GET /api/v1/auth/me
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

#### Logout
```bash
POST /api/v1/auth/logout
Authorization: Bearer <token>
```
Requires a valid token but is otherwise a no-op server-side (`{"message": "Successfully logged out"}`) — there's no token blacklist or revocation. Logout is purely the client discarding its stored token.

### Profile Management

#### Update Profile
```bash
PUT /api/v1/users/me
Authorization: Bearer <token>
Content-Type: application/json

{
  "full_name": "John Smith Jr.",
  "bio": "Fantasy football champion 2023",
  "timezone": "America/New_York",
  "preferred_scoring": "PPR",
  "favorite_teams": ["BUF", "NYJ"],
  "notifications_enabled": true
}
```

#### Get User Statistics
```bash
GET /api/v1/users/me/stats
Authorization: Bearer <token>
```
```json
{
  "total_leagues": 3,
  "total_drafts": 8,
  "completed_drafts": 7,
  "member_since": "2024-01-15T10:30:00Z",
  "last_login": "2024-01-20T14:22:00Z"
}
```
(No `is_premium` field — see above.)

#### Other user routes that exist (`backend/app/api/v1/endpoints/users.py`)
- `DELETE /api/v1/users/me` — deactivates the account (`is_active = False`), does not hard-delete
- `GET /api/v1/users/me/drafts` — recent draft sessions
- `GET /api/v1/users/{username}/public` — limited public profile
- `GET /api/v1/users/{user_id}` — full profile by id

### League Management

#### Add League
```bash
POST /api/v1/users/me/leagues
Authorization: Bearer <token>
Content-Type: application/json

{
  "platform": "espn",
  "league_id": "123456",
  "team_id": "1",
  "league_name": "Championship League",
  "season": 2026,
  "scoring_format": "PPR",
  "league_size": 12,
  "is_commissioner": false
}
```
In practice, leagues are more often connected through the platform-specific flows in `backend/app/api/v1/endpoints/leagues.py` (`POST /api/v1/leagues/espn/connect`, `/sleeper/connect`, `/yahoo/connect`) rather than this generic endpoint, because those flows also validate the league against the real platform API and persist platform credentials (ESPN cookies, Yahoo OAuth tokens) needed for live-draft and scoring features — see `DRAFT_ASSISTANT_GUIDE.md`.

#### Get My Leagues
```bash
GET /api/v1/users/me/leagues
Authorization: Bearer <token>
```

#### Remove League
```bash
DELETE /api/v1/users/me/leagues/1
Authorization: Bearer <token>
```

### Password Management

#### Change Password
```bash
POST /api/v1/auth/change-password
Authorization: Bearer <token>
Content-Type: application/json

{
  "current_password": "OldPass123!",
  "new_password": "NewSecurePass456!"
}
```

#### Request Password Reset
```bash
POST /api/v1/auth/request-password-reset
Content-Type: application/json

{
  "email": "user@example.com"
}
```
Always returns a generic success message to avoid leaking which emails are registered — *except* when the email does match a real user, in which case the response also currently includes the raw reset token directly in the JSON body (`{"message": "...", "token": "..."}`), explicitly marked in the code as a dev convenience ("For development, return token (remove in production)"). This is real, current behavior, not hypothetical — be aware it means the reset token is not actually secret in this deployment today.

#### Reset Password
```bash
POST /api/v1/auth/reset-password
Content-Type: application/json

{
  "token": "password_reset_token_here",
  "new_password": "NewSecurePass456!"
}
```

### Email Verification

#### Verify Email
```bash
POST /api/v1/auth/verify-email
Content-Type: application/json

{
  "token": "email_verification_token_here"
}
```

#### Resend Verification
```bash
POST /api/v1/auth/resend-verification
Content-Type: application/json

{
  "email": "user@example.com"
}
```
Same dev-mode token-echo behavior as password reset (returns the token in the response body when a matching, unverified user exists).

These two endpoints are fully wired and functional, but — per "Register User" above — nothing currently requires a user to complete this flow. It exists for a future gated-access mode.

### Email Delivery

`backend/app/services/email_service.py` (`EmailService`) is genuinely real, not a stub: it builds real HTML/text verification and password-reset emails and will send them over SMTP when configured. Whether it actually sends or just logs is derived, not flag-driven:

```python
self.development_mode = not settings.SMTP_USERNAME
```

Configure real delivery with these `backend/.env` keys (note the real names — `SMTP_SERVER`, not `SMTP_HOST`, and `SMTP_USERNAME`, not `SMTP_USER`):
```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=noreply@yourdomain.com
```

**This environment currently has none of these set**, so `EmailService` runs in honest dev-log mode: it logs `EMAIL SENT (Dev Mode) - To: ..., Subject: ...` plus the full email body instead of calling `smtplib`, and still returns `True` (a "send" that didn't reach an inbox is not reported as a failure to the caller, since nothing did fail from the app's point of view). If you set all of `SMTP_SERVER`/`SMTP_USERNAME`/`SMTP_PASSWORD` (and optionally `SMTP_PORT`/`FROM_EMAIL`), the same code path sends real mail via `smtplib.SMTP(...).starttls()` — no code changes needed, just env vars.

## Demo Mode: user id `"1"`

`backend/app/api/deps.py::get_current_user` has intentional demo-mode behavior that this guide previously didn't document at all: if a valid JWT decodes to subject `"1"` but no `User` row with `id == 1` exists yet, it auto-creates one (`demo@test.com` / username `demo`, active and verified) instead of returning 401. If DB insertion itself fails, it falls back to an in-memory `User(id=1, ...)` object so the request still succeeds.

This is **intentional**, not a bug — per this repo's `CLAUDE.md`, don't "fix" it into a 401 without checking with the user first. In practice it means: any token minted with subject `1` (e.g. via `security.create_access_token(subject="1")`, or a hardcoded `id: 1` in older frontend/test code) will always resolve to *some* valid user, seeded on first use. On a database that already has a real user with `id == 1` (common in a long-lived dev DB), that existing row is returned as-is and the auto-create path never triggers.

## Security Features

### Password Requirements
Enforced by `UserCreate`/`PasswordChange`/`PasswordResetConfirm` validators in `backend/app/schemas/user.py`:
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number
- (No special-character requirement is enforced, despite what an older version of this doc implied.)

### Account Security
- **Account lockout**: 5 failed attempts locks the account for 15 minutes (`UserService.authenticate_user`, `backend/app/services/user_service.py`). The lockout check and the failed-password check share the same generic 401 response — see "Login" above.
- **Token expiration**: access tokens expire in **8 days** (`ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 8` in `backend/app/core/config.py`) — corrected from a previous version of this doc, which claimed 8 hours.
- **Refresh tokens**: valid for 30 days (`create_refresh_token`, `backend/app/core/security.py`)
- **Password reset**: 1 hour token expiration
- **Email verification**: 24 hour token expiration
- **Lockout-check bug, fixed**: an earlier version of `authenticate_user` compared a timezone-aware `locked_until` against a naive `datetime.now()`, which raised `TypeError: can't compare offset-naive and offset-aware datetimes` and crashed `/auth/login` with a 500 for *any* login attempt once an account had ever been locked. It's now `datetime.now(timezone.utc)` throughout — fixed in commit `a471226` ("Fix login 500 crash: naive/aware datetime comparison on account lockout check").

### Database Security
- **Password hashing**: bcrypt via `passlib` (`CryptContext(schemes=["bcrypt"], deprecated="auto")`)
- **No plaintext storage**: passwords are never stored in plaintext
- **Failed attempt tracking**: `failed_login_attempts` / `locked_until` columns on `users`
- **Soft deletion**: `DELETE /api/v1/users/me` sets `is_active = False`; there is no hard-delete path

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    username VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR NOT NULL,
    full_name VARCHAR,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    is_superuser BOOLEAN DEFAULT FALSE,
    avatar_url VARCHAR,
    bio TEXT,
    timezone VARCHAR DEFAULT 'UTC',
    preferred_scoring VARCHAR DEFAULT 'PPR',
    favorite_teams JSON,
    notifications_enabled BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP WITH TIME ZONE,
    login_count INTEGER DEFAULT 0,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);
```
(No `is_premium` column — removed from this doc; it never existed in `backend/app/models/user.py`.)

### User Leagues Table
```sql
CREATE TABLE user_leagues (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    platform VARCHAR NOT NULL, -- sleeper, espn, yahoo, nfl, cbs
    league_id VARCHAR NOT NULL,
    league_key VARCHAR,        -- Yahoo's composite key, e.g. "449.l.12345"
    team_id VARCHAR,
    league_name VARCHAR,
    season INTEGER DEFAULT 2024,
    scoring_format VARCHAR,
    league_size INTEGER,
    -- Real per-league roster/scoring extraction (new this session --
    -- see DRAFT_ASSISTANT_GUIDE.md's "Real per-league scoring rules" section)
    roster_positions TEXT,     -- JSON: {"starters": {...}, "bench": N, "roster_size": N}
    points_per_reception FLOAT,
    scoring_rules TEXT,        -- JSON: {"passing": {...}, "rushing": {...}, "receiving": {...}, "fumbles": {...}, "source": "sleeper"|"espn"}
    is_commissioner BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    enable_notifications BOOLEAN DEFAULT TRUE,
    auto_draft_assistant BOOLEAN DEFAULT TRUE,
    -- Per-user platform credentials (not shared/global state -- see
    -- DRAFT_ASSISTANT_GUIDE.md)
    espn_swid VARCHAR,
    espn_s2 VARCHAR,
    yahoo_access_token VARCHAR,
    yahoo_refresh_token VARCHAR,
    yahoo_token_expires_at TIMESTAMP WITH TIME ZONE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_synced TIMESTAMP WITH TIME ZONE
);
```

### Draft Sessions Table
```sql
CREATE TABLE draft_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    session_id VARCHAR UNIQUE NOT NULL,
    platform VARCHAR NOT NULL,
    league_id VARCHAR NOT NULL,
    user_team_id VARCHAR,
    draft_settings JSON,
    is_active BOOLEAN DEFAULT TRUE,
    is_completed BOOLEAN DEFAULT FALSE,
    user_roster JSON,
    draft_grade VARCHAR,
    final_analysis TEXT,
    recommendations_used INTEGER DEFAULT 0,
    ai_accuracy_score INTEGER,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Development Setup

### Environment Variables
```bash
# Required
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://user:pass@localhost:5432/fantasy_db

# Optional (real SMTP email delivery -- see "Email Delivery" above;
# omit any of these and EmailService degrades to honest dev-log mode)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=noreply@yourdomain.com
```
`backend/app/core/config.py`'s `Settings` uses `extra="ignore"`, so unrecognized `.env` keys no longer crash the entire backend on import — fixed this session (commit `f7edb81`, "Fix: Settings crashed the entire backend on any unrecognized .env key"). Previously, `pydantic-settings`' default `extra="forbid"` meant one stray/legacy `.env` line (e.g. a leftover key from a manual verification script) would take down the whole app at startup, not just fail to read that key.

### Database Migrations
```bash
cd backend
alembic revision --autogenerate -m "Create user tables"
alembic upgrade head
alembic downgrade -1
```

### Testing Authentication
```bash
# Register user
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","username":"testuser","password":"TestPass123!"}'

# Login
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPass123!"}'

# Get profile
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```
All three of the above were re-run live against a running instance of this codebase while writing this guide and returned the response shapes documented above.

## Frontend Integration

The real frontend auth code is smaller and simpler than earlier versions of this guide implied — no separate hand-rolled `useState`-based hook, no `refresh_token` persisted client-side. The actual files:

### `src/hooks/useAuth.tsx` — real auth context
```tsx
// Actual current implementation (trimmed of comments) -- a React Context
// provider, not a bare hook. login() takes an already-issued access token
// (from auth.login()'s response), not credentials -- credentials are
// posted directly to /auth/login by the caller, and only the resulting
// token is handed to login().
export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const login = async (token: string) => {
    localStorage.setItem('access_token', token)
    await refreshUser()
  }

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    setUser(null)
  }, [])

  const refreshUser = useCallback(async () => {
    try {
      const response = await auth.getProfile()
      setUser(response.data)
    } catch (error) {
      logout()
    }
  }, [logout])
  // ... loads on mount if a token is already in localStorage
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
```
Note the state field is `loading`, not `isLoading`, and there's no `token` field exposed at all — only `user` and `loading`.

### `src/components/common/ProtectedRoute.tsx` — real implementation
```tsx
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { user, loading } = useAuth()

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen">
      <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-600"></div>
    </div>
  }

  if (!user) {
    return <Navigate to="/auth" replace />
  }

  return <>{children}</>
}
```
Redirects to **`/auth`**, not `/login` — there is no `/login` route in this app; the single combined login/register page lives at `/auth`. This also matches `src/services/api.ts`'s response interceptor, which does the same redirect on any 401:
```ts
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/auth'
    }
    return Promise.reject(error)
  }
)
```
(An earlier version of this redirect pointed at `/login`, which didn't exist as a route and produced a dead-end 404 on any expired/invalid token — fixed in commit `ac6a9d7`.)

### `src/services/api.ts` — real `auth` group
```ts
export const auth = {
  register: (data: { email: string; username: string; password: string; full_name: string }) =>
    api.post('/auth/register', data),

  login: (data: { username: string; password: string }) =>
    api.post('/auth/login', { email: data.username, password: data.password }),

  getProfile: () => api.get('/auth/me'),

  // PUT /users/me (not /auth/me) -- profile updates are handled by users.py
  updateProfile: (data: Record<string, unknown>) => api.put('/users/me', data),
}
```
`API_BASE_URL` is hardcoded to `http://localhost:8000/api/v1` (no env-var override today), and the axios instance's request interceptor attaches `Authorization: Bearer <access_token>` from `localStorage` on every request automatically — components never need to pass the token manually.

## Next Steps

Real, currently-missing items (not implemented anywhere in this codebase today):
1. **Social login** (OAuth with Google/Facebook) — not implemented
2. **Two-Factor Authentication** — not implemented
3. **Admin dashboard** for user management — not implemented
4. **API rate limiting** on auth endpoints specifically — not implemented (no rate-limit middleware found on `/auth/*`)
5. **Audit logging** of auth events beyond `failed_login_attempts`/`last_login` — not implemented
6. **Token revocation / blacklist** — `/auth/logout` is currently a client-side-only no-op; a compromised token remains valid until it expires (up to 8 days) even after "logout"
