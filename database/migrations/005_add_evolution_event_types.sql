-- Migration: Add class_evolution, class_consolidation, and skill_change event types
-- These support tracking class/skill evolutions and consolidations

-- Drop the old constraint
ALTER TABLE raw_events
DROP CONSTRAINT raw_events_event_type_check;

-- Add new constraint with additional event types
ALTER TABLE raw_events
ADD CONSTRAINT raw_events_event_type_check CHECK (
    event_type IN (
        'class_obtained',
        'class_evolution',
        'class_consolidation',
        'level_up',
        'skill_change',
        'skill_obtained',
        'spell_obtained'
    )
);

-- Record migration
INSERT INTO migrations (name, applied_at)
VALUES ('005_add_evolution_event_types', CURRENT_TIMESTAMP);
