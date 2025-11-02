# Error Handling & Resilience

The scraper is designed to be highly resilient to formatting inconsistencies and errors in The Wandering Inn web serial.

## Philosophy: Never Give Up

The scraper follows these principles:

1. **Save what you can** - If a chapter is fetched, save it even if parsing fails
2. **Continue forward** - One bad chapter shouldn't stop the entire scrape
3. **Track issues** - Log problems for later review without crashing
4. **Partial success is success** - A chapter with parsing errors is better than no chapter

## Error Categories

The scraper distinguishes between different types of failures:

### 1. Complete Failures (`chapters_failed`)
Chapter couldn't be fetched or saved at all.

**Causes:**
- Network error (timeout, DNS failure)
- HTTP 404 (chapter doesn't exist)
- Database connection lost
- URL not found in database

**Handling:**
- Counts toward consecutive failures (stops after 5)
- Chapter NOT saved to database
- Scraper moves to next chapter

### 2. Partial Failures (`chapters_partial`)
Chapter was saved but had parsing issues.

**Causes:**
- Empty chapter content
- Malformed HTML structure
- Event parsing errors
- Database error saving events (but chapter saved)

**Handling:**
- Chapter IS saved to database
- Events that parsed successfully ARE saved
- Logged as warning, not error
- Scraper continues normally

### 3. Parsing Errors (`parsing_errors`)
Individual events that couldn't be parsed.

**Causes:**
- Malformed bracket syntax
- Empty class/skill names
- Invalid level numbers
- Missing regex capture groups

**Handling:**
- Other events in same chapter still processed
- Error logged at debug level
- Tracked in `parser.parse_errors` list
- Chapter still considered successful

### 4. Incomplete Events (`events_incomplete`)
Intentionally malformed events (e.g., cancelled class assignments).

**Causes:**
- Character rejects a class: `[Warrior class` (unclosed bracket)
- Skill offer declined: `[Skill - [Incomplete]`
- Narrative intentional malformation

**Handling:**
- Captured by special incomplete patterns
- Saved to database with `is_incomplete=True` flag
- Requires manual review in web UI
- Counted separately in statistics

## Event Parser Resilience

The parser has multiple layers of error handling:

### Layer 1: Input Validation
```python
if not text or not isinstance(text, str):
    logger.warning("Empty or invalid text provided")
    return []  # Empty list, not crash
```

### Layer 2: Per-Event Try/Catch
Each event is wrapped in try/catch - one malformed event doesn't stop others:

```python
for match in pattern.finditer(text):
    try:
        event = self._create_event(...)
        if event:
            events.append(event)
    except Exception as e:
        # Log and continue to next event
        continue
```

### Layer 3: Graceful Parsing
Each field is validated before use:

```python
# Check if we have enough capture groups
if match.lastindex < 2:
    return None

# Validate level is a number
try:
    level = int(match.group(2))
except ValueError:
    return None  # Not an error, just invalid
```

### Layer 4: Context Extraction Fallback
If context extraction fails, fall back to raw text:

```python
try:
    context = self._extract_context(...)
except Exception:
    context = raw_text  # Better than nothing
```

## Scraper Resilience

The main scraper ensures chapters are saved even when parsing fails:

```python
chapter_saved = False
parsing_had_issues = False

try:
    # Fetch chapter
    chapter_data = fetch(...)

    # Save chapter FIRST
    chapter_id = save_chapter(...)
    chapter_saved = True

    # Then try to parse events
    try:
        events = parse(...)
    except Exception:
        # Chapter is still saved!
        parsing_had_issues = True

    return True  # Success even if parsing failed

except Exception:
    # Only fail if chapter itself wasn't saved
    return chapter_saved
```

## Statistics Tracking

The scraper provides detailed statistics:

```
Scraping completed
============================================================
Chapters processed: 100
  ✓ Fully scraped: 92        (everything worked)
  ⚠ Partial (with issues): 6 (chapter saved, parsing issues)
  ✗ Failed: 2                (chapter not fetched)
  ⊘ Skipped (already existed): 50

Events found: 1,247
  Incomplete/cancelled: 15   (intentional malformations)
  Parsing errors: 23         (malformed events)

Total errors: 2
============================================================
```

## Consecutive Failure Logic

The scraper stops after 5 consecutive COMPLETE failures:

- **Complete failure**: Chapter not fetched at all → Counts
- **Partial failure**: Chapter saved, parsing issues → Doesn't count
- **Success**: Everything worked → Resets counter

This prevents infinite loops on truly dead chapter ranges while tolerating intermittent issues.

## Real-World Examples

### Example 1: Malformed Bracket
```
Chapter text: "[Warrior clas obtained!"
```

**Handling:**
- Regex doesn't match (typo in "class")
- No event created
- No error logged (debug only)
- Other events in chapter still processed
- Chapter marked as successful

### Example 2: Cancelled Class
```
Chapter text: "She felt the pull... [Necromancer class—no!"
```

**Handling:**
- Matched by incomplete pattern
- Saved with `is_incomplete=True`
- Counted in `events_incomplete`
- Available for manual review
- Chapter marked as successful

### Example 3: Empty Chapter Content
```
Chapter fetched but HTML changed, no content extracted
```

**Handling:**
- Chapter metadata saved (title, URL)
- Content field empty
- No events parsed (no content to parse)
- Logged as warning
- Chapter marked as partial success
- Can be re-scraped later

### Example 4: Database Error During Event Save
```
Chapter parsed successfully, 50 events found
Database connection lost during batch insert
```

**Handling:**
- Chapter already saved earlier
- Events not saved (transaction rolled back)
- Logged as warning
- Chapter marked as partial success
- Events can be re-parsed from saved content

## Debugging Parsing Errors

The parser tracks errors in `parser.parse_errors`:

```python
{
    'position': 1234,
    'raw_text': '[Warrior clas obtained!]',
    'error': 'No match found',
    'event_type': 'class_obtained'
}
```

Enable verbose logging to see these:
```bash
python -m src.main -v scrape --max 5
```

## Recovery Strategies

### Re-scrape Failed Chapters
Chapters marked as failed can be re-scraped by clearing the `content` field:

```sql
UPDATE chapters SET content = NULL WHERE id IN (SELECT id FROM chapters WHERE content IS NULL OR content = '');
```

Then re-run the scraper - it will skip chapters with content.

### Re-parse Existing Content
If you improve the parser, re-parse without re-scraping:

```sql
-- Delete events from chapters
DELETE FROM raw_events WHERE chapter_id IN (1, 2, 3, ...);

-- Then manually re-parse using the parse command
python -m src.main parse chapter_content.txt
```

Or write a script to re-parse all chapters from database.

## Best Practices

1. **Start small** - Test on 5-10 chapters first: `--max 10`
2. **Monitor logs** - Watch for patterns in partial failures
3. **Update selectors** - If many chapters fail, HTML structure may have changed
4. **Check parsing errors** - If many parsing errors, regex patterns may need tuning
5. **Resume freely** - The scraper is idempotent, safe to restart anytime

## Summary

The scraper is designed for a messy, real-world web serial with:
- **Thousands of chapters** spanning years
- **Inconsistent formatting** across different time periods
- **Intentional malformations** (cancelled progressions)
- **Potential HTML changes** on the website
- **Network intermittency** during long scrapes

It prioritizes **saving data** over **perfect data**, allowing manual review and refinement later in the web UI.
