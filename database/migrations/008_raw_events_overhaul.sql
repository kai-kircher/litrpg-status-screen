-- Migration: Overhaul raw_events for bracket-capture approach
-- This migration supports the new scraping approach where we capture ALL brackets
-- and classify them manually in the admin panel

-- Add new columns for event indexing
ALTER TABLE raw_events ADD COLUMN IF NOT EXISTS event_index INTEGER;
ALTER TABLE raw_events ADD COLUMN IF NOT EXISTS total_chapter_events INTEGER;

-- Add surrounding_text column for better context (distinct from existing context)
ALTER TABLE raw_events ADD COLUMN IF NOT EXISTS surrounding_text TEXT;

-- Make event_type nullable since it will be set manually during classification
-- Drop the constraint first, then re-add it as nullable with updated types
ALTER TABLE raw_events DROP CONSTRAINT IF EXISTS raw_events_event_type_check;

-- Change event_type to nullable
ALTER TABLE raw_events ALTER COLUMN event_type DROP NOT NULL;

-- Add new event types and make constraint more flexible
ALTER TABLE raw_events ADD CONSTRAINT raw_events_event_type_check CHECK (
    event_type IS NULL OR event_type IN (
        'class_obtained',
        'class_evolution',
        'class_consolidation',
        'class_removed',
        'level_up',
        'skill_change',
        'skill_consolidation',
        'skill_obtained',
        'skill_removed',
        'spell_obtained',
        'spell_removed',
        'condition',
        'aspect',
        'title',
        'rank',
        'ability_obtained',  -- Generic ability (skill, spell, song, etc)
        'ability_removed',   -- Generic ability removal
        'other'
    )
);

-- Add index on event_index for better query performance
CREATE INDEX IF NOT EXISTS idx_raw_events_event_index ON raw_events(chapter_id, event_index);

-- Add comment to document the new approach
COMMENT ON COLUMN raw_events.event_index IS 'Position of this event within the chapter (0-based)';
COMMENT ON COLUMN raw_events.total_chapter_events IS 'Total number of bracket events found in this chapter';
COMMENT ON COLUMN raw_events.surrounding_text IS 'Text surrounding the bracket for context (200-400 chars)';
COMMENT ON COLUMN raw_events.event_type IS 'Event classification - NULL until manually classified in admin panel';
