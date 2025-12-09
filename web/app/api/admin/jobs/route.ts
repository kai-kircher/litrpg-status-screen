import { NextRequest, NextResponse } from 'next/server';
import { exec, spawn, ChildProcess } from 'child_process';
import { promisify } from 'util';
import pool from '@/lib/db';

const execAsync = promisify(exec);

// Simple API key auth - set ADMIN_API_KEY env var
function isAuthorized(request: NextRequest): boolean {
  const apiKey = process.env.ADMIN_API_KEY;
  if (!apiKey) return true; // No auth configured, allow all

  const authHeader = request.headers.get('authorization');
  if (!authHeader) return false;

  const [type, token] = authHeader.split(' ');
  return type === 'Bearer' && token === apiKey;
}

// Track running processes in memory (for cancellation)
type RunningJob = { process: ChildProcess; containerName: string };
const runningJobs: Map<number, RunningJob> = new Map();

// GET /api/admin/jobs - List jobs
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = parseInt(searchParams.get('limit') || '20');
    const status = searchParams.get('status');

    let query = `
      SELECT id, job_type, status, started_at, completed_at,
             config, progress, result, error_message, created_at
      FROM jobs
    `;
    const params: any[] = [];

    if (status) {
      query += ' WHERE status = $1';
      params.push(status);
    }

    query += ' ORDER BY created_at DESC LIMIT $' + (params.length + 1);
    params.push(limit);

    const result = await pool.query(query, params);

    // Also get any currently running job
    const runningResult = await pool.query(
      `SELECT id, job_type, status, started_at, config, progress
       FROM jobs WHERE status = 'running' LIMIT 1`
    );

    return NextResponse.json({
      jobs: result.rows,
      running: runningResult.rows[0] || null,
    });
  } catch (error) {
    console.error('Error listing jobs:', error);
    return NextResponse.json(
      { error: 'Failed to list jobs' },
      { status: 500 }
    );
  }
}

// POST /api/admin/jobs - Start a new job
export async function POST(request: NextRequest) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const body = await request.json();
    const { jobType, config = {} } = body;

    if (!jobType) {
      return NextResponse.json(
        { error: 'jobType is required' },
        { status: 400 }
      );
    }

    // Check if a job is already running
    const runningCheck = await pool.query(
      `SELECT id, job_type FROM jobs WHERE status = 'running' LIMIT 1`
    );
    if (runningCheck.rows.length > 0) {
      return NextResponse.json(
        {
          error: 'A job is already running',
          runningJob: runningCheck.rows[0],
        },
        { status: 409 }
      );
    }

    // Create job record
    const insertResult = await pool.query(
      `INSERT INTO jobs (job_type, status, config, started_at)
       VALUES ($1, 'running', $2, CURRENT_TIMESTAMP)
       RETURNING id`,
      [jobType, JSON.stringify(config)]
    );
    const jobId = insertResult.rows[0].id;

    // Build the command based on job type
    let command: string;
    switch (jobType) {
      case 'scrape':
        command = buildScrapeCommand(config);
        break;
      case 'build-toc':
        command = 'python -m src.main build-toc';
        break;
      case 'process-ai':
        command = buildProcessAiCommand(config);
        break;
      case 'extract-characters':
        command = buildExtractCharactersCommand(config);
        break;
      case 'attribute-events':
        command = buildAttributeEventsCommand(config);
        break;
      case 'batch-attribute-events':
        command = buildBatchAttributeEventsCommand(config);
        break;
      case 'scrape-wiki':
        command = 'python -m src.main scrape-wiki';
        break;
      default:
        return NextResponse.json(
          { error: `Unknown job type: ${jobType}` },
          { status: 400 }
        );
    }

    // Run the job in a Docker container with a named container for cancellation
    const containerName = `scraper-job-${jobId}`;
    const dockerCommand = buildDockerCommand(command, containerName);

    // Spawn the process
    const child = spawn('sh', ['-c', dockerCommand], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    runningJobs.set(jobId, { process: child, containerName });

    // Collect output
    let stdout = '';
    let stderr = '';

    child.stdout?.on('data', (data) => {
      stdout += data.toString();
      // Update progress periodically
      updateJobProgress(jobId, stdout);
    });

    child.stderr?.on('data', (data) => {
      stderr += data.toString();
    });

    child.on('close', async (code) => {
      runningJobs.delete(jobId);

      const status = code === 0 ? 'completed' : 'failed';
      const result = {
        exitCode: code,
        stdout: stdout.slice(-10000), // Keep last 10k chars
        stderr: stderr.slice(-5000),
      };

      await pool.query(
        `UPDATE jobs
         SET status = $1, completed_at = CURRENT_TIMESTAMP,
             result = $2, error_message = $3, updated_at = CURRENT_TIMESTAMP
         WHERE id = $4`,
        [
          status,
          JSON.stringify(result),
          code !== 0 ? stderr.slice(-1000) : null,
          jobId,
        ]
      );
    });

    child.on('error', async (error) => {
      runningJobs.delete(jobId);

      await pool.query(
        `UPDATE jobs
         SET status = 'failed', completed_at = CURRENT_TIMESTAMP,
             error_message = $1, updated_at = CURRENT_TIMESTAMP
         WHERE id = $2`,
        [error.message, jobId]
      );
    });

    return NextResponse.json({
      success: true,
      jobId,
      message: `Job ${jobType} started`,
    });
  } catch (error) {
    console.error('Error starting job:', error);
    return NextResponse.json(
      { error: 'Failed to start job' },
      { status: 500 }
    );
  }
}

