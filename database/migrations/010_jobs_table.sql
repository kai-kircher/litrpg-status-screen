-- Migration: Add jobs table for tracking background job status
-- Used by the admin UI to trigger and monitor scraper/AI jobs

CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,           -- 'scrape', 'process-ai', 'build-toc'
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed', 'cancelled'
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Job configuration
    config JSONB DEFAULT '{}',               -- Start/end chapter, max chapters, etc.

    -- Progress tracking
    progress JSONB DEFAULT '{}',             -- Current progress (chapters_done, events_processed, etc.)

    -- Output
    result JSONB,                            -- Final result summary
    error_message TEXT,                      -- Error details if failed

    -- Docker container info
    container_id VARCHAR(100),               -- Docker container ID

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT jobs_status_check CHECK (
        status IN ('pending', 'running', 'completed', 'failed', 'cancelled')
    ),
    CONSTRAINT jobs_type_check CHECK (
        job_type IN ('scrape', 'process-ai', 'build-toc', 'extract-characters', 'attribute-events', 'scrape-wiki')
    )
);

-- Index for finding active jobs
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status) WHERE status IN ('pending', 'running');

-- Index for recent jobs
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);

-- Comments
COMMENT ON TABLE jobs IS 'Tracks background scraper/AI jobs triggered from the admin UI';
COMMENT ON COLUMN jobs.config IS 'Job configuration JSON (start_chapter, end_chapter, max_chapters, dry_run, etc.)';
COMMENT ON COLUMN jobs.progress IS 'Current progress JSON (chapters_done, total_chapters, events_processed, etc.)';
