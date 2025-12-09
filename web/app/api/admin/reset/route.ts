import { NextRequest, NextResponse } from 'next/server';
import pool from '@/lib/db';

// Simple API key auth - set ADMIN_API_KEY env var
function isAuthorized(request: NextRequest): boolean {
  const apiKey = process.env.ADMIN_API_KEY;
  if (!apiKey) return true; // No auth configured, allow all

  const authHeader = request.headers.get('authorization');
  if (!authHeader) return false;

  const [type, token] = authHeader.split(' ');
  return type === 'Bearer' && token === apiKey;
}

// POST /api/admin/reset - Reset various data
export async function POST(request: NextRequest) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const { action } = await request.json();

    switch (action) {
      case 'unassign-all-events': {
        // Unassign all events (set character_id to null, is_assigned to false)
        // but keep is_processed status to avoid re-processing already processed events
        const result = await pool.query(
          `UPDATE raw_events
           SET character_id = NULL, is_assigned = false
           WHERE is_assigned = true
           RETURNING id`
        );

        return NextResponse.json({
          success: true,
          message: `Unassigned ${result.rowCount} events`,
          count: result.rowCount,
        });
      }

      case 'clear-progression-data': {
        // Unassign all events from characters
        await pool.query(
          `UPDATE raw_events
           SET character_id = NULL, is_assigned = false
           WHERE character_id IS NOT NULL`
        );

        // Delete character abilities
        const abilitiesResult = await pool.query(
          `DELETE FROM character_abilities RETURNING id`
        );

        // Delete character levels
        const levelsResult = await pool.query(
          `DELETE FROM character_levels RETURNING id`
        );

        // Delete character classes
        const classesResult = await pool.query(
          `DELETE FROM character_classes RETURNING id`
        );

        // Note: wiki_characters are not deleted - they are sourced from the wiki

        return NextResponse.json({
          success: true,
          message: `Cleared progression data`,
          details: {
            classes: classesResult.rowCount,
            levels: levelsResult.rowCount,
            abilities: abilitiesResult.rowCount,
          },
        });
      }

      case 'reset-processed-events': {
        // Reset is_processed flag on all events so they can be re-processed
        const result = await pool.query(
          `UPDATE raw_events
           SET is_processed = false
           WHERE is_processed = true
           RETURNING id`
        );

        return NextResponse.json({
          success: true,
          message: `Reset ${result.rowCount} processed events`,
          count: result.rowCount,
        });
      }

      case 'full-reset': {
        // Complete reset: clear all progression data, unassign and unprocess all events

        // Unassign and unprocess all events
        const eventsResult = await pool.query(
          `UPDATE raw_events
           SET character_id = NULL, is_assigned = false, is_processed = false
           RETURNING id`
        );

        // Delete all character progression data
        const abilitiesResult = await pool.query(`DELETE FROM character_abilities RETURNING id`);
        const levelsResult = await pool.query(`DELETE FROM character_levels RETURNING id`);
        const classesResult = await pool.query(`DELETE FROM character_classes RETURNING id`);

        // Note: wiki_characters are not deleted - they are sourced from the wiki

        return NextResponse.json({
          success: true,
          message: `Full reset complete`,
          details: {
            eventsReset: eventsResult.rowCount,
            classesDeleted: classesResult.rowCount,
            levelsDeleted: levelsResult.rowCount,
            abilitiesDeleted: abilitiesResult.rowCount,
          },
        });
      }

      default:
        return NextResponse.json(
          { error: `Unknown action: ${action}` },
          { status: 400 }
        );
    }
  } catch (error) {
    console.error('Error performing reset:', error);
    return NextResponse.json(
      { error: 'Failed to perform reset' },
      { status: 500 }
    );
  }
}
