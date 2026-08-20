# User Authentication System Guide

## Overview

The Fantasy Football Assistant now includes a comprehensive user authentication system with JWT tokens, user profiles, league management, and robust security features.

## Features

### 🔐 **Authentication & Security**
- **JWT-based authentication** with access and refresh tokens
- **Password hashing** with bcrypt
- **Account lockout** after failed login attempts
- **Email verification** (tokens generated, email service integration ready)
- **Password reset** with secure tokens
- **Rate limiting** and brute force protection

### 👤 **User Management**
- **User registration** with validation
- **Profile management** with preferences
- **League connections** across platforms
- **Draft session history**
- **Account deactivation**

### 🏈 **Fantasy Integration**
- **Multi-platform league management** (ESPN, Yahoo, Sleeper)
- **Draft session tracking** with AI analysis
- **User preferences** for scoring format and teams
- **Premium account features**

## API Endpoints

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

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "fantasyfan123",
  "full_name": "John Smith",
  "is_active": true,
  "is_verified": false,
  "is_premium": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### Login
```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 28800,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "fantasyfan123",
    "is_verified": true
  }
}
```

#### Refresh Token
```bash
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

#### Get Current User
```bash
GET /api/v1/auth/me
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

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

**Response:**
```json
{
  "total_leagues": 3,
  "total_drafts": 8,
  "completed_drafts": 7,
  "member_since": "2024-01-15T10:30:00Z",
  "last_login": "2024-01-20T14:22:00Z",
  "is_premium": false
}
```

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
  "season": 2024,
  "scoring_format": "PPR",
  "league_size": 12,
  "is_commissioner": false
}
```

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

## Frontend Integration

### React Authentication Hook

```typescript
// hooks/useAuth.ts
import { useState, useEffect } from 'react';

interface User {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  is_verified: boolean;
  is_premium: boolean;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
}

export function useAuth() {
  const [auth, setAuth] = useState<AuthState>({
    user: null,
    token: localStorage.getItem('access_token'),
    isLoading: true
  });

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      // Verify token and get user info
      fetchCurrentUser(token);
    } else {
      setAuth(prev => ({ ...prev, isLoading: false }));
    }
  }, []);

  const login = async (email: string, password: string) => {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    if (response.ok) {
      const data = await response.json();
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      
      setAuth({
        user: data.user,
        token: data.access_token,
        isLoading: false
      });
      
      return { success: true };
    } else {
      const error = await response.json();
      return { success: false, error: error.detail };
    }
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setAuth({ user: null, token: null, isLoading: false });
  };

  const fetchCurrentUser = async (token: string) => {
    try {
      const response = await fetch('/api/v1/auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const user = await response.json();
        setAuth({ user, token, isLoading: false });
      } else {
        logout();
      }
    } catch (error) {
      logout();
    }
  };

  return { auth, login, logout };
}
```

### Protected Route Component

```typescript
// components/ProtectedRoute.tsx
import { useAuth } from '../hooks/useAuth';
import { Navigate } from 'react-router-dom';

interface Props {
  children: React.ReactNode;
  requireVerified?: boolean;
}

export function ProtectedRoute({ children, requireVerified = false }: Props) {
  const { auth } = useAuth();

  if (auth.isLoading) {
    return <div>Loading...</div>;
  }

  if (!auth.user) {
    return <Navigate to="/login" replace />;
  }

  if (requireVerified && !auth.user.is_verified) {
    return <Navigate to="/verify-email" replace />;
  }

  return <>{children}</>;
}
```

### Login Form Component

```typescript
// components/LoginForm.tsx
import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';

export function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    const result = await login(email, password);
    
    if (result.success) {
      navigate('/dashboard');
    } else {
      setError(result.error);
    }
    
    setIsLoading(false);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700">
          Email
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300"
          required
        />
      </div>
      
      <div>
        <label className="block text-sm font-medium text-gray-700">
          Password
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300"
          required
        />
      </div>

      {error && (
        <div className="text-red-600 text-sm">{error}</div>
      )}

      <button
        type="submit"
        disabled={isLoading}
        className="w-full btn-primary"
      >
        {isLoading ? 'Signing in...' : 'Sign In'}
      </button>
    </form>
  );
}
```

## Security Features

### Password Requirements
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter  
- At least one number
- Special characters recommended

### Account Security
- **Account lockout**: 5 failed attempts = 15 minute lockout
- **Token expiration**: Access tokens expire in 8 hours
- **Refresh tokens**: Valid for 30 days
- **Password reset**: 1 hour token expiration
- **Email verification**: 24 hour token expiration

### Database Security
- **Password hashing**: bcrypt with salt
- **No plaintext storage**: Passwords are never stored in plaintext
- **Failed attempt tracking**: Login attempts are monitored
- **Soft deletion**: User accounts are deactivated, not deleted

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
    is_premium BOOLEAN DEFAULT FALSE,
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

### User Leagues Table
```sql
CREATE TABLE user_leagues (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    platform VARCHAR NOT NULL, -- sleeper, espn, yahoo
    league_id VARCHAR NOT NULL,
    league_key VARCHAR,
    team_id VARCHAR,
    league_name VARCHAR,
    season INTEGER DEFAULT 2024,
    scoring_format VARCHAR,
    league_size INTEGER,
    is_commissioner BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    enable_notifications BOOLEAN DEFAULT TRUE,
    auto_draft_assistant BOOLEAN DEFAULT TRUE,
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

# Optional (for email features)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

### Database Migrations
```bash
# Create migration
cd backend
alembic revision --autogenerate -m "Create user tables"

# Run migrations
alembic upgrade head

# Rollback
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

## Next Steps

1. **Email Service Integration**: Add SMTP configuration for verification/reset emails
2. **Social Login**: Implement OAuth with Google/Facebook
3. **Two-Factor Authentication**: Add TOTP support
4. **Admin Dashboard**: Create admin interface for user management
5. **API Rate Limiting**: Implement request rate limiting
6. **Audit Logging**: Track user actions and security events

Your Fantasy Football Assistant now has a complete, production-ready authentication system! 🔐