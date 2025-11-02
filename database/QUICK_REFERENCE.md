# Database Quick Reference

## Most Common Commands

### Start/Stop Database

```bash
# Start PostgreSQL
docker-compose up -d postgres

# Stop PostgreSQL (keeps data)
docker-compose down

# Stop and delete all data (WARNING!)
docker-compose down -v
```

### Run Migrations

```bash
cd database

# Windows PowerShell:
.\migrate.ps1            # Apply pending migrations
.\migrate.ps1 status     # Show migration status
.\migrate.ps1 reset      # Reset database (DANGEROUS!)

# Mac/Linux/Git Bash:
./migrate.sh            # Apply pending migrations
./migrate.sh status     # Show migration status
./migrate.sh reset      # Reset database (DANGEROUS!)
```

### Connect to Database

```bash
# Set password first
export PGPASSWORD=dev_password_change_in_production  # Mac/Linux
$env:PGPASSWORD = "dev_password_change_in_production"  # PowerShell

# Connect
psql -h localhost -p 5432 -U wandering_inn -d wandering_inn_tracker
```

### Useful psql Commands

```sql
\dt              -- List all tables
\dv              -- List all views
\df              -- List all functions
\d table_name    -- Describe a table
\q               -- Quit
```

## Quick Queries

```sql
-- See all characters
SELECT * FROM characters;

-- See unassigned events (need manual review)
SELECT * FROM unassigned_events LIMIT 10;

-- Get character's abilities at chapter 100
SELECT * FROM get_character_abilities_at_chapter(1, 100);

-- Get character's level at chapter 100
SELECT get_character_level_at_chapter(1, 'Innkeeper', 100);

-- Count events by type
SELECT event_type, COUNT(*)
FROM raw_events
GROUP BY event_type;

-- Find characters with multiple classes
SELECT c.name, COUNT(DISTINCT cc.class_name) as class_count
FROM characters c
JOIN character_classes cc ON c.id = cc.character_id
GROUP BY c.name
HAVING COUNT(DISTINCT cc.class_name) > 1;
```

## View Logs

```bash
# Follow logs in real-time
docker-compose logs -f postgres

# Last 50 lines
docker-compose logs --tail 50 postgres
```

## Backup & Restore

```bash
# Backup
docker exec wandering-inn-db pg_dump -U wandering_inn wandering_inn_tracker > backup.sql

# Restore
cat backup.sql | docker exec -i wandering-inn-db psql -U wandering_inn -d wandering_inn_tracker
```

## Connection String for Apps

```python
# Python (psycopg2)
"postgresql://wandering_inn:dev_password_change_in_production@localhost:5432/wandering_inn_tracker"

# Python (SQLAlchemy)
"postgresql+psycopg2://wandering_inn:dev_password_change_in_production@localhost:5432/wandering_inn_tracker"

# Node.js (pg)
{
  host: 'localhost',
  port: 5432,
  database: 'wandering_inn_tracker',
  user: 'wandering_inn',
  password: 'dev_password_change_in_production'
}
```

## Table Relationships

```
chapters
  ├── raw_events (one-to-many)
  ├── character_classes (one-to-many)
  ├── character_levels (one-to-many)
  └── character_abilities (one-to-many)

characters
  ├── character_classes (one-to-many)
  └── character_abilities (one-to-many)

character_classes
  └── character_levels (one-to-many)

abilities
  └── character_abilities (one-to-many)
```
