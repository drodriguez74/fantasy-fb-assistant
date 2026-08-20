#!/bin/bash

echo "📄 Creating database migration for Fantasy Football Assistant"
echo "=========================================================="

# Change to backend directory
cd "$(dirname "$0")/../backend" || exit 1

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Activated virtual environment"
fi

# Install requirements if needed
echo "📦 Installing/updating dependencies..."
pip install -r requirements.txt

# Create the migration
echo "📄 Creating initial database migration..."
alembic revision --autogenerate -m "Initial database schema"

if [ $? -eq 0 ]; then
    echo "✅ Migration created successfully!"
    echo ""
    echo "📋 Next steps:"
    echo "   1. Start PostgreSQL database"
    echo "   2. Run: alembic upgrade head"
    echo "   3. Run: python -c 'from app.db.init_db import init_db; init_db()'"
    echo ""
    echo "🐳 To start with Docker:"
    echo "   docker-compose up -d db redis"
    echo ""
else
    echo "❌ Migration creation failed"
    exit 1
fi