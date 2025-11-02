# Database Setup Guide

This guide walks you through setting up the PostgreSQL database for the Wandering Inn Tracker from scratch.

## Prerequisites

Install these tools on your system:

1. **Docker & Docker Compose** - For running PostgreSQL in a container
   - Download from: https://www.docker.com/products/docker-desktop
   - Verify installation: `docker --version` and `docker-compose --version`

2. **PostgreSQL Client Tools** (psql) - For running migrations
   - **Windows**: Download from https://www.postgresql.org/download/windows/
     - Or use WSL2 with Linux instructions
   - **macOS**: `brew install postgresql` (installs client tools only)
   - **Linux**: `sudo apt-get install postgresql-client`
   - Verify installation: `psql --version`

## Quick Start (TL;DR)

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Start PostgreSQL
docker-compose up -d postgres

# 3. Run migrations
# On Windows PowerShell:
cd database
.\migrate.ps1

# On Mac/Linux or Git Bash:
cd database
chmod +x migrate.sh
./migrate.sh
```

That's it! Your database is ready.

---

## Detailed Setup Instructions

### Step 1: Configure Environment Variables

Create a `.env` file from the template:

```bash
cp .env.example .env
```

The default values work for local development:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=wandering_inn_tracker
DB_USER=wandering_inn
DB_PASSWORD=dev_password_change_in_production
```

**Note**: The `.env` file is gitignored. Never commit it with real passwords.

### Step 2: Start PostgreSQL with Docker

Start the PostgreSQL container:

```bash
docker-compose up -d postgres
```

This command:
- Downloads the PostgreSQL 16 Alpine image (first time only)
- Creates a container named `wandering-inn-db`
- Exposes PostgreSQL on `localhost:5432`
- Creates a persistent volume for data storage
- Sets up the database with credentials from docker-compose.yml

**Verify it's running:**

```bash
docker-compose ps
```

You should see the `wandering-inn-db` container with status "Up".

**View logs:**

```bash
docker-compose logs postgres
```

### Step 3: Run Database Migrations

Migrations apply the database schema (tables, indexes, views, functions).

#### On Windows (PowerShell):

```powershell
cd database
.\migrate.ps1
```

#### On Mac/Linux/Git Bash:

```bash
cd database
chmod +x migrate.sh  # Make script executable (first time only)
./migrate.sh
```

**What happens during migration:**

1. Creates `schema_migrations` table (tracks applied migrations)
2. Applies `001_initial_schema.sql`:
   - Creates all tables (chapters, characters, raw_events, etc.)
   - Creates indexes for performance
   - Creates views (unassigned_events, character_current_state, etc.)
   - Creates utility functions (get_character_abilities_at_chapter, etc.)

**Expected output:**

```
Checking database connection...
Database connection successful
Initializing migration tracking...
Migration tracking initialized
Applying migrations...
Applying: 001_initial_schema.sql
✓ Applied: 001_initial_schema.sql
All migrations applied successfully
```

### Step 4: Verify the Setup

#### Check migration status:

```bash
# Windows PowerShell:
.\migrate.ps1 status

# Mac/Linux:
./migrate.sh status
```

#### Connect to the database directly:

```bash
# Set password environment variable
export PGPASSWORD=dev_password_change_in_production  # Mac/Linux
$env:PGPASSWORD = "dev_password_change_in_production"  # PowerShell

# Connect
psql -h localhost -p 5432 -U wandering_inn -d wandering_inn_tracker
```

#### Run a test query:

```sql
-- List all tables
\dt

-- Check if views exist
\dv

-- Check if functions exist
\df

-- Query the unassigned events view (should be empty)
SELECT * FROM unassigned_events;

-- Exit
\q
```

You should see 7 tables:
- chapters
- characters
- raw_events
- character_classes
- character_levels
- abilities
- character_abilities

---

## Common Tasks

### View Database Logs

```bash
docker-compose logs -f postgres
```

### Stop the Database

```bash
docker-compose down
```

**Note**: This stops the container but keeps the data (in the Docker volume).

### Stop and Delete All Data

```bash
docker-compose down -v
```

**Warning**: This deletes the Docker volume. All data will be lost.

### Reset Database (Drop and Recreate)

If you need to start fresh:

```bash
# Windows PowerShell:
.\migrate.ps1 reset

# Mac/Linux:
./migrate.sh reset
```

This will:
1. Ask for confirmation (type "yes")
2. Drop the database
3. Recreate it
4. Reapply all migrations

