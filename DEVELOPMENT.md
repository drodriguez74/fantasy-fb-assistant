# Fantasy Football Assistant - Development Guide

This guide provides detailed instructions for setting up, running, and maintaining the Fantasy Football Assistant development environment.

## 🚀 Quick Start Commands

### Starting the Application

**Option 1: Individual Services**
```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend  
cd frontend
npm run dev
```

**Option 2: Using Scripts**
```bash
# Backend
./scripts/start-backend.sh

# Frontend
./scripts/start-frontend.sh
```

### Stopping the Application

- **Backend**: Press `Ctrl+C` in the backend terminal
- **Frontend**: Press `Ctrl+C` in the frontend terminal
- **PostgreSQL**: `brew services stop postgresql@14` (if you want to stop the database)

## 🗄️ Database Management

### Starting/Stopping PostgreSQL

```bash
# Start PostgreSQL
brew services start postgresql@14

# Stop PostgreSQL  
brew services stop postgresql@14

# Check status
brew services list | grep postgres
```

### Database Operations

```bash
# Navigate to backend
cd backend && source venv/bin/activate

# Create new migration after model changes
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Reset database with fresh sample data
python -c "from app.db.init_db import init_db; init_db()"

# Check database connection
python -c "
from app.db.base import SessionLocal
from app.models import User
db = SessionLocal()
print(f'Users in database: {db.query(User).count()}')
db.close()
"
```

### Sample Data

The application includes these demo accounts:

| Account Type | Email | Password | Description |
|--------------|-------|----------|-------------|
| **Admin** | `admin@fantasyfootball.com` | `admin123` | Full system access |
| **User** | `test@example.com` | `password123` | Regular user account |

**Sample data includes:**
- 4 players (Josh Allen, Christian McCaffrey, Tyreek Hill, Travis Kelce)
- 1 sample blog post with multi-perspective analysis
- 1 test league connection

## 🔧 Development Workflows

### Adding New Features

1. **Backend Changes:**
   ```bash
   cd backend
   source venv/bin/activate
   
   # Create new model/endpoint
   # Edit files in app/models/ or app/api/v1/endpoints/
   
   # Create migration if models changed
   alembic revision --autogenerate -m "Add new feature"
   alembic upgrade head
   
   # Test changes
   python -c "from app.main import app; print('✅ App loads successfully')"
   ```

2. **Frontend Changes:**
   ```bash
   cd frontend
   
   # Add new components in src/components/
   # Add new pages in src/pages/
   # Update types in src/types/
   
   # Check for issues
   npm run lint
   ```

### Code Quality

```bash
# Backend linting (if configured)
cd backend
source venv/bin/activate
# Add tools like black, flake8, mypy to requirements-dev.txt

# Frontend linting
cd frontend
npm run lint
npm run build  # Check for build errors
```

### Testing API Endpoints

**Using the Interactive Docs:**
- Visit http://localhost:8000/docs
- Use the "Try it out" feature for each endpoint
- Authenticate using the demo accounts

**Using curl:**
```bash
# Test registration
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "username": "newuser", 
    "password": "password123",
    "full_name": "New User"
  }'

# Test login
curl -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=password123"

# Test protected endpoint (replace YOUR_TOKEN)
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 🐳 Docker Development

### Using Docker Compose

```bash
# Start all services (PostgreSQL, Redis, Backend, Frontend)
docker-compose up -d

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Rebuild after changes
docker-compose up --build

# Stop all services
docker-compose down

# Remove volumes (reset database)
docker-compose down -v
```

### Individual Docker Commands

```bash
# Build backend
docker build -t ff-backend ./backend

# Run backend container
docker run -p 8000:8000 --env-file backend/.env ff-backend

# Build frontend  
docker build -t ff-frontend ./frontend

# Run frontend container
docker run -p 5173:5173 ff-frontend
```

## 🛠️ Troubleshooting

### Common Issues

**Backend won't start:**
```bash
# Check Python virtual environment
cd backend
source venv/bin/activate
python --version  # Should be 3.11+

