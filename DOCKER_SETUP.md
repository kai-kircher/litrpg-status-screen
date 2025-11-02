# Docker Setup Guide

## Overview

The Wandering Inn Tracker has been fully containerized with Docker. All three components (PostgreSQL, Scraper, and Web App) can run in containers.

## Components

### 1. PostgreSQL Database
- **Image**: postgres:16-alpine
- **Port**: 54320:5432 (host:container)
- **Container**: wandering-inn-db
- **Status**: ✅ Fully working

### 2. Python Scraper
- **Base**: python:3.11-slim
- **Container**: wandering-inn-scraper
- **Profile**: `scraper` (runs on-demand)
- **Status**: ✅ Fully working

### 3. Next.js Web App
- **Base**: node:20-alpine
- **Port**: 3000:3000
- **Container**: wandering-inn-web
- **Status**: ✅ Fully working

## Migration from Tanstack Start to Next.js

The web app was rebuilt from scratch using Next.js 15 instead of Tanstack Start due to dependency issues. The new app includes:

- **Framework**: Next.js 15 with App Router
- **TypeScript**: Full type safety
- **Styling**: Tailwind CSS
- **Database**: PostgreSQL via `pg` library
- **API Routes**:
  - `/api/health` - Database health check
  - `/api/characters` - GET/POST characters
  - `/api/chapters` - GET chapters

## Quick Start

### Start Database Only (Default)
```bash
docker-compose up -d
```

This starts just PostgreSQL, useful for running migrations or connecting external tools.

### Start Database + Web App
```bash
docker-compose --profile web up -d
```

Access the web app at: http://localhost:3000

### Using the Scraper

**The scraper is designed for one-off commands, not as a persistent service.**

```bash
# 1. Start database
docker-compose up -d

# 2. Build table of contents (REQUIRED FIRST STEP)
docker-compose run --rm scraper python -m src.main build-toc

# 3. Verify ToC was populated
docker-compose run --rm scraper python -m src.main show-toc

# 4. Scrape chapters
docker-compose run --rm scraper python -m src.main scrape --max 5

# 5. Check scraper status
docker-compose run --rm scraper python -m src.main check-db
```

### Full Scraper Workflow

```bash
# Start database
docker-compose up -d

# Step 1: Build ToC (scrapes the table of contents page)
docker-compose run --rm scraper python -m src.main build-toc

# Step 2: Scrape chapters (uses ToC URLs from step 1)
docker-compose run --rm scraper python -m src.main scrape --max 10

# Stop database
docker-compose down
```

### Stop All Containers
```bash
docker-compose down
```

### View Logs
```bash
docker-compose logs postgres          # Database logs
docker-compose --profile web logs web # Web app logs (if running)
docker-compose logs scraper           # Scraper logs (if running)
```

## Environment Variables

### Web App (`docker-compose.yml`)
```yaml
environment:
  DB_HOST: postgres
  DB_PORT: 5432
  DB_NAME: wandering_inn_tracker
  DB_USER: wandering_inn
  DB_PASSWORD: dev_password_change_in_production
  NODE_ENV: production
```

### Scraper (`docker-compose.yml`)
```yaml
environment:
  DB_HOST: postgres
  DB_PORT: 5432
  DB_NAME: wandering_inn_tracker
  DB_USER: wandering_inn
  DB_PASSWORD: dev_password_change_in_production
```

## Database

### Auto-Initialization
The database automatically runs migrations on first startup from `database/` directory files.

### Access PostgreSQL Directly
```bash
# Via Docker
docker exec -it wandering-inn-db psql -U wandering_inn -d wandering_inn_tracker

# Via Host (port 54320)
psql -h localhost -p 54320 -U wandering_inn -d wandering_inn_tracker
```

### pgAdmin (Optional)
```bash
docker-compose --profile tools up -d pgadmin
```
Access at: http://localhost:5050
- Email: admin@wandering-inn.local
- Password: admin

## File Structure

