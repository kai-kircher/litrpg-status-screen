#!/bin/bash
# Database migration runner
# Usage: ./migrate.sh [up|down|status|reset]

set -e

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Database connection parameters
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-wandering_inn_tracker}"
DB_USER="${DB_USER:-wandering_inn}"
DB_PASSWORD="${DB_PASSWORD:-dev_password_change_in_production}"

# PSQL command with connection string
PSQL="PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME"

# Migrations directory
MIGRATIONS_DIR="$(dirname "$0")/migrations"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to check if database exists, create if missing
check_database() {
    echo "Checking database connection..."
    if ! PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw $DB_NAME; then
        echo -e "${YELLOW}Database '$DB_NAME' does not exist, creating...${NC}"
        if PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME;" 2>/dev/null; then
            echo -e "${GREEN}Database '$DB_NAME' created successfully${NC}"
        else
            echo -e "${RED}Error: Failed to create database '$DB_NAME'${NC}"
            exit 1
        fi
    fi
    echo -e "${GREEN}Database connection successful${NC}"
}

# Function to initialize migration tracking
init_migrations() {
    echo "Initializing migration tracking..."
    $PSQL -f "$MIGRATIONS_DIR/000_create_migrations_table.sql" 2>/dev/null || true
    echo -e "${GREEN}Migration tracking initialized${NC}"
}

# Function to get applied migrations
get_applied_migrations() {
    $PSQL -t -c "SELECT migration_name FROM schema_migrations ORDER BY migration_name;" 2>/dev/null | sed 's/^[ \t]*//' | grep -v '^$' || true
}

# Function to get pending migrations
get_pending_migrations() {
    applied=$(get_applied_migrations)

    for migration_file in "$MIGRATIONS_DIR"/*.sql; do
        filename=$(basename "$migration_file")

        # Skip the migrations table creation
        if [ "$filename" = "000_create_migrations_table.sql" ]; then
            continue
        fi

        # Check if this migration has been applied
        if ! echo "$applied" | grep -q "^$filename$"; then
            echo "$filename"
        fi
    done
}

# Function to run migrations
migrate_up() {
    check_database
    init_migrations

    pending=$(get_pending_migrations)

    if [ -z "$pending" ]; then
        echo -e "${GREEN}No pending migrations${NC}"
        return 0
    fi

    echo "Applying migrations..."
    echo "$pending" | while read -r migration; do
        echo -e "${YELLOW}Applying: $migration${NC}"

        # Run the migration
        if $PSQL -f "$MIGRATIONS_DIR/$migration"; then
            # Record the migration
            $PSQL -c "INSERT INTO schema_migrations (migration_name) VALUES ('$migration');"
            echo -e "${GREEN}✓ Applied: $migration${NC}"
        else
            echo -e "${RED}✗ Failed: $migration${NC}"
            exit 1
        fi
    done

    echo -e "${GREEN}All migrations applied successfully${NC}"
}

# Function to show migration status
migration_status() {
    check_database
    init_migrations

    echo "=== Applied Migrations ==="
    applied=$(get_applied_migrations)
    if [ -z "$applied" ]; then
        echo "None"
    else
        echo "$applied" | while read -r migration; do
            echo -e "${GREEN}✓ $migration${NC}"
        done
    fi

    echo ""
    echo "=== Pending Migrations ==="
    pending=$(get_pending_migrations)
    if [ -z "$pending" ]; then
        echo "None"
    else
        echo "$pending" | while read -r migration; do
            echo -e "${YELLOW}• $migration${NC}"
        done
    fi
}

# Function to reset database (dangerous!)
reset_database() {
    echo -e "${RED}WARNING: This will drop and recreate the database!${NC}"
    read -p "Are you sure? (yes/no): " -r
    if [ "$REPLY" != "yes" ]; then
        echo "Aborted"
        exit 0
    fi

    echo "Dropping database..."
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"

    echo "Creating database..."
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME;"

    echo "Running migrations..."
    migrate_up

    echo -e "${GREEN}Database reset complete${NC}"
}

# Main command handler
case "${1:-up}" in
    up)
        migrate_up
        ;;
    status)
        migration_status
        ;;
    reset)
        reset_database
        ;;
    *)
        echo "Usage: $0 [up|status|reset]"
        echo ""
        echo "Commands:"
        echo "  up      - Apply pending migrations (default)"
        echo "  status  - Show migration status"
        echo "  reset   - Drop and recreate database (DANGEROUS!)"
        exit 1
        ;;
esac
