# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Wandering Inn Tracker scrapes and tracks character progression data from The Wandering Inn web serial. It extracts classes, levels, skills, and spells as characters progress, allowing spoiler-free lookups at specific story points.

## Tech Stack

- **Scraper**: Python 3 with BeautifulSoup, lxml
- **Web**: Next.js 15, TypeScript, React 19, Tailwind CSS
- **Database**: PostgreSQL 16
- **Deployment**: Docker, Docker Compose

## Local Development Setup

**Database**:
```bash
docker-compose up -d postgres           # Start PostgreSQL (port 54320)
cd database && ./migrate.sh             # Run migrations (Mac/Linux)
cd database && .\migrate.ps1            # Run migrations (Windows)
```

**Scraper** (Python):
```bash
cd scraper
python -m venv venv
venv\Scripts\activate                   # Windows
source venv/bin/activate                # Mac/Linux
pip install -r requirements.txt
```

**Web Application**:
```bash
cd web
npm install
npm run dev                             # http://localhost:3000
npm run build                           # Production build
npm run lint                            # ESLint
```

## Scraper Commands

```bash
python -m src.main check-db             # Test database connection
python -m src.main build-toc            # Build chapter list from ToC (run first)
python -m src.main show-toc             # View chapter stats
python -m src.main scrape               # Scrape chapters (uses ToC data)
python -m src.main scrape --max 5       # Scrape max 5 chapters
python -m src.main test 1               # Test on chapter 1 (no DB save)
python -m src.main fetch 1              # Fetch and display chapter 1
python -m src.main parse file.txt       # Parse events from file
python -m src.main -v scrape            # Verbose logging
```

**AI Processing Commands** (requires ANTHROPIC_API_KEY):
```bash
python -m src.main extract-characters --chapter 1    # Extract characters from chapter
python -m src.main attribute-events --chapter 1      # Attribute events to characters
python -m src.main process-ai --start 1 --end 10     # Full AI processing
python -m src.main ai-stats                          # Show AI usage statistics
python -m src.main review-queue                      # Show events needing review
```

## Docker Compose Profiles

```bash
docker-compose up -d postgres           # Database only
docker-compose --profile web up -d      # Database + web app
docker-compose --profile scraper run scraper python -m src.main scrape
docker-compose --profile tools up -d    # Includes pgAdmin at :5050
```

## Database Connection

- **Host**: localhost (or `postgres` in Docker network)
- **Port**: 54320 (mapped from container's 5432)
- **Database**: wandering_inn_tracker
- **User**: wandering_inn
- **Password**: dev_password_change_in_production

## Key Database Tables

- `chapters` - Chapter content and metadata
- `characters` - Character info with aliases
- `raw_events` - Unprocessed scraped events (awaiting assignment)
- `character_classes` - Class acquisitions per character
- `character_levels` - Level progression per class
- `abilities` - Skills/spells catalog
- `character_abilities` - Character ability acquisitions
- `ai_chapter_state` - Tracks AI processing progress per chapter

## API Routes

- `GET /api/characters` - All characters
- `GET /api/chapters` - All chapters
- `GET /api/progression?characterId=X&maxChapter=Y` - Character progression
- `GET /api/character-summary?characterId=X` - Character current state
- `GET /api/admin/events` - Unassigned raw events
- `POST /api/admin/assign` - Assign event to character
- `POST /api/admin/process` - Convert events to progression data

## Architecture Notes

**Two-Step Scraping**: The scraper first builds a chapter URL list from the Table of Contents (`build-toc`), then scrapes content (`scrape`). This is necessary because chapter URLs are date-based and unpredictable.

**Event Pipeline**:
1. Scraper extracts all `[bracketed text]` from chapters as raw events
2. AI processing (or manual admin UI) attributes events to characters
3. Events with confidence >= 0.93 are auto-accepted; lower confidence flagged for review
4. Processed events become character progression data

**Rate Limiting**: 10-second delay between requests (per robots.txt). Initial scrape of thousands of chapters takes days.

**Error Resilience**: The scraper saves chapters even if parsing fails. See `scraper/ERROR_HANDLING.md` for details on failure modes and recovery strategies.

## Event Pattern Examples

The series uses bracket notation for progression:
```
[Warrior class obtained!]
[Warrior Level 5!]
[Skill - Power Strike obtained!]
[Spell - Fireball obtained!]
[Skill Change - Power Strike -> Greater Power Strike!]
[Condition - Poisoned obtained!]
```

Incomplete/cancelled events (unclosed brackets) are captured separately for manual review.

## Development Considerations

- The series is 12M+ words with thousands of chapters
- Large character cast requires disambiguation
- Raw events stored separately from processed data for manual review
- All progression tied to chapters for spoiler-free queries
- Scraper is idempotent (safe to restart/re-run)