### Access Database via GUI (Optional)

Start pgAdmin (web-based PostgreSQL GUI):

```bash
docker-compose --profile tools up -d pgadmin
```

Access it at: http://localhost:5050
- Email: `admin@wandering-inn.local`
- Password: `admin`

To connect to the database in pgAdmin:
1. Right-click "Servers" → "Register" → "Server"
2. General tab: Name = "Local Wandering Inn"
3. Connection tab:
   - Host: `postgres` (Docker service name)
   - Port: `5432`
   - Database: `wandering_inn_tracker`
   - Username: `wandering_inn`
   - Password: `dev_password_change_in_production`

---

## Migration System

### How Migrations Work

Migrations are numbered SQL files in `database/migrations/`:

```
000_create_migrations_table.sql  - Creates tracking table
001_initial_schema.sql           - Initial schema
002_add_some_feature.sql         - Future migrations...
```

The migration script:
1. Checks which migrations have been applied
2. Runs pending migrations in order
3. Records each successful migration in `schema_migrations` table

### Adding New Migrations

Create a new file with the next number:

```bash
# Example: Add a new feature
database/migrations/002_add_character_aliases_search.sql
```

Write your SQL:

```sql
-- Add full-text search for character aliases
CREATE INDEX idx_characters_aliases_gin ON characters USING gin(aliases);
```

Run the migration:

```bash
./migrate.sh  # or .\migrate.ps1 on Windows
```

### Migration Best Practices

1. **Never modify applied migrations** - Create a new migration instead
2. **One feature per migration** - Easier to debug and rollback
3. **Test migrations** - Run them on a fresh database before committing
4. **Use transactions** - Wrap migrations in `BEGIN`/`COMMIT` if needed
5. **Document complex changes** - Add comments explaining "why"

---

## Troubleshooting

### "psql: command not found"

You need to install PostgreSQL client tools:
- **Windows**: https://www.postgresql.org/download/windows/
- **macOS**: `brew install postgresql`
- **Linux**: `sudo apt-get install postgresql-client`

### "Connection refused" or "Database does not exist"

1. Check if Docker container is running:
   ```bash
   docker-compose ps
   ```

2. If not running, start it:
   ```bash
   docker-compose up -d postgres
   ```

3. Wait 5-10 seconds for PostgreSQL to initialize

4. Check logs for errors:
   ```bash
   docker-compose logs postgres
   ```

### "Port 5432 already in use"

Another PostgreSQL instance is running on your machine.

**Option 1**: Stop the other PostgreSQL:
```bash
# Windows: Stop PostgreSQL service in Services
# Mac: brew services stop postgresql
# Linux: sudo systemctl stop postgresql
```

**Option 2**: Change the port in `docker-compose.yml`:
```yaml
ports:
  - "5433:5432"  # Use 5433 on host instead
```

Then update `.env`:
```env
DB_PORT=5433
```

### Migration fails with "relation already exists"

The migration was partially applied. Reset the database:

```bash
./migrate.sh reset
```

### Can't connect from Python/Node.js app

Make sure your connection string matches `.env`:

```python
# Python example
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="wandering_inn_tracker",
    user="wandering_inn",
    password="dev_password_change_in_production"
)
```

---

## Production Deployment

For AWS deployment, you'll use Amazon RDS instead of Docker. The migration scripts work the same way:

1. Create RDS PostgreSQL instance
2. Update `.env` with RDS endpoint:
   ```env
   DB_HOST=your-rds-instance.abc123.us-east-1.rds.amazonaws.com
   DB_PORT=5432
   DB_NAME=wandering_inn_tracker
   DB_USER=postgres
   DB_PASSWORD=your-secure-password
   ```
3. Run migrations from your local machine:
   ```bash
   ./migrate.sh
   ```
4. Or run migrations from EC2/ECS during deployment

**Security for production**:
- Use strong passwords
- Restrict RDS security group to your app's IPs only
- Use SSL/TLS for connections
- Enable RDS automated backups
- Never commit `.env` file

---

## Summary

You've now:
- ✅ Set up PostgreSQL in Docker
- ✅ Created the database schema with migrations
- ✅ Verified the setup with test queries
- ✅ Learned how to manage the database

**Next steps**:
- Build the Python scraper to populate `chapters` and `raw_events`
- Build the Tanstack Start web app for manual assignment

The database is ready! 🎉
