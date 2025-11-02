-- Backfill is_processed flag for events that have already been processed
-- An event is considered processed if it appears in any of the progression tables

UPDATE raw_events
SET is_processed = TRUE
WHERE id IN (
    -- Events that created character classes
    SELECT DISTINCT raw_event_id
    FROM character_classes
    WHERE raw_event_id IS NOT NULL

    UNION

    -- Events that created character levels
    SELECT DISTINCT raw_event_id
    FROM character_levels
    WHERE raw_event_id IS NOT NULL

    UNION

    -- Events that created character abilities
    SELECT DISTINCT raw_event_id
    FROM character_abilities
    WHERE raw_event_id IS NOT NULL
);

-- Show summary of what was updated
SELECT
    COUNT(*) FILTER (WHERE is_processed = TRUE) as processed_count,
    COUNT(*) FILTER (WHERE is_processed = FALSE) as unprocessed_count,
    COUNT(*) as total_count
FROM raw_events
WHERE is_assigned = TRUE;
