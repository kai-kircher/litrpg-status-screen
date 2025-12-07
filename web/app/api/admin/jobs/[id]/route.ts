import { NextRequest, NextResponse } from 'next/server';
import pool from '@/lib/db';

// GET /api/admin/jobs/[id] - Get single job status
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const jobId = parseInt(id);

    if (!jobId) {
      return NextResponse.json(
        { error: 'Invalid job ID' },
        { status: 400 }
      );
    }

    const result = await pool.query(
      `SELECT id, job_type, status, started_at, completed_at,
              config, progress, result, error_message, created_at
       FROM jobs WHERE id = $1`,
      [jobId]
    );

    if (result.rows.length === 0) {
      return NextResponse.json(
        { error: 'Job not found' },
        { status: 404 }
      );
    }

    return NextResponse.json(result.rows[0]);
  } catch (error) {
    console.error('Error getting job:', error);
    return NextResponse.json(
      { error: 'Failed to get job' },
      { status: 500 }
    );
  }
}
