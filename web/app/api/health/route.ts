import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function GET() {
  try {
    const result = await pool.query('SELECT NOW()');
    return NextResponse.json({
      status: 'ok',
      database: 'connected',
      timestamp: result.rows[0].now,
    });
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    const errorStack = error instanceof Error ? error.stack : '';
    console.error('Health check failed:', errorMessage, errorStack);
    return NextResponse.json(
      {
        status: 'error',
        database: 'disconnected',
        error: errorMessage,
        details: errorStack,
      },
      { status: 500 }
    );
  }
}
