# AI-Assisted Event Processing Plan

## Overview

Refactor the event processing pipeline to use Claude AI (Haiku/Sonnet) for:
1. **Character identification** - Automatically identify and catalog characters from chapter text
2. **Character knowledge building** - Build contextual knowledge for each character over time
3. **Event attribution** - Map progression events to characters using AI with context

## Architecture Decision: Knowledge Storage

**Recommendation: PostgreSQL with JSONB columns**

Why this approach over alternatives:

| Approach | Pros | Cons |
|----------|------|------|
| **PostgreSQL + JSONB** | No new infrastructure, queryable, transactional, easy to edit via admin UI | Less semantic matching |
| JSON files | Easy to version control, human-readable | Hard to query, sync issues with DB |
| Vector embeddings | Semantic search, handles ambiguity well | Requires new infrastructure (Pinecone/pgvector), more complex, overkill for ~500 characters |

For The Wandering Inn with ~500-1000 named characters, JSONB in PostgreSQL is sufficient. The AI can match characters by name/alias without needing semantic search. If needed, pgvector can be added later.

---

## Phase 1: Database Schema Updates

### New Tables

```sql
-- Enhanced character knowledge
ALTER TABLE characters ADD COLUMN IF NOT EXISTS knowledge JSONB DEFAULT '{}';
-- Structure: {
--   "species": "Human",
--   "classes": ["Innkeeper", "Singer"],
--   "known_skills": ["Boon of the Guest", "Inn's Aura"],
--   "relationships": {"Pisces": "friend", "Lyonette": "employee"},
--   "summary": "Erin Solstice is a human innkeeper from Earth..."
-- }

-- AI processing tracking
CREATE TABLE ai_processing_log (
    id SERIAL PRIMARY KEY,
    chapter_id INTEGER REFERENCES chapters(id),
    processing_type VARCHAR(50), -- 'character_extraction', 'event_attribution'
    model_used VARCHAR(50),      -- 'claude-3-haiku', 'claude-3-sonnet'
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_estimate DECIMAL(10,6),
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add confidence tracking to raw_events
ALTER TABLE raw_events ADD COLUMN IF NOT EXISTS ai_confidence DECIMAL(3,2); -- 0.00-1.00
ALTER TABLE raw_events ADD COLUMN IF NOT EXISTS ai_reasoning TEXT;
ALTER TABLE raw_events ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;
```

---

## Phase 2: AI Processing Pipeline

### Step 1: Character Extraction (Per Chapter)

Process chapters sequentially, extracting characters mentioned:

```python
# Input to AI
{
    "chapter_number": "1.00",
    "chapter_text": "...",  # Full or truncated chapter
    "existing_characters": ["Erin Solstice", "Klbkch", ...],  # Known characters
    "existing_aliases": {"Erin Solstice": ["Erin", "the innkeeper"]}
}

# Output from AI
{
    "characters_mentioned": [
        {"name": "Erin Solstice", "confidence": 0.95},
        {"name": "Klbkch", "confidence": 0.90, "alias_used": "Klb"}
    ],
    "new_characters": [
        {
            "name": "Relc Grasstongue",
            "species": "Drake",
            "description": "A senior guardsman in Liscor",
            "first_seen_as": "the [Guard]"
        }
    ]
}
```

### Step 2: Event Attribution (Per Event Batch)

For each chapter's events, attribute to characters:

```python
# Input to AI
{
    "chapter_number": "1.00",
    "events": [
        {
            "id": 123,
            "raw_text": "[Innkeeper class obtained!]",
            "surrounding_text": "...Erin felt something click. [Innkeeper class obtained!] She blinked...",
            "event_index": 5
        }
    ],
    "chapter_characters": ["Erin Solstice", "Klbkch"],
    "character_context": {
        "Erin Solstice": {
            "species": "Human",
            "current_classes": [],
            "last_chapter_level": null
        }
    }
}

# Output from AI
{
    "attributions": [
        {
            "event_id": 123,
            "character_name": "Erin Solstice",
            "event_type": "class_obtained",
            "parsed_data": {"class_name": "Innkeeper"},
            "confidence": 0.98,
            "reasoning": "Erin is the POV character and the surrounding text uses 'She'"
        }
    ]
}
```

### Step 3: Knowledge Update

After processing events, update character knowledge:

```python
# After attributing "[Innkeeper Level 4!]" to Erin Solstice
UPDATE characters SET knowledge = knowledge || '{
    "classes": ["Innkeeper"],
    "current_levels": {"Innkeeper": 4}
}' WHERE name = 'Erin Solstice';
```

---

## Phase 3: Implementation Modules

### Directory Structure

```
scraper/
├── src/
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── client.py           # Anthropic API client wrapper
│   │   ├── character_extractor.py  # Character identification
│   │   ├── event_attributor.py     # Event -> character mapping
│   │   ├── prompts.py              # System prompts
│   │   └── cost_tracker.py         # Token/cost tracking
│   ├── parsers/
│   │   └── event_parser.py     # (existing)
│   ├── db/
│   │   ├── operations.py       # (existing, add new functions)
│   │   └── ai_operations.py    # AI-specific DB ops
│   └── ...
```