// DELETE /api/admin/jobs - Cancel a running job
export async function DELETE(request: NextRequest) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const { searchParams } = new URL(request.url);
    const jobId = parseInt(searchParams.get('jobId') || '0');

    if (!jobId) {
      return NextResponse.json(
        { error: 'jobId is required' },
        { status: 400 }
      );
    }

    // Get the running job info
    const runningJob = runningJobs.get(jobId);
    if (runningJob) {
      // Stop the Docker container - this properly terminates the job
      try {
        await execAsync(`docker stop ${runningJob.containerName}`);
      } catch {
        // Container may already be stopped, that's ok
      }
      runningJob.process.kill('SIGTERM');
      runningJobs.delete(jobId);
    }

    // Update job status
    await pool.query(
      `UPDATE jobs
       SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP,
           error_message = 'Cancelled by user', updated_at = CURRENT_TIMESTAMP
       WHERE id = $1 AND status = 'running'`,
      [jobId]
    );

    return NextResponse.json({
      success: true,
      message: 'Job cancelled',
    });
  } catch (error) {
    console.error('Error cancelling job:', error);
    return NextResponse.json(
      { error: 'Failed to cancel job' },
      { status: 500 }
    );
  }
}

// Helper functions to build commands
function buildScrapeCommand(config: any): string {
  let cmd = 'python -m src.main scrape';
  if (config.startChapter) cmd += ` --start ${config.startChapter}`;
  if (config.endChapter) cmd += ` --end ${config.endChapter}`;
  if (config.maxChapters) cmd += ` --max ${config.maxChapters}`;
  return cmd;
}

function buildProcessAiCommand(config: any): string {
  let cmd = 'python -m src.main process-ai';
  if (config.startChapter) cmd += ` --start ${config.startChapter}`;
  if (config.endChapter) cmd += ` --end ${config.endChapter}`;
  if (config.chapter) cmd += ` --chapter ${config.chapter}`;
  if (config.dryRun) cmd += ' --dry-run';
  return cmd;
}

function buildExtractCharactersCommand(config: any): string {
  let cmd = 'python -m src.main extract-characters';
  if (config.startChapter) cmd += ` --start ${config.startChapter}`;
  if (config.endChapter) cmd += ` --end ${config.endChapter}`;
  if (config.chapter) cmd += ` --chapter ${config.chapter}`;
  if (config.dryRun) cmd += ' --dry-run';
  return cmd;
}

function buildAttributeEventsCommand(config: any): string {
  let cmd = 'python -m src.main attribute-events';
  if (config.startChapter) cmd += ` --start ${config.startChapter}`;
  if (config.endChapter) cmd += ` --end ${config.endChapter}`;
  if (config.chapter) cmd += ` --chapter ${config.chapter}`;
  if (config.dryRun) cmd += ' --dry-run';
  return cmd;
}

function buildBatchAttributeEventsCommand(config: any): string {
  let cmd = 'python -m src.main batch-attribute-events';
  if (config.startChapter) cmd += ` --start ${config.startChapter}`;
  if (config.endChapter) cmd += ` --end ${config.endChapter}`;
  if (config.dryRun) cmd += ' --dry-run';
  return cmd;
}

function buildDockerCommand(scraperCommand: string, containerName: string): string {
  // Run the scraper command in a new Docker container
  // Using docker-compose run to inherit environment and network settings
  // The compose file is mounted into the container at /app/docker-compose.prod.yml
  // Pass ANTHROPIC_API_KEY directly since the web container has it in env
  // Use --no-deps since postgres is already running, and -p to match the existing project name
  // Use --name so we can stop the container by name if cancelled
  const apiKey = process.env.ANTHROPIC_API_KEY || '';
  return `docker compose -p litrpg-status-screen -f /app/docker-compose.prod.yml run --rm --no-deps --name ${containerName} -e ANTHROPIC_API_KEY="${apiKey}" scraper ${scraperCommand}`;
}

async function updateJobProgress(jobId: number, output: string): Promise<void> {
  // Parse output to extract progress information
  // This is a simple implementation - can be enhanced based on scraper output format
  try {
    const lines = output.split('\n');
    const lastLines = lines.slice(-20);

    // Look for progress indicators in output
    let chaptersProcessed = 0;
    let eventsProcessed = 0;

    for (const line of lastLines) {
      // Look for patterns like "Chapter 5: 1.00" or "Processed 10 chapters"
      const chapterMatch = line.match(/[Cc]hapter\s+(\d+)/);
      if (chapterMatch) {
        chaptersProcessed = Math.max(chaptersProcessed, parseInt(chapterMatch[1]));
      }

      const eventsMatch = line.match(/(\d+)\s+events?/i);
      if (eventsMatch) {
        eventsProcessed = Math.max(eventsProcessed, parseInt(eventsMatch[1]));
      }
    }

    const progress = {
      chaptersProcessed,
      eventsProcessed,
      lastOutput: lastLines.join('\n').slice(-500),
    };

    await pool.query(
      `UPDATE jobs SET progress = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2`,
      [JSON.stringify(progress), jobId]
    );
  } catch (error) {
    // Ignore progress update errors
  }
}
