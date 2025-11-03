-- Migration: Add archived flag to raw_events
-- This allows marking false positive events as archived without deleting them

ALTER TABLE raw_events
ADD COLUMN archived BOOLEAN NOT NULL DEFAULT FALSE;

-- Create index for filtering out archived events
CREATE INDEX idx_raw_events_archived
ON raw_events(archived) WHERE archived = FALSE;

-- Update the existing processing status index to include archived
DROP INDEX IF EXISTS idx_raw_events_processing_status;
CREATE INDEX idx_raw_events_processing_status
ON raw_events(is_assigned, is_processed, archived);

-- Record migration
INSERT INTO migrations (name, applied_at)
VALUES ('004_add_archived_flag', CURRENT_TIMESTAMP);