# Check database connection
python -c "
from app.core.config import settings
print('Database URL:', settings.DATABASE_URL)
"

# Reinstall dependencies
pip install -r requirements.txt
```

**Database connection errors:**
```bash
# Check if PostgreSQL is running
brew services list | grep postgres

# Start PostgreSQL if needed
brew services start postgresql@14

# Test database connection
psql fantasy_football_db -c "SELECT version();"

# Reset database
dropdb fantasy_football_db
createdb fantasy_football_db
cd backend && source venv/bin/activate
alembic upgrade head
python -c "from app.db.init_db import init_db; init_db()"
```

**Frontend won't start:**
```bash
# Check Node.js version
node --version  # Should be 18+
npm --version

# Clear and reinstall dependencies
cd frontend
rm -rf node_modules package-lock.json
npm install

# Check for port conflicts
lsof -i :5173  # Kill process if needed
```

**API calls failing:**
```bash
# Check CORS settings in backend/.env
CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"]

# Verify backend is running
curl http://localhost:8000/

# Check browser network tab for specific errors
```

### Performance Issues

**Backend slow:**
- Check database indexes in models
- Monitor query performance in logs
- Consider adding Redis caching

**Frontend slow:**
- Run `npm run build` to check bundle size
- Use React DevTools Profiler
- Check for unnecessary re-renders

### Environment Issues

**Missing environment variables:**
```bash
# Backend - check .env file exists
cd backend
ls -la .env

# Copy from template if missing
cp .env.example .env
# Edit .env with your values
```

**Port conflicts:**
```bash
# Find what's using the ports
lsof -i :8000  # Backend
lsof -i :5173  # Frontend
lsof -i :5432  # PostgreSQL

# Kill conflicting processes
kill -9 PID_NUMBER
```

## 📁 File Structure Guide

### Backend Structure
```
backend/
├── app/
│   ├── api/v1/
│   │   ├── endpoints/       # API route handlers
│   │   └── router.py        # Main API router
│   ├── core/
│   │   ├── config.py        # App configuration
│   │   └── security.py      # Auth & security
│   ├── db/
│   │   ├── base.py          # Database setup
│   │   └── init_db.py       # Database initialization
│   ├── models/              # SQLAlchemy models
│   └── services/            # Business logic
├── alembic/                 # Database migrations
├── requirements.txt         # Python dependencies
└── .env                     # Environment variables
```

### Frontend Structure
```
frontend/
├── src/
│   ├── components/
│   │   ├── auth/            # Authentication components
│   │   ├── common/          # Shared components
│   │   └── players/         # Player-specific components
│   ├── hooks/               # Custom React hooks
│   ├── pages/               # Page components
│   ├── services/            # API service layer
│   ├── types/               # TypeScript definitions
│   └── utils/               # Utility functions
├── package.json             # Dependencies
└── tailwind.config.js       # Styling configuration
```

## 🚀 Deployment Preparation

### Production Build

```bash
# Backend - no special build needed, just ensure:
cd backend
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head

# Frontend - create production build
cd frontend
npm run build
# Output in dist/ folder

# Test production build locally
npm run preview
```

### Environment Variables for Production

```env
# backend/.env.production
DATABASE_URL=postgresql://user:pass@prod-db:5432/ff_db
SECRET_KEY=your-secure-secret-key
ENVIRONMENT=production

# Add your API keys
OPENAI_API_KEY=your-production-openai-key
ANTHROPIC_API_KEY=your-production-anthropic-key
```

## 📚 Additional Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **React Documentation**: https://react.dev/
- **SQLAlchemy Documentation**: https://docs.sqlalchemy.org/
- **Tailwind CSS**: https://tailwindcss.com/docs
- **Alembic Documentation**: https://alembic.sqlalchemy.org/

## 🆘 Getting Help

1. **Check the logs** first - they usually contain helpful error messages
2. **Search existing issues** in the repository  
3. **Create a new issue** with:
   - Steps to reproduce
   - Error messages
   - Your environment (OS, Python version, Node version)
   - What you expected vs what happened

---

**Happy coding!** 🚀