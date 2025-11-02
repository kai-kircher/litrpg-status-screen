# Database Schema

## Overview

The database is designed to handle the two-phase workflow of this application:
1. **Scraping Phase**: Extract progression events from chapters
2. **Assignment Phase**: Manually link events to characters

## Core Tables

### `chapters`
Stores chapter metadata and content from The Wandering Inn.
- Tracks scrape timestamps for idempotent processing
- Stores full content for potential re-parsing

### `characters`
Catalog of all characters in the series.
- Supports aliases for characters with multiple names
- Tracks first appearance for context

### `raw_events`
**Unprocessed** events extracted during scraping.
- Each bracketed notification becomes a row
- `is_assigned = FALSE` until manually linked to a character
- Stores context text to help with manual assignment
- `parsed_data` JSONB field holds structured extraction

### `character_classes`
**Processed** class assignments after manual review.
- Tracks class evolution via `evolved_from_class_id`
- Handles class consolidation via `consolidated_class_ids` array
- `is_active` flag marks superseded classes

### `character_levels`
Level progression for each character-class combination.
- One row per level gain
- May skip intermediate levels (e.g., 4 → 6 gets one row with level=6)

### `abilities`
Catalog of all skills and spells (unified table).
- `type` field distinguishes 'skill' vs 'spell'
- `normalized_name` for fuzzy matching during scraping

### `character_abilities`
**Processed** ability acquisitions after manual assignment.
- Links characters to abilities with chapter context
- Tracks acquisition method (level-up vs learned)
- Optional link to the class that granted it

## Workflow

### 1. Scraping
```
chapters → raw_events (is_assigned = FALSE)
```
Python scraper:
- Inserts chapters
- Extracts bracketed patterns
- Creates `raw_events` with parsed data
- Does NOT assign to characters

### 2. Manual Assignment (Web UI)
```
raw_events → character_classes
           → character_levels
           → character_abilities
```
User reviews unassigned events and:
- Creates/selects character
- Links event to character
- Updates `is_assigned = TRUE`
- Creates appropriate character_* record

### 3. Querying
```
get_character_abilities_at_chapter(character_id, chapter_num)
get_character_level_at_chapter(character_id, class_name, chapter_num)
```
Web UI provides spoiler-free lookups.

## Key Design Decisions

### Why separate `raw_events` from `character_*` tables?
- Automatic character attribution is unreliable (large cast, similar names)
- Scraper can run fully automated without human intervention
- Manual assignment happens asynchronously in the UI
- Allows re-assignment if mistakes are made

### Why `normalized_name` on abilities?
- Handles inconsistent capitalization/spacing in source text
- Enables fuzzy matching: "Immortal Moment" ≈ "immortal moment"
- Prevents duplicate abilities from minor variations

### Why track class evolution separately?
- Classes can consolidate (multiple classes → one)
- Classes can evolve (Innkeeper → Magic Innkeeper)
- Need to maintain historical accuracy (character had X at chapter Y)
- `is_active` flag lets us query "current" classes easily

### Why JSONB for `parsed_data`?
- Pattern matching may extract different fields per event type
- Schema can evolve without migrations
- Useful for debugging scraper logic

## Indexes

Critical indexes for common queries:
- `(character_id, chapter_id)` on `character_abilities` - "what abilities at chapter X?"
- `(chapter_id, is_assigned)` on `raw_events` - "unassigned events in chapter X"
- `(character_class_id, chapter_id)` on `character_levels` - "level at chapter X"

## Views

### `unassigned_events`
Shows events awaiting manual assignment, ordered by chapter.
Used by the web UI assignment interface.

### `character_current_state`
Quick lookup of each character's latest classes and levels.
Useful for dashboards and character browsing.

### `character_abilities_timeline`
Full progression history for a character.
Powers the detailed character profile pages.

## Utility Functions

### `get_character_abilities_at_chapter(character_id, chapter_number)`
Returns all abilities a character has up to a specific chapter.
Enables spoiler-free queries.

### `get_character_level_at_chapter(character_id, class_name, chapter_number)`
Returns the character's level for a specific class at a given chapter.
Handles skipped levels correctly (returns highest level <= chapter).
