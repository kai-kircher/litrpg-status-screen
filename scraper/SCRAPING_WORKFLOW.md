# Wandering Inn Scraping Workflow

This document explains the two-step process for scraping The Wandering Inn.

## Why Two Steps?

The Wandering Inn has complex chapter URLs that vary by date and character:
- Example: `/2016/07/27/1-00/` (Chapter 1)
- Example: `/2017/03/21/interlude-blackmage/` (Interlude)

We can't predict these URLs, so we must first scrape the Table of Contents to build an ordered list.

## Step 1: Build Chapter List

Scrapes the Table of Contents page to extract all chapter URLs in order.

```bash
cd scraper
python -m venv venv
venv\Scripts\activate                # Windows
pip install -r requirements.txt
python -m src.main build-toc
```

This will:
1. Fetch https://wanderinginn.com/table-of-contents/
2. Extract all chapter links in order
3. Save to database: `chapters` table with `(chapter_number, title, url)`
4. Also save to `chapters.json` as backup

**Output:**
```
INFO: Fetching table of contents from https://wanderinginn.com/table-of-contents/
INFO: Successfully extracted 500 chapters from ToC
INFO: Chapter List Summary
INFO: Total chapters: 500
INFO: Regular chapters: 450
INFO: Interludes: 50
INFO: Saving chapter metadata to database...
INFO: ✓ Successfully saved 500 chapters to database
INFO: ✓ Also saved to chapters.json as backup
```

## Step 2: Scrape Chapter Content

Uses the URLs from Step 1 to fetch chapter content and parse events.

```bash
# Scrape all chapters (resumes from last scraped)
python -m src.main scrape

# Scrape first 5 chapters only
python -m src.main scrape --max 5

# Scrape specific range
python -m src.main scrape --start 1 --end 10
```

This will:
1. For each chapter number, get URL from database
2. Fetch chapter content from that URL
3. Parse progression events (classes, levels, skills, spells)
4. Save content and events to database
5. Resume automatically if interrupted

**Output:**
```
INFO: Starting from chapter 1
INFO: Fetching chapter 1 from https://wanderinginn.com/2016/07/27/1-00/
INFO: Chapter 1: Found 12 events - 1 classes, 3 levels, 6 skills, 2 spells
INFO: Saved chapter 1: 1.00
...
INFO: Scraping completed
INFO: Chapters scraped: 5
INFO: Events found: 47
```

## Viewing Chapter List

Check what's in the database:

```bash
python -m src.main show-toc
```

**Output:**
```
Total chapters in database: 500

First 5 chapters:
  1: 1.00
     https://wanderinginn.com/2016/07/27/1-00/
  2: 1.01
     https://wanderinginn.com/2016/07/27/1-01/
  ...

Last 5 chapters:
  496: 9.20
     https://wanderinginn.com/2023/10/15/9-20/
  ...
```

## Testing Individual Chapters

Before scraping everything, test on one chapter:

```bash
# Test scraping chapter 1 (no database save)
python -m src.main test 1

# Fetch and display chapter 1
python -m src.main fetch 1
```

## Complete Workflow Example

```bash
# 1. Setup
cd scraper
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. Check database connection
python -m src.main check-db

# 3. Build chapter list from ToC
python -m src.main build-toc

# 4. Verify chapter list
python -m src.main show-toc

# 5. Test on one chapter
python -m src.main test 1

# 6. Scrape first 10 chapters
python -m src.main scrape --max 10

# 7. If all looks good, scrape everything
python -m src.main scrape
```

## Resuming After Interruption

The scraper is resumable. If interrupted (Ctrl+C, crash, etc.), just run again:

```bash
python -m src.main scrape
```

It will:
- Check the last successfully scraped chapter
- Continue from the next chapter
- Skip chapters that already have content

## Re-running ToC Scraper

If new chapters are published, re-run the ToC scraper:

```bash
python -m src.main build-toc
```

This is safe - it will update existing chapters and add new ones without duplicates.

## Rate Limiting

The scraper respects rate limits:
- 2 seconds between requests (configurable in `.env`)
- For 500+ chapters, expect several hours
- Safe to run in background/tmux/screen

## Troubleshooting

**No chapters found in ToC:**
- Check if https://wanderinginn.com/table-of-contents/ is accessible
- The HTML structure may have changed
- Inspect `src/scrapers/toc_scraper.py` and update selectors

**Chapter content not found:**
- The HTML structure may have changed
- Inspect `src/scrapers/chapter_scraper.py` and update selectors in `_extract_chapter_data()`

**Database connection error:**
- Ensure PostgreSQL is running: `docker-compose ps`
- Check `.env` file has correct credentials
- Test connection: `python -m src.main check-db`

## Next Steps

After scraping:
1. Review events in database: `SELECT * FROM raw_events LIMIT 10;`
2. Build web UI for manual character assignment
3. Query character progression data