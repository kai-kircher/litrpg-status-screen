-- Migration: Add batch processing support for Anthropic Batch API
-- Tracks batch jobs and their results for 50% cost savings on bulk AI processing

-- ============================================================================
-- BATCH JOBS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_batch_jobs (
    id SERIAL PRIMARY KEY,
    batch_id VARCHAR(100) NOT NULL UNIQUE,  -- Anthropic batch ID (msgbatch_xxx)

    -- Job metadata
    batch_type VARCHAR(50) NOT NULL,         -- 'character_extraction', 'event_attribution'
    processing_status VARCHAR(20) NOT NULL DEFAULT 'in_progress',

    -- Request tracking
    total_requests INTEGER NOT NULL DEFAULT 0,
    requests_succeeded INTEGER DEFAULT 0,
    requests_errored INTEGER DEFAULT 0,
    requests_canceled INTEGER DEFAULT 0,
    requests_expired INTEGER DEFAULT 0,

    -- Chapter range being processed
    start_chapter INTEGER,
    end_chapter INTEGER,
    chapter_ids INTEGER[],                   -- Array of chapter IDs in this batch

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP WITH TIME ZONE,   -- When batch was submitted to Anthropic
    expires_at TIMESTAMP WITH TIME ZONE,     -- Anthropic's expiry time (24h from submit)
    ended_at TIMESTAMP WITH TIME ZONE,       -- When processing completed
    results_processed_at TIMESTAMP WITH TIME ZONE,  -- When we downloaded and processed results

    -- Cost tracking
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    estimated_cost_usd DECIMAL(10,6) DEFAULT 0,

    -- Status tracking
    results_url TEXT,                        -- URL to download results
    error_message TEXT,

    CONSTRAINT ai_batch_jobs_status_check CHECK (
        processing_status IN ('in_progress', 'canceling', 'ended', 'results_processed', 'failed')
    ),
    CONSTRAINT ai_batch_jobs_type_check CHECK (
        batch_type IN ('character_extraction', 'event_attribution')
    )
);

-- Index for finding active batches
CREATE INDEX IF NOT EXISTS idx_ai_batch_jobs_status
    ON ai_batch_jobs(processing_status)
    WHERE processing_status IN ('in_progress', 'canceling');

-- Index for recent batches
CREATE INDEX IF NOT EXISTS idx_ai_batch_jobs_created
    ON ai_batch_jobs(created_at DESC);

-- ============================================================================
-- BATCH REQUEST MAPPING
-- ============================================================================

-- Maps individual batch requests to chapters/events for result processing
CREATE TABLE IF NOT EXISTS ai_batch_requests (
    id SERIAL PRIMARY KEY,
    batch_job_id INTEGER NOT NULL REFERENCES ai_batch_jobs(id) ON DELETE CASCADE,
    custom_id VARCHAR(100) NOT NULL,         -- Unique ID for this request in the batch

    -- What this request is for
    chapter_id INTEGER REFERENCES chapters(id),
    event_ids INTEGER[],                     -- For event attribution: array of event IDs

    -- Request metadata
    request_type VARCHAR(50) NOT NULL,       -- 'character_extraction', 'event_attribution'

    -- Result tracking
    result_type VARCHAR(20),                 -- 'succeeded', 'errored', 'canceled', 'expired'
    result_processed BOOLEAN DEFAULT FALSE,

    -- Token usage (filled when results come back)
    input_tokens INTEGER,
    output_tokens INTEGER,

    -- Error tracking
    error_message TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ai_batch_requests_type_check CHECK (
        request_type IN ('character_extraction', 'event_attribution')
    )
);

-- Index for finding requests by batch
CREATE INDEX IF NOT EXISTS idx_ai_batch_requests_batch
    ON ai_batch_requests(batch_job_id);

-- Index for finding unprocessed results
CREATE INDEX IF NOT EXISTS idx_ai_batch_requests_unprocessed
    ON ai_batch_requests(batch_job_id, result_processed)
    WHERE result_processed = FALSE;

-- Unique constraint on custom_id within a batch
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_batch_requests_custom_id
    ON ai_batch_requests(batch_job_id, custom_id);

-- ============================================================================
-- UPDATE JOBS TABLE FOR BATCH SUPPORT
-- ============================================================================

-- Add batch job types to the jobs table constraint
-- First drop the old constraint, then add the new one
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_type_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_type_check CHECK (
    job_type IN (
        'scrape', 'process-ai', 'build-toc',
        'extract-characters', 'attribute-events', 'scrape-wiki',
        'batch-extract-characters', 'batch-attribute-events',
        'batch-check-status', 'batch-process-results'
    )
);

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE ai_batch_jobs IS 'Tracks Anthropic Batch API jobs for cost-effective bulk AI processing (50% cheaper)';
COMMENT ON COLUMN ai_batch_jobs.batch_id IS 'Anthropic batch ID (e.g., msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d)';
COMMENT ON COLUMN ai_batch_jobs.chapter_ids IS 'Array of chapter IDs included in this batch';
COMMENT ON COLUMN ai_batch_jobs.expires_at IS 'Batch expires 24h after submission if not completed';

COMMENT ON TABLE ai_batch_requests IS 'Maps individual requests within a batch to chapters/events for result processing';
COMMENT ON COLUMN ai_batch_requests.custom_id IS 'Unique identifier for matching results to requests';
COMMENT ON COLUMN ai_batch_requests.event_ids IS 'For event attribution: IDs of raw_events being processed';
