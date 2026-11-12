# Fantasy Football Assistant

An in-season fantasy football assistant for PPR leagues: lineup, waiver and trade advice from your real ESPN, Yahoo or Sleeper league, plus a betting board priced against the sportsbooks.

## 🏆 Features

- **This Week**: your matchup, start/sit calls and lineup swaps from live projections
- **Waivers and trades**: valued by what a player does to your real best lineup
- **Platform integrations**: ESPN (cookies), Yahoo (OAuth) and Sleeper leagues
- **Bets**: NFL props and game lines priced against a seven-book consensus, tracked and graded
- **AI content**: player analysis and injury reports with an OpenAI/Anthropic fallback
- **Accounts**: JWT auth; sign-up is closed unless an email is allowed (`REGISTRATION_ALLOWED_EMAILS`)

## 🛠 Tech Stack

- **Backend**: Python 3.11+ • FastAPI • SQLAlchemy • PostgreSQL • Alembic
- **Frontend**: React 19 • TypeScript • Vite • Tailwind CSS • Heroicons
- **AI**: OpenAI/Anthropic APIs for content generation
- **Auth**: JWT with secure password hashing
- **Development**: Hot reload, type checking, comprehensive error handling

## 📁 Project Structure

```
fantasy-football-assistant/
├── backend/                 # Python FastAPI backend
│   ├── app/
│   │   ├── api/v1/         # API endpoints
│   │   ├── core/           # Configuration and security
│   │   ├── db/             # Database configuration
│   │   ├── models/         # SQLAlchemy models
│   │   └── services/       # Business logic
│   ├── alembic/            # Database migrations
│   ├── requirements.txt
│   └── .env               # Environment variables
├── frontend/               # React TypeScript frontend
│   ├── src/
│   │   ├── components/     # Reusable components
│   │   ├── pages/          # Page components
│   │   ├── services/       # API calls
│   │   ├── types/          # TypeScript definitions
│   │   └── hooks/          # Custom React hooks
│   ├── package.json
│   └── tailwind.config.js
├── scripts/               # Setup and utility scripts
├── docs/                  # Documentation
└── .github/workflows/     # CI, weekly digest and betting board builds
```

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+** ([Download](https://python.org))
- **Node.js 18+** ([Download](https://nodejs.org))
- **PostgreSQL 14+** (Install via [Homebrew](https://brew.sh): `brew install postgresql`)

### 1️⃣ Backend Setup

```bash
# Navigate to backend
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL (if not running)
brew services start postgresql@14

# Create database and user
createdb fantasy_football_db
createuser -s fantasy_user
psql fantasy_football_db -c "ALTER USER fantasy_user PASSWORD 'fantasy_pass';"

# Run database migrations
alembic upgrade head

# Initialize with sample data
python -c "from app.db.init_db import init_db; init_db()"

# Start the backend server
uvicorn app.main:app --reload --port 8000
```

**Backend is now running at:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Alternative Docs:** http://localhost:8000/redoc

### 2️⃣ Frontend Setup

```bash
# Navigate to frontend (in a new terminal)
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

**Frontend is now running at:** http://127.0.0.1:3001

### 3️⃣ Create an account

Sign-up is closed by default. Add your email to `REGISTRATION_ALLOWED_EMAILS` in `backend/.env` (comma-separated, or `*` for anyone), restart the backend, then register at `/auth`. There are no built-in demo accounts.

## 🔧 Development Commands

### Backend Commands
```bash
# Start backend server
cd backend && source venv/bin/activate && uvicorn app.main:app --reload

# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Reset database
python -c "from app.db.init_db import init_db; init_db()"

# Run the tests (isolated SQLite, not your database)
pip install -r requirements-dev.txt && pytest
```

### Frontend Commands
```bash
# Start development server
cd frontend && npm run dev

# Build for production
npm run build

# Run linter and tests
npm run lint
npm test

# Preview production build
npm run preview
```

## 🌐 API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register (allowed emails only)
- `POST /api/v1/auth/login` - Log in
- `GET /api/v1/auth/me` - Current user

### Leagues
- `GET /api/v1/leagues/{id}/this-week` - Matchup, start/sit and lineup swaps
- `GET /api/v1/leagues/{id}/waiver-recommendations` - Waivers by lineup impact
- `GET /api/v1/leagues/{id}/trade-suggestions` - Trades that help both teams

### Betting
- `GET /api/v1/betting/board` - This week's priced props and game lines
- `GET /api/v1/betting/results` - Graded record

Full list: `docs/guides/API_GUIDE.md` or http://localhost:8000/docs.

## 🔐 Environment Variables

Create a `.env` file in the backend directory:

```env
# Database
DATABASE_URL=postgresql://fantasy_user:fantasy_pass@localhost:5432/fantasy_football_db

# Security
SECRET_KEY=your-secret-key-here

# AI APIs (optional - add your keys for full functionality)
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key

# Who may sign up (comma-separated emails, or * for anyone; unset = closed)
REGISTRATION_ALLOWED_EMAILS=you@example.com

# Yahoo OAuth app (optional; ESPN and Sleeper need no app credentials)
YAHOO_CLIENT_ID=your-yahoo-client-id
YAHOO_CLIENT_SECRET=your-yahoo-client-secret
```

## ✅ CI

`.github/workflows/ci.yml` runs the backend tests and the frontend lint, tests and build on every push and pull request. `docker-compose.yml` is out of date and not used.

## 📚 Additional Documentation

- [API Documentation](http://localhost:8000/docs) - Interactive API documentation

**Guides** (`docs/guides/`)
- [Development Guide](./docs/guides/DEVELOPMENT.md) - Detailed development setup and workflows
- [API Guide](./docs/guides/API_GUIDE.md) - Endpoint shapes and contracts
- [Authentication Guide](./docs/guides/AUTHENTICATION_GUIDE.md) - User management and security
- [Draft Assistant Guide](./docs/guides/DRAFT_ASSISTANT_GUIDE.md) - Draft recommendation engine
- [Enhanced Player Data](./docs/guides/ENHANCED_PLAYER_DATA.md) - Player data model
- [Style Guide](./docs/guides/STYLE_GUIDE.md) - Frontend visual/design conventions

**Manual test procedures** (`docs/testing/`)
- [Live Draft Test](./docs/testing/LIVE_DRAFT_TEST.md)
- [Yahoo Integration Test](./docs/testing/YAHOO_INTEGRATION_TEST.md)

**Audit history** (`docs/audits/`) - point-in-time findings, check git log before trusting an open item as still-current
- [Audit Task List](./docs/audits/AUDIT_TASK_LIST.md)
- [Decommission Task List](./docs/audits/DECOMMISSION_TASK_LIST.md)
- [Deferred Features Checklist](./docs/audits/DEFERRED_FEATURES_CHECKLIST.md)
- [UX Product Review](./docs/audits/UX_PRODUCT_REVIEW.md)
- [UX Task Checklist](./docs/audits/UX_TASK_CHECKLIST.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and test thoroughly
4. Commit with clear messages: `git commit -m "Add feature description"`
5. Push to your fork and submit a pull request

## 📝 License

MIT License - see LICENSE file for details

---

**Need help?** Check the [troubleshooting guide](./docs/guides/DEVELOPMENT.md#troubleshooting) or open an issue.