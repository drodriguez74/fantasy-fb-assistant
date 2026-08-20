#!/bin/bash

echo "🗄️ Fantasy Football Assistant - Database Setup"
echo "=============================================="

# Change to backend directory
cd "$(dirname "$0")/../backend" || exit 1

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "📋 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please update .env file with your database credentials"
    echo "   Default: postgresql://fantasy_user:fantasy_pass@localhost:5432/fantasy_football_db"
fi

# Install dependencies if not already installed
echo "📦 Installing Python dependencies..."
if [ ! -d "venv" ]; then
    python -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt

# Check if PostgreSQL is running
echo "🔍 Checking PostgreSQL connection..."
python -c "
import psycopg2
from app.core.config import settings

try:
    # Parse database URL
    db_url = settings.DATABASE_URL
    if db_url.startswith('postgresql://'):
        # Extract connection details
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port,
            user=parsed.username,
            password=parsed.password,
            dbname=parsed.path[1:]  # Remove leading slash
        )
        conn.close()
        print('✅ PostgreSQL connection successful')
    else:
        print('❌ Invalid DATABASE_URL format')
        exit(1)
except Exception as e:
    print(f'❌ PostgreSQL connection failed: {e}')
    print('')
    print('🐳 To start PostgreSQL with Docker:')
    print('   docker-compose up -d db')
    print('')
    print('📊 Or install PostgreSQL locally:')
    print('   brew install postgresql (macOS)')
    print('   sudo apt-get install postgresql (Ubuntu)')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "💡 Starting database with Docker Compose..."
    cd ..
    docker-compose up -d db redis
    sleep 5
    cd backend
fi

# Create initial migration
echo "📄 Creating initial database migration..."
if [ ! -f "alembic/versions/$(ls alembic/versions/ 2>/dev/null | head -1)" ]; then
    alembic revision --autogenerate -m "Initial migration"
    echo "✅ Created initial migration"
else
    echo "📄 Migration already exists, creating new one..."
    alembic revision --autogenerate -m "Update schema"
fi

# Run migrations
echo "🔄 Running database migrations..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✅ Database migrations completed successfully"
else
    echo "❌ Database migration failed"
    exit 1
fi

# Initialize database with sample data
echo "🌱 Initializing database with sample data..."
python -c "
from app.db.init_db import init_db
init_db()
"

if [ $? -eq 0 ]; then
    echo "✅ Database initialization completed"
else
    echo "❌ Database initialization failed"
    exit 1
fi

echo ""
echo "🎉 Database setup completed successfully!"
echo ""
echo "📊 Database Info:"
echo "   URL: $(python -c 'from app.core.config import settings; print(settings.DATABASE_URL)')"
echo ""
echo "👤 Test Accounts Created:"
echo "   Admin: admin@fantasyfootball.com / admin123"
echo "   User:  test@example.com / password123"
echo ""
echo "🚀 You can now start the API server:"
echo "   uvicorn app.main:app --reload"
echo ""