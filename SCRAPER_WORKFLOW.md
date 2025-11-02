# Scraper Workflow Guide

## Important: Two-Step Process

The scraper uses a **two-step workflow** that must be followed in order:

1. **Build Table of Contents** (`build-toc`) - Scrapes the ToC page to get all chapter URLs
2. **Scrape Chapters** (`scrape`) - Uses those URLs to scrape individual chapters

**DO NOT skip step 1!** The `scrape` command requires chapter URLs to be in the database first.

## Complete Workflow

### Step 1: Start Database
```bash
docker-compose up -d
```

This starts only PostgreSQL (no web app, no scraper service).

### Step 2: Build Table of Contents
```bash
docker-compose run --rm scraper python -m src.main build-toc
```

This will:
- Scrape The Wandering Inn's table of contents page
- Extract all chapter URLs
- Store them in the `chapters` table
- Show progress as it works

**Expected output:**
```
INFO     Fetching table of contents from https://wanderinginn.com/...
INFO     Found X chapters
INFO     Saving chapters to database...
INFO     ✓ Saved X chapters
```

### Step 3: Verify ToC Was Built
```bash
docker-compose run --rm scraper python -m src.main show-toc
```

**Expected output:**
```
=== Table of Contents Statistics ===
Total chapters in database: X
Scraped chapters: 0
Unscraped chapters: X
```

### Step 4: Scrape Chapters
```bash
# Scrape just a few chapters for testing
docker-compose run --rm scraper python -m src.main scrape --max 5

# Or scrape all chapters (will take hours!)
docker-compose run --rm scraper python -m src.main scrape
```

This will:
- Fetch each chapter's content
- Parse progression events (classes, levels, skills, spells)
- Store events in the `raw_events` table
- Mark chapters as scraped

**Expected output:**
```
INFO     Starting chapter scraping (max chapters: 5)
INFO     Processing Chapter 1.00...
INFO     Found 10 events in chapter 1
INFO     Saved 10 events to database
INFO     ✓ Chapter 1 scraped successfully
...
```

### Step 5: Check Progress
```bash
docker-compose run --rm scraper python -m src.main show-toc
```

Now you should see some scraped chapters:
```
Total chapters in database: X
Scraped chapters: 5
Unscraped chapters: X-5
```

### Step 6: Stop Database
```bash
docker-compose down
```

## Common Scraper Commands

### Test Single Chapter
```bash
# Test scraper on chapter 1 (doesn't save to DB)
docker-compose run --rm scraper python -m src.main test 1
```

### Fetch Chapter Content
```bash
# Fetch and display chapter content
docker-compose run --rm scraper python -m src.main fetch 1
```

### Verbose Logging
```bash
# Run with verbose output for debugging
docker-compose run --rm scraper python -m src.main -v scrape --max 5
```

### Check Database Connection
```bash
docker-compose run --rm scraper python -m src.main check-db
```

## What NOT To Do

❌ **Don't run scraper as a persistent service:**
```bash
# WRONG - this doesn't work anymore
docker-compose --profile scraper up -d
```

The scraper profile has been removed because the scraper is designed for one-off commands, not as a background service.

✅ **Instead, use `docker-compose run` commands:**
```bash
# CORRECT
docker-compose up -d  # Start database
docker-compose run --rm scraper python -m src.main build-toc
docker-compose run --rm scraper python -m src.main scrape --max 5
```

## Long-Running Scrape Jobs

If you want to scrape hundreds of chapters in the background:

```bash
# Start database
docker-compose up -d

# Build ToC first
docker-compose run --rm scraper python -m src.main build-toc

# Run scraper in background
docker-compose run -d scraper python -m src.main scrape

# Get container ID
docker ps

# Monitor logs
docker logs -f <container-id>

# Check progress periodically
docker-compose run --rm scraper python -m src.main show-toc
```

## Troubleshooting

### Error: "No chapters found in database"
You forgot step 2! Run `build-toc` first:
```bash
docker-compose run --rm scraper python -m src.main build-toc
```

### Error: "Chapter URL is invalid"
The ToC may have changed. Rebuild it:
```bash
docker-compose run --rm scraper python -m src.main build-toc
```

### Scraper is slow / timing out
The scraper has a 2-second delay between requests (respectful scraping). This is normal.
For thousands of chapters, expect it to take several hours.

### Check what's in the database
```bash
# Access PostgreSQL
docker exec -it wandering-inn-db psql -U wandering_inn -d wandering_inn_tracker

# Check chapters
SELECT chapter_number, title, scraped_at FROM chapters LIMIT 10;

# Check raw events
SELECT COUNT(*) FROM raw_events;
```

## Summary

**Always follow this order:**
1. Start database: `docker-compose up -d`
2. Build ToC: `docker-compose run --rm scraper python -m src.main build-toc`
3. Verify: `docker-compose run --rm scraper python -m src.main show-toc`
4. Scrape: `docker-compose run --rm scraper python -m src.main scrape --max 5`
5. Stop: `docker-compose down`

**Remember:** The scraper needs chapter URLs before it can scrape content!
