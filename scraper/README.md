# Wandering Inn Tracker - Web Scraper

Python scraper for extracting character progression data from The Wandering Inn web serial.

## Features

- Scrapes chapters from The Wandering Inn website
- Extracts progression events using regex patterns:
  - Class obtained: `[Innkeeper class obtained!]`
  - Level up: `[Innkeeper level 5!]`
  - Skill obtained: `[Skill - Inn's Aura obtained!]`
  - Spell obtained: `[Spell - Fireball obtained!]`
- Stores chapter content and raw events in PostgreSQL
- Rate limiting to respect website resources
- Resume capability (continues from last scraped chapter)
- Idempotent (safe to re-run)

## Setup

### 1. Install Dependencies

```bash
cd scraper
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Test Database Connection

```bash
python -m src.main check-db
```

## Usage

### Two-Step Scraping Process

The Wandering Inn has complex chapter URLs (e.g., `/2016/07/27/1-00/`), so we use a two-step process:

**Step 1: Build Chapter List from Table of Contents**

```bash
python -m src.main build-toc
```

This fetches https://wanderinginn.com/table-of-contents/ and extracts all chapter URLs in order.

**Step 2: Scrape Chapter Content**

```bash
# Scrape all chapters (resumes from last scraped)
python -m src.main scrape

# Scrape first 5 chapters
python -m src.main scrape --max 5

# Scrape specific range
python -m src.main scrape --start 1 --end 10
```

### View Chapter List

See what chapters are in the database:

```bash
python -m src.main show-toc
```

### Test Scraper

Test on a single chapter without saving to database:

```bash
python -m src.main test 1
```

### Fetch Single Chapter

Fetch and display a chapter:

```bash
python -m src.main fetch 1
```

### Parse Text File

Test event parsing on a text file:

```bash
python -m src.main parse chapter.txt
```

### All Commands

```bash
python -m src.main --help
```

Commands:
- `build-toc` - Build chapter list from Table of Contents (run this first!)
- `show-toc` - Show chapter statistics from database
- `scrape` - Scrape chapters from The Wandering Inn
- `test` - Test scraper on a specific chapter
- `check-db` - Check database connection
- `fetch` - Fetch and display a single chapter
- `parse` - Parse events from a text file
- `version` - Show version information

## Configuration

Edit `.env` or `src/config.py`:

- `BASE_URL` - Base URL for The Wandering Inn (default: https://wanderinginn.com)
- `REQUEST_DELAY` - Seconds between requests (default: 2)
- `START_CHAPTER` - Default starting chapter (default: 1)
- `MAX_CHAPTERS` - Max chapters per run, 0=unlimited (default: 0)

Database settings (should match your PostgreSQL setup):
- `DB_HOST` - Database host (default: localhost)
- `DB_PORT` - Database port (default: 5432)
- `DB_NAME` - Database name (default: wandering_inn_tracker)
- `DB_USER` - Database user (default: wandering_inn)
- `DB_PASSWORD` - Database password

## Architecture

```
src/
├── config.py           # Configuration management
├── scraper.py          # Main orchestration logic
├── main.py             # CLI interface
├── db/
│   ├── connection.py   # Database connection pool
│   └── operations.py   # Database CRUD operations
├── parsers/
│   └── event_parser.py # Regex-based event extraction
└── scrapers/
    └── chapter_scraper.py  # Web scraping logic
```

## Complete Workflow

```bash
# 1. Setup
cd scraper
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 2. Check database
python -m src.main check-db

# 3. Build chapter list from ToC (IMPORTANT: Do this first!)
python -m src.main build-toc

# 4. Verify chapters were saved
python -m src.main show-toc

# 5. Test on one chapter
python -m src.main test 1

# 6. Scrape first 10 chapters
python -m src.main scrape --max 10

# 7. Scrape everything
python -m src.main scrape
```

## Important Notes

### Website Structure

The scraper contains placeholder selectors for HTML elements. You may need to:

1. Inspect The Wandering Inn's HTML structure if scraping fails
2. Update CSS selectors in `src/scrapers/chapter_scraper.py`:
   - `_extract_chapter_data()` - Title, content, date selectors
3. Update CSS selectors in `src/scrapers/toc_scraper.py`:
   - `_extract_chapters()` - ToC page structure

### Rate Limiting

The scraper respects rate limits (2 seconds between requests by default). The Wandering Inn has thousands of chapters, so:

- Initial scrape will take **hours**
- Run in a screen/tmux session or background process
- Scraper is resumable - can stop and restart anytime

### Idempotency

The scraper checks if chapters exist before scraping. If a chapter is already in the database, it's skipped. This means:

- Safe to re-run the scraper
- Can stop and resume without duplicates
- Use `--no-resume` to force re-scraping

## Development

### Adding New Event Patterns

Edit `src/parsers/event_parser.py` and add patterns to the `PATTERNS` dictionary:

```python
PATTERNS = {
    'skill_obtained': [
        r'\[Skill - ([^\]]+) obtained!?\]',
        r'\[Skill - ([^\]]+) learned!?\]',
        # Add new pattern here
    ],
}
```

### Testing Parsers

Create a test file with sample text and run:

```bash
python -m src.main parse test_chapter.txt
```

### Verbose Logging

Enable debug logging:

```bash
python -m src.main -v scrape
```

## Troubleshooting

### Connection Refused

Database not running. Start PostgreSQL:

```bash
docker-compose up -d postgres
```

### No Events Found

Check HTML selectors in `chapter_scraper.py`. The website structure may have changed.

### HTTP 404 Errors

Chapter doesn't exist. The scraper will stop after 5 consecutive 404s.

### Rate Limited

Increase `REQUEST_DELAY` in `.env` if you're getting 429 errors.

## Next Steps

After scraping chapters:

1. Review unassigned events in the web UI
2. Manually assign events to characters
3. Build character profiles and timelines
