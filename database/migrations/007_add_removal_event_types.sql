-- Migration: Add removal/loss event types for classes, skills, and spells
-- Tracks when abilities are lost, removed, or consolidated

-- Drop the old constraint
ALTER TABLE raw_events
DROP CONSTRAINT raw_events_event_type_check;

-- Add new constraint with removal event types
ALTER TABLE raw_events
ADD CONSTRAINT raw_events_event_type_check CHECK (
    event_type IN (
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
        'other'
    )
);

-- Record migration
INSERT INTO migrations (name, applied_at)
VALUES ('007_add_removal_event_types', CURRENT_TIMESTAMP);