### New CLI Commands

```bash
# Phase 1: Extract characters from scraped chapters
python -m src.main extract-characters --start 1 --end 100
python -m src.main extract-characters --chapter 50  # Single chapter

# Phase 2: Attribute events to characters
python -m src.main attribute-events --start 1 --end 100
python -m src.main attribute-events --needs-review  # Only unprocessed

# Utilities
python -m src.main ai-stats  # Show token usage, costs
python -m src.main review-queue  # Show events needing review
```

---

## Phase 4: Processing Strategy

### Batch Processing Workflow

1. **Chapter-by-Chapter Processing** (AI discovers all characters)
   ```
   For each chapter (in order):
     1. Extract characters mentioned → update characters table
     2. For each bracket event:
        - Get character context (known classes, last levels)
        - Call AI to attribute event
        - If confidence >= 0.93: auto-accept
        - If confidence < 0.93: flag for review
     3. Update character knowledge with new progression
   ```

2. **Cost Estimation**
   - ~1500 events across ~100 chapters
   - Average chapter: 10,000 words ≈ 12,000 tokens
   - Character extraction: ~1000 output tokens per chapter
   - Event attribution: ~500 tokens per batch of 20 events

   Estimated costs (using Haiku at $0.25/1M input, $1.25/1M output):
   - Character extraction: 100 chapters × 12K input × $0.00000025 ≈ $0.30
   - Character extraction output: 100 × 1K output × $0.00000125 ≈ $0.13
   - Event attribution: 1500 events / 20 per batch × 2K tokens × $0.00000025 ≈ $0.004
   - **Total estimate: ~$0.50 - $2.00** for initial processing

3. **Incremental Processing**
   - New chapters: process on scrape
   - Re-processing: only re-process events marked `needs_review`

---

## Phase 5: Confidence & Review Flow

### Confidence Thresholds

| Confidence | Action |
|------------|--------|
| >= 0.93 | Auto-accept, mark `is_assigned = TRUE` |
| 0.70 - 0.92 | Accept but flag `needs_review = TRUE` |
| < 0.70 | Do not accept, flag for manual review |

### Review UI Enhancements

The web app will need:
1. **Review Queue** - List of events with `needs_review = TRUE`
2. **AI Reasoning Display** - Show why AI made its attribution
3. **Quick Actions** - Accept AI suggestion, change character, mark false positive

---

## Phase 6: Handling Edge Cases

### Multiple Characters in Scene

When progression events occur during group scenes:
- AI uses narrative cues (pronouns, POV character, preceding dialogue)
- Lower confidence when ambiguous
- Store all candidate characters in `ai_reasoning`

### Class Evolutions & Consolidations

Special handling for complex events:
```
[Warrior class evolved into Blademaster!]
```
- Extract `source_class` and `target_class`
- Link to existing character_class record

### False Positives

Non-progression brackets like `[Guard]` (title mention):
- AI classifies as `event_type = NULL` or `other`
- Auto-archive with `archived = TRUE`

---

## Implementation Order

### Milestone 1: Foundation
- [ ] Schema updates (confidence, reasoning, needs_review columns)
- [ ] Anthropic client wrapper with retry logic
- [ ] Token/cost tracking

### Milestone 2: Character Extraction
- [ ] Character extraction prompt engineering
- [ ] Extract-characters CLI command
- [ ] Test on first 10 chapters

### Milestone 3: Event Attribution
- [ ] Event attribution prompt engineering
- [ ] Attribute-events CLI command
- [ ] Confidence thresholds and flagging

### Milestone 4: Integration
- [ ] Web UI: Review queue
- [ ] Web UI: AI reasoning display
- [ ] Incremental processing for new chapters

### Milestone 5: Refinement
- [ ] Analyze false positive/negative rates
- [ ] Tune prompts based on errors
- [ ] Add character knowledge feedback loop

---

## Cost Controls

1. **Use Haiku by default** - Much cheaper, usually sufficient
2. **Fall back to Sonnet** - Only for low-confidence retries
3. **Batch events** - Process 10-20 events per API call
4. **Cache character context** - Don't re-fetch for every event
5. **Dry-run mode** - Preview API calls without spending tokens

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| AI hallucinating characters | Validate against existing character list |
| High API costs | Start with Haiku, batch aggressively, dry-run first |
| Character disambiguation errors | Use chapter context, flag low confidence |
| Schema migration issues | Additive changes only, backward compatible |

---

## Decisions Made

1. **Character seeding**: Let AI discover all characters (no manual seeding)
2. **Auto-accept threshold**: 0.93 confidence
3. **Processing approach**: Build pipeline for all chapters (starting fresh)
