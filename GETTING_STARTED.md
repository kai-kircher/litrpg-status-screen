# Getting Started with Wandering Inn Tracker

Complete walkthrough from setup to working application.

## Prerequisites

Install these on your system:
- **Docker & Docker Compose** - For PostgreSQL
- **Node.js 20+** - For web application
- **Python 3.11+** - For scraper

## Quick Start (15 minutes)

### Step 1: Clone Repository

```bash
cd C:\Users\tamak\repos\wandering-inn-tracker
```

### Step 2: Start Database (2 minutes)

```bash
# Copy environment file
cp .env.example .env

# Start PostgreSQL
docker-compose up -d postgres

# Run migrations
cd database
.\migrate.ps1  # Windows PowerShell
# OR
./migrate.sh   # Mac/Linux/Git Bash

# Verify database
cd ..
```

### Step 3: Scrape Data (5-10 minutes)

```bash
cd scraper

# Setup Python environment
python -m venv venv
venv\Scripts\activate  # Windows
# OR
source venv/bin/activate  # Mac/Linux

pip install -r requirements.txt

# Copy environment
cp .env.example .env

# Build chapter list from Table of Contents
python -m src.main build-toc

# Test on one chapter
python -m src.main test 1

# Scrape first 10 chapters
python -m src.main scrape --max 10

cd ..
```

### Step 4: Start Web App (2 minutes)

```bash
cd web

# Install dependencies
npm install

# Copy environment
cp .env.local.example .env.local

# Start development server
npm run dev
```

Visit http://localhost:3000

## Full Walkthrough

### Database Setup

**1. Start PostgreSQL:**
```bash
docker-compose up -d postgres
```

**2. Run migrations:**
```bash
cd database
.\migrate.ps1  # Creates tables, views, functions
```

**3. Verify:**
```bash
.\migrate.ps1 status
```

See `DATABASE_SETUP.md` for detailed instructions.

### Scraper Usage

**1. Build chapter list (required first!):**
```bash
cd scraper
python -m src.main build-toc
```

This fetches https://wanderinginn.com/table-of-contents/ and saves all chapter URLs.

**2. View chapters:**
```bash
python -m src.main show-toc
```

**3. Test scraper:**
```bash
python -m src.main test 1
```

**4. Scrape data:**
```bash
# Scrape first 10 chapters (fast, for testing)
python -m src.main scrape --max 10

# Scrape all chapters (takes hours!)
python -m src.main scrape
```

See `scraper/README.md` and `scraper/SCRAPING_WORKFLOW.md` for details.

### Web App Usage

**1. Install dependencies:**
```bash
cd web
npm install
```

**2. Configure database:**
```bash
cp .env.local.example .env.local
# Default DATABASE_URL should work if you used docker-compose
```

**3. Start development server:**
```bash
npm run dev
```

**4. Access application:**
Open http://localhost:3000

**5. Use the status screen:**
- Select a character from dropdown
- Select max chapter (spoiler filter)
- View progression timeline
- Use search to filter results

See `web/README.md` for details.

## Complete Development Workflow

```bash
# Terminal 1: Database
docker-compose up postgres

# Terminal 2: Scraper (one-time or periodic)
cd scraper
venv\Scripts\activate
python -m src.main scrape --max 10

# Terminal 3: Web App
cd web
npm run dev
```

## Verifying Everything Works

### 1. Database Check

```bash
cd database
.\migrate.ps1 status
```

Expected: Shows `001_initial_schema.sql` as applied.

### 2. Scraper Check

```bash
cd scraper
python -m src.main check-db
python -m src.main show-toc
```

Expected: Database connection successful, chapters listed.

### 3. Web App Check

Visit http://localhost:3000

Expected: See "LitRPG Status Screen" header with dropdowns.

### 4. End-to-End Test

1. Scrape a few chapters:
   ```bash
   cd scraper
   python -m src.main scrape --max 5
   ```

2. Refresh web app
3. Select "Erin Solstice" (or first character)
4. See progression events appear

## Project Structure

```
wandering-inn-tracker/
├── database/
│   ├── migrations/           # SQL migrations
│   ├── migrate.ps1          # Windows migration runner
│   └── migrate.sh           # Mac/Linux migration runner
├── scraper/
│   ├── src/
│   │   ├── scrapers/        # Web scraping
│   │   ├── parsers/         # Event parsing
│   │   ├── db/              # Database operations
│   │   └── main.py          # CLI interface
│   └── requirements.txt
├── web/
│   ├── app/
│   │   ├── routes/          # Pages and API routes
│   │   ├── components/      # React components
│   │   └── lib/             # Database and utilities
│   └── package.json
├── docker-compose.yml       # PostgreSQL setup
└── .env                     # Database credentials
```

## Common Issues

### "Database connection failed"

Check if PostgreSQL is running:
```bash
docker-compose ps
```

If not running:
```bash
docker-compose up -d postgres
```

### "No characters found"

You need to scrape data first:
```bash
cd scraper
python -m src.main build-toc
python -m src.main scrape --max 5
```

### "Port 5432 already in use"

Another PostgreSQL is running. Either stop it or change the port in `docker-compose.yml`.

### "Port 3000 already in use"

Change port in `web/.env.local`:
```env
PORT=3001
```

### Web app shows "Loading..." forever

Check browser console for errors. Likely database connection issue.

Test API directly:
```bash
curl http://localhost:3000/api/characters
```

## Next Steps

### Add More Data

Scrape more chapters:
```bash
cd scraper
python -m src.main scrape --max 50
```

### Manual Assignment (Future)

Once you have raw events, you'll need to manually assign them to characters in the admin UI (coming in Phase 2).

For now, the scraper creates `raw_events` which need manual review.

### Deploy to Production

See `CLAUDE.md` for AWS deployment options.

## Getting Help

- **Database**: See `DATABASE_SETUP.md` and `database/QUICK_REFERENCE.md`
- **Scraper**: See `scraper/README.md` and `scraper/SCRAPING_WORKFLOW.md`
- **Web App**: See `web/README.md` and `web/PROJECT_PLAN.md`
- **Errors**: See `scraper/ERROR_HANDLING.md`

## Development Tips

### Fast Iteration

For quick testing without full scrape:

```sql
-- Manually insert test data
INSERT INTO characters (name) VALUES ('Test Character');

INSERT INTO character_classes (character_id, class_name, chapter_id)
VALUES (1, 'Warrior', 1);

INSERT INTO character_levels (character_class_id, level, chapter_id)
VALUES (1, 5, 1);
```

### Reset Database

```bash
cd database
.\migrate.ps1 reset
```

**Warning**: This deletes all data!

### Monitor Scraper

Run with verbose logging:
```bash
python -m src.main -v scrape --max 10
```

### Hot Reload

The web app has hot module reloading. Edit components and see changes instantly.

## Success!

If you can:
1. ✅ Start PostgreSQL
2. ✅ Run migrations
3. ✅ Scrape a few chapters
4. ✅ View character progression in web UI

You're all set! Happy tracking! 🎉
