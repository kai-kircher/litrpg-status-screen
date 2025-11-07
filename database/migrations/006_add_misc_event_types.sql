-- Migration: Add miscellaneous event types (conditions, aspects, titles, ranks, other)
-- The series has many progression mechanics beyond classes/skills/spells

-- Drop the old constraint
ALTER TABLE raw_events
DROP CONSTRAINT raw_events_event_type_check;

-- Add new constraint with all event types
ALTER TABLE raw_events
ADD CONSTRAINT raw_events_event_type_check CHECK (
    event_type IN (
        'class_obtained',
        'class_evolution',
        'class_consolidation',
        'level_up',
        'skill_change',
        'skill_obtained',
        'spell_obtained',
        'condition',
        'aspect',
        'title',
        'rank',
        'other'
    )
);

-- Record migration
INSERT INTO migrations (name, applied_at)
VALUES ('006_add_misc_event_types', CURRENT_TIMESTAMP);
