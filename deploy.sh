#!/bin/bash
set -e

echo "🚀 Deploying Wandering Inn Tracker..."

# Check if .env.production exists
if [ ! -f .env.production ]; then
    echo "❌ Error: .env.production file not found!"
    echo "📝 Please create it from .env.production.example"
    exit 1
fi

# Load environment variables
export $(cat .env.production | grep -v '^#' | xargs)

echo "📦 Building Docker images..."
docker compose -f docker-compose.prod.yml build

echo "🗄️  Starting database..."
docker compose -f docker-compose.prod.yml up -d postgres

echo "⏳ Waiting for database to be ready..."
sleep 10

echo "🔄 Running database migrations..."
cd database
if [ -f migrate.sh ]; then
    ./migrate.sh
else
    echo "⚠️  No migration script found, skipping..."
fi
cd ..

echo "🌐 Starting web application..."
docker compose -f docker-compose.prod.yml up -d web

echo "✅ Deployment complete!"
echo ""
echo "📊 Application Status:"
docker compose -f docker-compose.prod.yml ps

echo ""
echo "🔗 Application should be accessible at:"
echo "   http://localhost:${PORT:-3000}"
echo ""
echo "📝 To view logs:"
echo "   docker compose -f docker-compose.prod.yml logs -f web"
echo ""
echo "🛠️  To access admin panel:"
echo "   http://localhost:${PORT:-3000}/admin"
