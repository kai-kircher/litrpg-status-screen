#!/bin/bash
#
# Deployment script for Wandering Inn Tracker
# Called by GitHub Actions after building images, or run manually.
#
# Usage:
#   ./deploy.sh           # Deploy without running migrations
#   ./deploy.sh migrate   # Deploy and run migrations
#

set -e

# Store original arguments for potential re-exec
ORIGINAL_ARGS=("$@")

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.prod.yml"
LOG_FILE="${SCRIPT_DIR}/deploy.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${GREEN}[${timestamp}]${NC} $1"
    echo "[${timestamp}] $1" >> "$LOG_FILE"
}

error() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${RED}[${timestamp}] ERROR:${NC} $1" >&2
    echo "[${timestamp}] ERROR: $1" >> "$LOG_FILE"
}

warn() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${YELLOW}[${timestamp}] WARNING:${NC} $1"
    echo "[${timestamp}] WARNING: $1" >> "$LOG_FILE"
}

info() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${BLUE}[${timestamp}]${NC} $1"
}

# Load environment variables
load_env() {
    if [ -f "${SCRIPT_DIR}/.env.production" ]; then
        log "Loading .env.production"
        set -a
        source "${SCRIPT_DIR}/.env.production"
        set +a
    elif [ -f "${SCRIPT_DIR}/.env" ]; then
        log "Loading .env"
        set -a
        source "${SCRIPT_DIR}/.env"
        set +a
    else
        warn "No .env file found, using defaults"
    fi
}

# Check prerequisites
check_prerequisites() {
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
        exit 1
    fi

    # Check for docker compose (v2) or docker-compose (v1)
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="docker-compose"
    else
        error "Docker Compose is not installed"
        exit 1
    fi

    if [ ! -f "$COMPOSE_FILE" ]; then
        error "Docker Compose file not found: $COMPOSE_FILE"
        exit 1
    fi
}

# Pull latest code and re-exec if script changed
pull_code() {
    if [ -d "${SCRIPT_DIR}/.git" ]; then
        # Get current script hash before pull
        local old_hash=$(md5sum "${SCRIPT_DIR}/deploy.sh" 2>/dev/null | cut -d' ' -f1)

        log "Pulling latest code from git..."
        cd "$SCRIPT_DIR"
        git fetch origin main --quiet
        git reset --hard origin/main --quiet
        log "Code updated to $(git rev-parse --short HEAD)"

        # Check if deploy.sh changed and we haven't already re-execed
        local new_hash=$(md5sum "${SCRIPT_DIR}/deploy.sh" 2>/dev/null | cut -d' ' -f1)
        if [ "$old_hash" != "$new_hash" ] && [ -z "$DEPLOY_REEXEC" ]; then
            log "deploy.sh changed, re-executing with new version..."
            export DEPLOY_REEXEC=1
            exec "${SCRIPT_DIR}/deploy.sh" "${ORIGINAL_ARGS[@]}"
        fi
    else
        log "Not a git repository, skipping pull"
    fi
}

# Login to container registry
login_registry() {
    log "Checking container registry authentication..."

    # Try GitHub Container Registry
    if [ -n "$GITHUB_TOKEN" ] && [ -n "$GITHUB_USER" ]; then
        log "Logging into GitHub Container Registry..."
        echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USER" --password-stdin 2>/dev/null
    elif [ -n "$CR_PAT" ]; then
        # Alternative: use CR_PAT (Container Registry Personal Access Token)
        log "Logging into GitHub Container Registry with PAT..."
        echo "$CR_PAT" | docker login ghcr.io -u "${GITHUB_USER:-$USER}" --password-stdin 2>/dev/null
    else
        log "Using existing Docker credentials (if any)"
    fi
}

# Pull new images
pull_images() {
    log "Pulling new Docker images..."
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" pull --quiet 2>/dev/null || \
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" pull
    log "Images pulled successfully"
}

