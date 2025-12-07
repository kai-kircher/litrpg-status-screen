import { NextResponse } from 'next/server';
import pool from '@/lib/db';

// GET /api/admin/stats - Get database statistics
export async function GET() {
  try {
    // Get counts in parallel
    const [
      chaptersResult,
      scrapedChaptersResult,
      charactersResult,
      eventsResult,
      assignedEventsResult,
      processedEventsResult,
      archivedEventsResult,
      recentJobsResult,
    ] = await Promise.all([
      // Total chapters in ToC
      pool.query('SELECT COUNT(*) as count FROM chapters'),

      // Scraped chapters (have content)
      pool.query('SELECT COUNT(*) as count FROM chapters WHERE content IS NOT NULL'),

      // Total characters
      pool.query('SELECT COUNT(*) as count FROM characters'),

      // Total events
      pool.query('SELECT COUNT(*) as count FROM raw_events WHERE archived = FALSE'),

      // Assigned events
      pool.query('SELECT COUNT(*) as count FROM raw_events WHERE is_assigned = TRUE AND archived = FALSE'),

      // Processed events
      pool.query('SELECT COUNT(*) as count FROM raw_events WHERE is_processed = TRUE AND archived = FALSE'),

      // Archived events
      pool.query('SELECT COUNT(*) as count FROM raw_events WHERE archived = TRUE'),

      // Recent jobs
      pool.query(`
        SELECT id, job_type, status, started_at, completed_at, error_message
        FROM jobs
        ORDER BY created_at DESC
        LIMIT 5
      `),
    ]);

    // Get event type breakdown
    const eventTypesResult = await pool.query(`
      SELECT
        COALESCE(event_type, 'unclassified') as event_type,
        COUNT(*) as count
      FROM raw_events
      WHERE archived = FALSE
      GROUP BY event_type
      ORDER BY count DESC
    `);

    // Get AI processing stats if table exists
    let aiStats = null;
    try {
      const aiResult = await pool.query(`
        SELECT
          processing_type,
          COUNT(*) as requests,
          SUM(input_tokens) as input_tokens,
          SUM(output_tokens) as output_tokens,
          SUM(cost_estimate) as cost
        FROM ai_processing_log
        WHERE processed_at > NOW() - INTERVAL '30 days'
        GROUP BY processing_type
      `);
      aiStats = aiResult.rows;
    } catch {
      // Table may not exist yet
    }

    return NextResponse.json({
      chapters: {
        total: parseInt(chaptersResult.rows[0].count),
        scraped: parseInt(scrapedChaptersResult.rows[0].count),
      },
      characters: parseInt(charactersResult.rows[0].count),
      events: {
        total: parseInt(eventsResult.rows[0].count),
        assigned: parseInt(assignedEventsResult.rows[0].count),
        processed: parseInt(processedEventsResult.rows[0].count),
        archived: parseInt(archivedEventsResult.rows[0].count),
        byType: eventTypesResult.rows,
      },
      recentJobs: recentJobsResult.rows,
      aiStats,
    });
  } catch (error) {
    console.error('Error getting stats:', error);
    return NextResponse.json(
      { error: 'Failed to get stats' },
      { status: 500 }
    );
  }
}
