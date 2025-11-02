import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function POST(request: Request) {
  try {
    const { eventId, eventIds, characterId } = await request.json();

    if ((!eventId && !eventIds) || !characterId) {
      return NextResponse.json(
        { error: 'eventId(s) and characterId are required' },
        { status: 400 }
      );
    }

    // Handle batch assignment
    if (eventIds && Array.isArray(eventIds)) {
      const result = await pool.query(
        `UPDATE raw_events
         SET character_id = $1, is_assigned = true
         WHERE id = ANY($2)
         RETURNING *`,
        [characterId, eventIds]
      );

      return NextResponse.json({
        success: true,
        count: result.rowCount,
        events: result.rows,
      });
    }

    // Handle single assignment (backwards compatibility)
    const result = await pool.query(
      `UPDATE raw_events
       SET character_id = $1, is_assigned = true
       WHERE id = $2
       RETURNING *`,
      [characterId, eventId]
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
    console.error('Error assigning event:', error);
    return NextResponse.json(
      { error: 'Failed to assign event' },
      { status: 500 }
    );
  }
}

// Unassign an event
export async function DELETE(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const eventId = searchParams.get('eventId');

    if (!eventId) {
      return NextResponse.json(
        { error: 'eventId is required' },
        { status: 400 }
      );
    }

    const result = await pool.query(
      `UPDATE raw_events
       SET character_id = NULL, is_assigned = false
       WHERE id = $1
       RETURNING *`,
      [eventId]
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
    console.error('Error unassigning event:', error);
    return NextResponse.json(
      { error: 'Failed to unassign event' },
      { status: 500 }
    );
  }
}
