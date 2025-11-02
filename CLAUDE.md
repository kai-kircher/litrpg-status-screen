# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Wandering Inn Tracker is an application designed to scrape and track character progression data from The Wandering Inn web serial. It extracts and stores information about characters' classes, levels, skills, and spells as they progress through the story, allowing readers to look up character abilities at specific points without encountering spoilers.

## Core Data Model

The application needs to track:
- **Characters**: Named individuals from the series
- **Classes**: Character classes (can be multiple per character, can evolve/consolidate)
- **Levels**: Level progression per class (may skip intermediate levels)
- **Skills**: Abilities gained through leveling or learning
- **Spells**: Magic abilities (treated similarly to skills)
- **Chapters**: Source location for each progression event

Key relationships:
- Characters can have multiple classes simultaneously
- Classes can evolve into new classes or consolidate multiple classes
- Level gains may skip intermediate levels (e.g., level 4 → level 6)
- Skills/spells are typically gained on level-up but can be learned manually
- All progression data must be tied to specific chapters for spoiler-free lookups

## Text Parsing Requirements

The application must parse specific bracket-delimited patterns from chapter text:

```
[{CLASS NAME} class obtained!]
[{CLASS NAME} level {NUMBER}!]
[Skill - {SKILL NAME} obtained!]
[Spell - {SPELL NAME} obtained!]
```

Important parsing considerations:
- The series formatting is mostly consistent but may have minor inconsistencies
- Pattern matching should be flexible to handle variations in skill/spell naming
- Level notifications only show the final level reached (not intermediate levels)
- Each extracted event needs chapter context for timeline accuracy

## Tech Stack

- **Scraper**: Python with BeautifulSoup/Scrapy for web scraping and text parsing
- **Frontend**: Tanstack Start (full-stack React framework)
- **Database**: PostgreSQL
- **Deployment**: AWS with containerized deployment (Docker)
- **Infrastructure**: Cost-optimized AWS architecture

## Project Structure

```
wandering-inn-tracker/
├── scraper/              # Python scraping application
│   ├── src/
│   │   ├── parsers/      # Text pattern matching
│   │   ├── scrapers/     # Web scraping logic
│   │   └── db/           # Database operations
│   ├── requirements.txt
│   └── Dockerfile
├── web/                  # Tanstack Start application
│   ├── app/
│   │   ├── routes/       # Page routes
│   │   └── components/   # React components
│   ├── package.json
│   └── Dockerfile
├── database/
│   ├── migrations/       # SQL migration files
│   └── schema.sql        # Database schema
└── infrastructure/
    ├── docker-compose.yml # Local development
    └── aws/              # AWS deployment configs
```

## Application Architecture

The system is designed with three main components:

1. **Scraper/Parser** (Python):
   - Extracts chapter content from The Wandering Inn website
   - Identifies progression events using bracket pattern regex
   - Stores raw events in PostgreSQL for manual assignment
   - Can run as scheduled job (cron or ECS scheduled task)

2. **Database** (PostgreSQL):
   - Stores chapters, characters, progression events
   - Maintains character-class-level relationships
   - Supports efficient historical queries with proper indexing

3. **Web Application** (Tanstack Start):
   - Manual assignment UI for linking events to characters
   - Query interface for character lookups
   - Chapter-aware filtering to prevent spoilers
   - API routes for CRUD operations

The application must support:
- Sequential chapter-by-chapter processing
- Manual assignment of progression events to characters (since automatic attribution is difficult)
- Historical queries: "What skills did Character X have at level Y?"
- Chapter-aware filtering to prevent spoilers
- Future extensibility to other LitRPG series

## Local Development Setup

**Database**:
```bash
docker-compose up -d postgres           # Start PostgreSQL container
cd database
.\migrate.ps1                          # Windows: Run migrations
./migrate.sh                            # Mac/Linux: Run migrations
```

**Scraper** (Python):
```bash
cd scraper
python -m venv venv
venv\Scripts\activate                   # Windows
source venv/bin/activate                # Mac/Linux
pip install -r requirements.txt
python -m src.main check-db             # Test database connection
python -m src.main test 1               # Test on chapter 1
python -m src.main scrape --max 5       # Scrape 5 chapters
```

**Scraper Workflow** (Two-step process):
```bash
# Step 1: Build chapter list from Table of Contents
python -m src.main build-toc         # Scrapes ToC page, saves URLs to DB

# Step 2: Scrape chapter content
python -m src.main scrape            # Uses URLs from Step 1 to scrape
python -m src.main scrape --max 5    # Scrape 5 chapters only
```

**Other Scraper Commands**:
- `python -m src.main show-toc` - View chapter statistics from DB
- `python -m src.main test 1` - Test scraper on chapter 1 (no DB save)
- `python -m src.main fetch 1` - Fetch and display chapter 1
- `python -m src.main check-db` - Verify database connection
- `python -m src.main -v scrape` - Verbose logging

**Why two steps?** The Wandering Inn uses complex, date-based URLs (e.g., `/2016/07/27/1-00/`) that can't be predicted. The ToC scraper builds an ordered list of all chapter URLs first.

