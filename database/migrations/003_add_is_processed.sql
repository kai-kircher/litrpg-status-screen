-- Migration: Add is_processed flag to raw_events
-- This tracks whether an event has been processed into the progression tables

ALTER TABLE raw_events
ADD COLUMN is_processed BOOLEAN NOT NULL DEFAULT FALSE;

-- Create index for filtering
CREATE INDEX idx_raw_events_processing_status
ON raw_events(is_assigned, is_processed);

-- Record migration
INSERT INTO migrations (name, applied_at)
VALUES ('003_add_is_processed', CURRENT_TIMESTAMP);