# Run database migrations
run_migrations() {
    log "Running database migrations..."

    local db_user="${DB_USER:-wandering_inn}"
    local db_name="${DB_NAME:-wandering_inn_tracker}"

    # Wait for database to be ready
    log "Waiting for database to be ready..."
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if $DOCKER_COMPOSE -f "$COMPOSE_FILE" exec -T postgres pg_isready -U "$db_user" &>/dev/null; then
            log "Database is ready"
            break
        fi
        sleep 2
        ((attempt++))
    done

    if [ $attempt -gt $max_attempts ]; then
        error "Database did not become ready in time"
        return 1
    fi

    # Check if database exists, create if not
    log "Checking if database exists..."
    if ! $DOCKER_COMPOSE -f "$COMPOSE_FILE" exec -T postgres psql -U "$db_user" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db_name'" | grep -q 1; then
        log "Creating database '$db_name'..."
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" exec -T postgres psql -U "$db_user" -d postgres -c "CREATE DATABASE $db_name;"
    fi

    # Run migrations via psql inside the container (more reliable than host)
    log "Running SQL migrations inside container..."

    # First, ensure migrations table exists
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" exec -T postgres \
        psql -U "$db_user" -d "$db_name" \
        -f "/docker-entrypoint-initdb.d/migrations/000_create_migrations_table.sql" 2>/dev/null || true

    # Run each migration in order
    for migration in "${SCRIPT_DIR}"/database/migrations/*.sql; do
        if [ -f "$migration" ]; then
            local basename=$(basename "$migration")

            # Skip the migrations table creation (already done)
            if [ "$basename" = "000_create_migrations_table.sql" ]; then
                continue
            fi

            # Check if migration already applied
            local applied=$($DOCKER_COMPOSE -f "$COMPOSE_FILE" exec -T postgres \
                psql -U "$db_user" -d "$db_name" -tAc \
                "SELECT 1 FROM schema_migrations WHERE migration_name='$basename'" 2>/dev/null || echo "")

            if [ "$applied" != "1" ]; then
                log "  Applying: $basename"
                if $DOCKER_COMPOSE -f "$COMPOSE_FILE" exec -T postgres \
                    psql -U "$db_user" -d "$db_name" \
                    -f "/docker-entrypoint-initdb.d/migrations/$basename"; then
                    # Record migration
                    $DOCKER_COMPOSE -f "$COMPOSE_FILE" exec -T postgres \
                        psql -U "$db_user" -d "$db_name" \
                        -c "INSERT INTO schema_migrations (migration_name) VALUES ('$basename') ON CONFLICT DO NOTHING;"
                else
                    error "Failed to apply migration: $basename"
                    return 1
                fi
            else
                log "  Skipping (already applied): $basename"
            fi
        fi
    done

    log "Migrations completed"
}

# Restart services with minimal downtime
restart_services() {
    log "Restarting services..."

    # Start/restart database first
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d postgres

    # Wait for database
    sleep 5

    # Restart web service
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d web

    # Clean up orphaned containers
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d --remove-orphans

    log "Services restarted"
}

# Health check
health_check() {
    log "Running health check..."

    local health_url="http://localhost:${PORT:-3000}/api/health"
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -sf "$health_url" > /dev/null 2>&1; then
            log "Health check passed!"
            return 0
        fi

        log "Waiting for service to be ready (attempt $attempt/$max_attempts)..."
        sleep 2
        ((attempt++))
    done

    warn "Health check did not pass after $max_attempts attempts"
    warn "Service may still be starting up..."
    return 0  # Don't fail deployment on health check timeout
}

# Cleanup old images and containers
cleanup() {
    log "Cleaning up..."
    docker image prune -f --filter "until=24h" 2>/dev/null || true
    docker container prune -f 2>/dev/null || true
    log "Cleanup completed"
}

# Show status
show_status() {
    info ""
    info "=========================================="
    info "Deployment Status"
    info "=========================================="
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" ps
    info ""
    info "Application: http://localhost:${PORT:-3000}"
    info "Admin Panel: http://localhost:${PORT:-3000}/admin"
    info ""
    info "View logs: $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f"
    info "=========================================="
}

# Main deployment flow
main() {
    local run_migrations_flag="${1:-}"

    log "=========================================="
    log "Starting deployment"
    log "=========================================="

    load_env
    check_prerequisites
    pull_code
    login_registry
    pull_images

    # Always run migrations on deploy (they're idempotent)
    if [ "$run_migrations_flag" = "migrate" ] || [ "$run_migrations_flag" = "" ]; then
        restart_services
        run_migrations
    else
        restart_services
    fi

    health_check
    cleanup
    show_status

    log "=========================================="
    log "Deployment completed!"
    log "=========================================="
}

# Run main function
main "$@"