**Web Application** (Tanstack Start):
```bash
cd web
npm install
cp .env.local.example .env.local  # Configure database connection
npm run dev                        # Development server (http://localhost:3000)
npm run build                      # Production build
npm start                          # Production server
npm run typecheck                  # TypeScript type checking
```

**Web App Routes:**
- `/` - Main status screen (character progression lookup)
- `/api/characters` - GET all characters
- `/api/chapters` - GET all chapters
- `/api/progression/:id?maxChapter=X` - GET character progression
- `/api/character/:id/summary` - GET character current state

**Full Stack** (Docker Compose):
```bash
docker-compose up  # Runs all services (postgres, scraper, web)
```

## AWS Deployment Architecture (Cost-Optimized)

**Option 1: Single EC2 Instance (Cheapest)**
- t3.small or t4g.small EC2 instance (~$15-20/month)
- Run docker-compose with all services on one instance
- PostgreSQL in a Docker container with persistent EBS volume
- Use Elastic IP for stable access
- Good for initial development and low traffic

**Option 2: ECS + RDS (Production-Ready, Moderate Cost)**
- **Database**: RDS PostgreSQL t4g.micro with gp3 storage (~$20-30/month)
  - Enable automated backups
  - Single-AZ for cost savings (multi-AZ for production)
- **Web App**: ECS Fargate service (~$15-30/month depending on traffic)
  - Application Load Balancer for HTTPS
  - Auto-scaling based on CPU/memory
- **Scraper**: ECS Scheduled Task (runs periodically, minimal cost)
  - Fargate Spot for cost savings
  - CloudWatch Events for scheduling
- **Total**: ~$50-80/month

**Option 3: Hybrid (Balanced)**
- RDS PostgreSQL t4g.micro for managed database
- Single EC2 t3.small running web app + scraper via docker-compose
- Easier than full ECS but with managed database benefits
- Total: ~$35-50/month

**Cost Optimization Tips**:
- Use AWS Free Tier where available (RDS, EC2 for first year)
- Enable RDS storage autoscaling to avoid over-provisioning
- Use gp3 EBS volumes (cheaper than gp2)
- Consider ARM instances (t4g family) for 20% savings
- Use Fargate Spot for scraper jobs (70% cheaper)
- Set up CloudWatch alarms to monitor costs

## Scraper Implementation Details

**HTML Selectors** (src/scrapers/chapter_scraper.py):
The scraper contains placeholder CSS selectors that must be updated for The Wandering Inn's actual HTML structure:
- `_build_chapter_url()` - URL pattern for chapters
- `_extract_chapter_data()` - Selectors for title, content, published date

**Event Patterns** (src/parsers/event_parser.py):
Regex patterns for extracting progression events from text:
- Class obtained: `\[([^\]]+?)\s+[Cc]lass\s+[Oo]btained!?\]`
- Level up: `\[([^\]]+?)\s+[Ll]evel\s+(\d+)!?\]`
- Skill: `\[[Ss]kill\s*[-–—:]\s*([^\]]+?)\s+[Oo]btained!?\]`
- Spell: `\[[Ss]pell\s*[-–—:]\s*([^\]]+?)\s+[Oo]btained!?\]`

The parser includes validation to reduce false positives and handles minor formatting variations.

**Database Operations** (src/db/operations.py):
- `save_chapter()` - Upserts chapter with ON CONFLICT handling
- `save_raw_events_batch()` - Batch insert for performance
- `chapter_exists()` - Idempotency check
- `get_last_scraped_chapter()` - Resume capability

**Rate Limiting**:
Default 2-second delay between requests. The initial scrape of thousands of chapters will take hours. The scraper:
- Stops after 5 consecutive complete failures (not partial)
- Can be interrupted and resumed safely
- Skips already-scraped chapters
- Logs progress with detailed event statistics

**Error Handling & Resilience**:
The scraper is highly resilient to formatting inconsistencies:
- **Partial failures** - Saves chapter even if event parsing fails
- **Malformed events** - Individual parsing errors don't stop other events
- **Incomplete events** - Captures intentionally cancelled progressions (e.g., `[Warrior class` unclosed)
- **Graceful degradation** - Empty chapters and parsing errors logged but don't halt scraper
- **Detailed statistics** - Tracks fully scraped, partial, failed, and incomplete events separately

See `scraper/ERROR_HANDLING.md` for full details.

## Development Considerations

- The Wandering Inn is one of the longest pieces of fiction, so performance and data volume are concerns
- Web scraping should respect the source website's policies and rate limits (2s delay default)
- The large cast means character disambiguation will be important
- Raw events are stored separately from character assignments to enable manual review
- Timeline consistency is critical: data must be tied to specific chapters
- PostgreSQL indexes are critical: index on (character_id, chapter_id), (chapter_id, event_type)
- The scraper is idempotent (safe to re-run on same chapters)
- Store scrape timestamps to track when data was last updated
- Initial scrape will take hours; run in tmux/screen or as background job
- Test scraper on a few chapters before doing full scrape to validate selectors
