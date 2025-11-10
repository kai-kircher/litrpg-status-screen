import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function POST(request: Request) {
  try {
    const { eventId, eventType, title } = await request.json();

    if (!eventId || !eventType) {
      return NextResponse.json(
        { error: 'eventId and eventType are required' },
        { status: 400 }
      );
    }

    // Update the event with classification
    const parsedData = title ? { title } : null;

    const result = await pool.query(
      `UPDATE raw_events
       SET event_type = $1, parsed_data = $2
       WHERE id = $3
       RETURNING *`,
      [eventType, parsedData ? JSON.stringify(parsedData) : null, eventId]
    );

    if (result.rowCount === 0) {
      return NextResponse.json(
        { error: 'Event not found' },
        { status: 404 }
      );
    }

    return NextResponse.json({
      success: true,
      event: result.rows[0],
    });
  } catch (error) {
    console.error('Error classifying event:', error);
    return NextResponse.json(
      { error: 'Failed to classify event' },
      { status: 500 }
    );
  }
}
