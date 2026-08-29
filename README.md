# Fantasy Football Assistant

An AI-powered fantasy football assistant that helps PPR league users with draft picks, waiver wire decisions, and provides intelligent content aggregation from multiple fantasy football sources.

## 🏆 Features

- **🎯 Smart Draft Assistant**: PPR-optimized player rankings and real-time draft recommendations
- **🔌 Platform Integrations**: Connect to ESPN, Yahoo, Sleeper, NFL.com, and CBS Fantasy
- **🤖 AI-Powered Content**: Multi-perspective analysis with consensus recommendations
- **📊 Player Analytics**: Comprehensive player database with injury tracking and projections
- **👤 User Management**: JWT authentication with personalized preferences
- **📱 Responsive UI**: Modern React interface with mobile support

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
└── docker-compose.yml     # Development environment
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

**Frontend is now running at:** http://localhost:5173

### 3️⃣ Test the Application

**Demo Accounts:**
- **Admin:** `admin@fantasyfootball.com` / `admin123`
- **User:** `test@example.com` / `password123`
- **Demo:** `demo@test.com` / `DemoPass123!`

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
```

### Frontend Commands
```bash
# Start development server
cd frontend && npm run dev

# Build for production
npm run build

# Run linter
npm run lint

# Preview production build
npm run preview
```

## 🌐 API Endpoints

### Authentication
- `POST /api/v1/auth/register` - User registration
- `POST /api/v1/auth/token` - User login
- `GET /api/v1/auth/me` - Get current user

### Players
- `GET /api/v1/players/` - List all players
- `GET /api/v1/players/{id}` - Get player details
- `GET /api/v1/players/search` - Search players

### Draft Assistant
- `POST /api/v1/draft/start` - Start draft session
- `GET /api/v1/draft/{session_id}/recommendations` - Get recommendations
- `POST /api/v1/draft/{session_id}/picks` - Record draft pick

### Content
- `GET /api/v1/content/blog-posts/` - List blog posts
- `POST /api/v1/content/generate` - Generate AI content

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

# Fantasy Platform APIs (optional)
ESPN_CLIENT_ID=your-espn-client-id
ESPN_CLIENT_SECRET=your-espn-client-secret
YAHOO_CLIENT_ID=your-yahoo-client-id
YAHOO_CLIENT_SECRET=your-yahoo-client-secret
```

## 🐳 Docker Development (Alternative)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

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