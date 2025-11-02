# Docker Usage Guide - Quick Reference

## Service Profiles

The docker-compose setup uses profiles to control which services start:

| Profile | Services Started | Use Case |
|---------|-----------------|----------|
| (none) | `postgres` only | Run migrations, database access, **run scraper commands** |
| `--profile web` | `postgres` + `web` | Normal development with web UI |

**Note:** The scraper is **not meant to run as a persistent service**. Use `docker-compose run` commands to execute specific scraper tasks (see below).

## Common Commands

### Database Only
```bash
# Start database
docker-compose up -d

# Run migrations
cd database
./migrate.sh up

# Access PostgreSQL
docker exec -it wandering-inn-db psql -U wandering_inn -d wandering_inn_tracker
```

### Using the Scraper

**Important:** The scraper should be run via `docker-compose run` commands, not as a persistent service.

```bash
# 1. Start database
docker-compose up -d

# 2. Check scraper can connect
docker-compose run --rm scraper python -m src.main check-db

# 3. Build table of contents (MUST DO THIS FIRST!)
docker-compose run --rm scraper python -m src.main build-toc

# 4. Verify ToC was built
docker-compose run --rm scraper python -m src.main show-toc

# 5. Scrape chapters
docker-compose run --rm scraper python -m src.main scrape --max 5

# Stop database when done
docker-compose down
```

### Database + Web App
```bash
# Start database and web app
docker-compose --profile web up -d

# View web app
curl http://localhost:3000/api/health

# Check logs
docker-compose logs web

# Stop everything
docker-compose down
```

### Full Stack (Database + Web App)
```bash
# Start database and web app
docker-compose --profile web up -d

# Check services
docker-compose ps

# View logs
docker-compose logs -f

# Run scraper commands while web app is running
docker-compose run --rm scraper python -m src.main check-db

# Stop everything
docker-compose down
```

## Scraper Commands

### One-off Commands (No Need for `--profile scraper`)
When using `docker-compose run`, profiles are not required:

```bash
# Check database connection
docker-compose run --rm scraper python -m src.main check-db

# Build table of contents from website
docker-compose run --rm scraper python -m src.main build-toc

# View ToC statistics
docker-compose run --rm scraper python -m src.main show-toc

# Test scraper on a single chapter
docker-compose run --rm scraper python -m src.main test 1

# Fetch and display a chapter
docker-compose run --rm scraper python -m src.main fetch 1

# Scrape chapters (with limit)
docker-compose run --rm scraper python -m src.main scrape --max 5

# Scrape with verbose logging
docker-compose run --rm scraper python -m src.main -v scrape --max 5
```

### Long-Running Scraper
If you want to run a long scraping job in the background:

```bash
# Start database
docker-compose up -d

# Run scraper in background (not detached from compose, but runs in background)
docker-compose run -d scraper python -m src.main scrape

# Get the container ID
docker ps | grep scraper

# Monitor progress
docker logs -f <container-id>

# Or check the database for progress
docker-compose run --rm scraper python -m src.main show-toc
```

## Database Operations

### Migrations
```bash
# Start database
docker-compose up -d

# Run migrations (from host)
cd database
DB_PORT=54320 ./migrate.sh up

# Check migration status
DB_PORT=54320 ./migrate.sh status
```

### Direct Database Access
```bash
# Via Docker
docker exec -it wandering-inn-db psql -U wandering_inn -d wandering_inn_tracker

# Via host (port 54320)
psql -h localhost -p 54320 -U wandering_inn -d wandering_inn_tracker

# Run SQL file
docker exec -i wandering-inn-db psql -U wandering_inn -d wandering_inn_tracker < query.sql
```

### Database Backup/Restore
```bash
# Backup
docker exec wandering-inn-db pg_dump -U wandering_inn wandering_inn_tracker > backup.sql

# Restore
docker exec -i wandering-inn-db psql -U wandering_inn -d wandering_inn_tracker < backup.sql
```

## Troubleshooting

### Check What's Running
```bash
docker-compose ps
```

### View Logs
```bash
# All logs
docker-compose logs

# Specific service
docker-compose logs postgres
docker-compose logs scraper
docker-compose --profile web logs web

# Follow logs (real-time)
docker-compose logs -f scraper
```

### Rebuild After Code Changes
```bash
# Rebuild specific service
docker-compose build scraper
docker-compose build web

# Rebuild and restart
docker-compose up -d --build scraper
```

### Clean Start (Removes Data!)
```bash
# Stop and remove volumes
docker-compose down -v

# Start fresh
docker-compose --profile web up -d
```

### Check Service Health
```bash
# Database health
docker-compose exec postgres pg_isready -U wandering_inn -d wandering_inn_tracker

# Web app health
curl http://localhost:3000/api/health
```

## Environment Variables

All services use these database connection variables:
- `DB_HOST=postgres` (container name)
- `DB_PORT=5432` (internal port)
- `DB_NAME=wandering_inn_tracker`
- `DB_USER=wandering_inn`
- `DB_PASSWORD=dev_password_change_in_production`

For local development (outside Docker), use port `54320`:
```bash
export DB_PORT=54320
export DB_HOST=localhost
```

## Quick Reference Card

```bash
# Database only
docker-compose up -d

# Database + Web
docker-compose --profile web up -d

# Run scraper commands (database must be running)
docker-compose run --rm scraper python -m src.main build-toc
docker-compose run --rm scraper python -m src.main scrape --max 5

# Stop all
docker-compose down

# Rebuild
docker-compose build <service>

# View logs
docker-compose logs <service>
```