```
wandering-inn-tracker/
├── docker-compose.yml          # Container orchestration
├── database/
│   ├── migrations/             # SQL migration files
│   └── schema.sql              # Database schema
├── scraper/
│   ├── Dockerfile              # Python scraper image
│   ├── .dockerignore
│   ├── requirements.txt
│   └── src/                    # Scraper source code
├── web/
│   ├── Dockerfile              # Next.js app image
│   ├── .dockerignore
│   ├── next.config.ts
│   ├── package.json
│   ├── app/                    # Next.js App Router
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── api/                # API routes
│   │       ├── health/
│   │       ├── characters/
│   │       └── chapters/
│   └── lib/
│       └── db.ts               # Database connection
└── web-tanstack-backup/        # Old Tanstack app (reference)
```

## Dockerfiles

### Web App (Next.js)
- Multi-stage build (deps → builder → runner)
- Standalone output for optimized production
- Runs as non-root user (nextjs:nodejs)
- Image size: ~150MB

### Scraper (Python)
- Python 3.11 slim base
- Includes PostgreSQL client tools
- gcc for compiling psycopg2

## Troubleshooting

### Network not found error
```
Error response from daemon: failed to set up container networking: network ... not found
```

This happens when Docker has orphaned network references. Fix:
```bash
docker-compose down
docker rm -f wandering-inn-scraper wandering-inn-web  # Remove containers
docker container prune -f                              # Clean up stopped containers
docker network prune -f                                # Remove unused networks
docker-compose --profile scraper up -d                 # Start fresh
```

### Database "wandering_inn" does not exist errors
**Fixed!** The healthcheck was using the wrong database name. The fix has been applied:
- Changed healthcheck from: `pg_isready -U wandering_inn`
- To: `pg_isready -U wandering_inn -d wandering_inn_tracker`

If you see this error, make sure you have the latest docker-compose.yml.

### Web app can't connect to database
1. Check logs: `docker-compose logs web`
2. Verify postgres is healthy: `docker-compose ps`
3. Test connection: `curl http://localhost:3000/api/health`

### Scraper fails to connect
```bash
docker-compose --profile scraper run --rm scraper python -m src.main check-db
```

### Rebuild containers after code changes
```bash
docker-compose build
docker-compose up -d
```

### Clean restart (removes data)
```bash
docker-compose down -v
docker-compose up -d
```

## Development vs Production

### Local Development (Current Setup)
- Uses `npm install` (no package-lock.json)
- Environment variables in docker-compose.yml
- Database data persists in Docker volume

### Production Recommendations
1. Generate package-lock.json: `cd web && npm install`
2. Use environment variable files (not hardcoded)
3. Enable multi-AZ for RDS (if using AWS)
4. Use secrets management (AWS Secrets Manager, etc.)
5. Add HTTPS via reverse proxy (nginx, Caddy)
6. Set up monitoring and logging
7. Configure backup strategy for PostgreSQL

## Next Steps

1. **Generate package-lock.json**:
   ```bash
   cd web
   npm install  # Creates package-lock.json
   ```

2. **Add initial data**:
   - Run scraper to populate chapters
   - Manually assign characters in web UI

3. **Deploy to AWS** (see CLAUDE.md for AWS architecture)

## Testing

### Test Web App
```bash
# Health check
curl http://localhost:3000/api/health

# Home page
curl http://localhost:3000/

# Characters API
curl http://localhost:3000/api/characters

# Chapters API
curl http://localhost:3000/api/chapters
```

### Test Scraper
```bash
# Check database
docker-compose --profile scraper run --rm scraper python -m src.main check-db

# Test on chapter 1
docker-compose --profile scraper run --rm scraper python -m src.main test 1

# Scrape 5 chapters
docker-compose --profile scraper run --rm scraper python -m src.main scrape --max 5
```

## Summary

All three components are now fully containerized and working:
- ✅ PostgreSQL database with auto-migrations
- ✅ Python scraper with database connectivity
- ✅ Next.js web app with API routes
- ✅ Docker Compose orchestration
- ✅ Production-ready Dockerfiles

The Tanstack Start version has been backed up to `web-tanstack-backup/` for reference.
