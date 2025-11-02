#!/bin/bash
# Script to create .env.production with a secure password

set -e

echo "🔒 Creating .env.production file..."

# Check if .env.production already exists
if [ -f .env.production ]; then
    echo "⚠️  .env.production already exists!"
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborted. Keeping existing .env.production"
        exit 1
    fi
fi

# Generate secure password
SECURE_PASSWORD=$(openssl rand -base64 32)

# Create .env.production
cat > .env.production <<EOF
# Production Environment Variables
# Generated on $(date)

# Database Configuration
DB_HOST=postgres
DB_PORT=5432
DB_NAME=wandering_inn_tracker
DB_USER=wandering_inn
DB_PASSWORD=${SECURE_PASSWORD}

# Node Environment
NODE_ENV=production

# Application Port (default: 3000)
PORT=3000
EOF

echo "✅ Created .env.production with secure password"
echo ""
echo "📝 Database password: ${SECURE_PASSWORD}"
echo ""
echo "⚠️  IMPORTANT: Save this password securely!"
echo "   You'll need it if you want to access the database directly."
echo ""
echo "🚀 You can now run: ./deploy.sh"
