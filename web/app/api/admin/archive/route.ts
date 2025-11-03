import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function POST(request: Request) {
  try {
    const { eventId, eventIds } = await request.json();

    if (!eventId && (!eventIds || eventIds.length === 0)) {
      return NextResponse.json(
        { error: 'Event ID(s) required' },
        { status: 400 }
      );
    }

    const client = await pool.connect();

    try {
      await client.query('BEGIN');

      if (eventIds && eventIds.length > 0) {
        // Batch archive
        await client.query(
          'UPDATE raw_events SET archived = TRUE WHERE id = ANY($1)',
          [eventIds]
        );
        await client.query('COMMIT');

        return NextResponse.json({
          success: true,
          count: eventIds.length,
          message: `Archived ${eventIds.length} event(s)`,
        });
      } else {
        // Single archive
        await client.query(
          'UPDATE raw_events SET archived = TRUE WHERE id = $1',
          [eventId]
        );
        await client.query('COMMIT');

        return NextResponse.json({
          success: true,
          message: 'Event archived successfully',
        });
      }
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  } catch (error) {
    console.error('Error archiving event:', error);
    return NextResponse.json(
      { error: 'Failed to archive event' },
      { status: 500 }
    );
  }
}

export async function DELETE(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const eventId = searchParams.get('eventId');
    const eventIdsParam = searchParams.get('eventIds');

    if (!eventId && !eventIdsParam) {
      return NextResponse.json(
        { error: 'Event ID(s) required' },
        { status: 400 }
      );
    }

    const client = await pool.connect();

    try {
      await client.query('BEGIN');

      if (eventIdsParam) {
        // Batch unarchive
        const eventIds = eventIdsParam.split(',').map(id => parseInt(id));
        await client.query(
          'UPDATE raw_events SET archived = FALSE WHERE id = ANY($1)',
          [eventIds]
        );
        await client.query('COMMIT');

        return NextResponse.json({
          success: true,
          count: eventIds.length,
          message: `Unarchived ${eventIds.length} event(s)`,
        });
      } else {
        // Single unarchive
        await client.query(
          'UPDATE raw_events SET archived = FALSE WHERE id = $1',
          [parseInt(eventId!)]
        );
        await client.query('COMMIT');

        return NextResponse.json({
          success: true,
          message: 'Event unarchived successfully',
        });
      }
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  } catch (error) {
    console.error('Error unarchiving event:', error);
    return NextResponse.json(
      { error: 'Failed to unarchive event' },
      { status: 500 }
    );
  }
}
