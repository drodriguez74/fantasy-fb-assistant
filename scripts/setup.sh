#!/bin/bash

echo "🚀 Setting up Fantasy Football Assistant..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env file for backend if it doesn't exist
if [ ! -f "./backend/.env" ]; then
    echo "📋 Creating backend .env file..."
    cp ./backend/.env.example ./backend/.env
    echo "⚠️  Please update the .env file with your API keys and secrets"
fi

# Start services
echo "🐳 Starting Docker services..."
docker-compose up -d

echo "⏳ Waiting for services to be ready..."
sleep 10

# Run database migrations (once implemented)
echo "🗄️  Running database migrations..."
# docker-compose exec backend alembic upgrade head

echo "✅ Setup complete!"
echo ""
echo "🌐 Frontend: http://localhost:3000"
echo "🔌 Backend API: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo ""
echo "To stop services: docker-compose down"