-- Migration: Add false_positive event type for AI-detected non-progression events
-- These are bracket text that look like events but aren't (e.g., skill names mentioned in dialogue)

-- Drop the old constraint
ALTER TABLE raw_events DROP CONSTRAINT IF EXISTS raw_events_event_type_check;

-- Add new constraint with false_positive type
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
        'ability_obtained',
        'ability_removed',
        'false_positive',  -- Not a real progression event (mentioned in dialogue, etc.)
        'other'
    )
);

COMMENT ON COLUMN raw_events.event_type IS 'Type of progression event. false_positive indicates AI determined this is not a real event.';
