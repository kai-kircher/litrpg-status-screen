-- Migration: Add AI processing support
-- This migration adds columns for AI-assisted event attribution and character knowledge

-- ============================================================================
-- RAW EVENTS: AI ATTRIBUTION COLUMNS
-- ============================================================================

-- AI confidence score (0.00 - 1.00)
ALTER TABLE raw_events ADD COLUMN IF NOT EXISTS ai_confidence DECIMAL(3,2);

-- AI reasoning for the attribution
ALTER TABLE raw_events ADD COLUMN IF NOT EXISTS ai_reasoning TEXT;

-- Flag for events that need human review (confidence < 0.93)
ALTER TABLE raw_events ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;

-- Add index for review queue queries
CREATE INDEX IF NOT EXISTS idx_raw_events_needs_review ON raw_events(needs_review) WHERE needs_review = TRUE;

-- ============================================================================
-- CHARACTERS: KNOWLEDGE COLUMN
-- ============================================================================

-- JSONB column for storing character knowledge
-- Structure: {
--   "species": "Human",
--   "classes": ["Innkeeper", "Singer"],
--   "current_levels": {"Innkeeper": 45, "Singer": 20},
--   "known_skills": ["Boon of the Guest", "Inn's Aura"],
--   "known_spells": [],
--   "summary": "Brief character description..."
-- }
ALTER TABLE characters ADD COLUMN IF NOT EXISTS knowledge JSONB DEFAULT '{}';

-- ============================================================================
-- AI PROCESSING LOG
-- ============================================================================

-- Track AI API usage for cost monitoring
CREATE TABLE IF NOT EXISTS ai_processing_log (
    id SERIAL PRIMARY KEY,
    chapter_id INTEGER REFERENCES chapters(id),
    processing_type VARCHAR(50) NOT NULL, -- 'character_extraction', 'event_attribution'
    model_used VARCHAR(100) NOT NULL,     -- 'claude-3-haiku-20240307', etc.
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_estimate DECIMAL(10,6),          -- Estimated cost in USD
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ai_processing_log_type_check CHECK (
        processing_type IN ('character_extraction', 'event_attribution', 'knowledge_update')
    )
);

-- Index for cost analysis queries
CREATE INDEX IF NOT EXISTS idx_ai_processing_log_type ON ai_processing_log(processing_type);
CREATE INDEX IF NOT EXISTS idx_ai_processing_log_chapter ON ai_processing_log(chapter_id);
CREATE INDEX IF NOT EXISTS idx_ai_processing_log_date ON ai_processing_log(processed_at);

-- ============================================================================
-- AI PROCESSING STATE
-- ============================================================================

-- Track which chapters have been processed by AI
CREATE TABLE IF NOT EXISTS ai_chapter_state (
    chapter_id INTEGER PRIMARY KEY REFERENCES chapters(id) ON DELETE CASCADE,
    characters_extracted BOOLEAN DEFAULT FALSE,
    characters_extracted_at TIMESTAMP WITH TIME ZONE,
    events_attributed BOOLEAN DEFAULT FALSE,
    events_attributed_at TIMESTAMP WITH TIME ZONE,

    -- Stats for this chapter
    characters_found INTEGER DEFAULT 0,
    new_characters_created INTEGER DEFAULT 0,
    events_processed INTEGER DEFAULT 0,
    events_auto_accepted INTEGER DEFAULT 0,
    events_flagged_review INTEGER DEFAULT 0
);

-- Comments for documentation
COMMENT ON COLUMN raw_events.ai_confidence IS 'AI confidence score (0.00-1.00). >= 0.93 auto-accepts, < 0.70 requires manual review';
COMMENT ON COLUMN raw_events.ai_reasoning IS 'AI explanation for the character attribution';
COMMENT ON COLUMN raw_events.needs_review IS 'TRUE if AI confidence was below auto-accept threshold (0.93)';
COMMENT ON COLUMN characters.knowledge IS 'JSONB storage for character knowledge (species, classes, skills, summary)';
COMMENT ON TABLE ai_processing_log IS 'Tracks AI API calls for cost monitoring';
COMMENT ON TABLE ai_chapter_state IS 'Tracks AI processing state per chapter for resumability';
