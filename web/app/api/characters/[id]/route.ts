import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const characterId = parseInt(id);

    if (isNaN(characterId)) {
      return NextResponse.json(
        { error: 'Invalid character ID' },
        { status: 400 }
      );
    }

    const result = await pool.query(
      `SELECT id, name, aliases, first_appearance_chapter_id, notes, created_at
       FROM characters
       WHERE id = $1`,
      [characterId]
    );

    if (result.rows.length === 0) {
      return NextResponse.json(
        { error: 'Character not found' },
        { status: 404 }
      );
    }

    return NextResponse.json(result.rows[0]);
  } catch (error) {
    console.error('Error fetching character:', error);
    return NextResponse.json(
      { error: 'Failed to fetch character' },
      { status: 500 }
    );
  }
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const characterId = parseInt(id);

    if (isNaN(characterId)) {
      return NextResponse.json(
        { error: 'Invalid character ID' },
        { status: 400 }
      );
    }

    const body = await request.json();
    const { name, aliases, first_appearance_chapter_id, notes } = body;

    // Build dynamic update query
    const updates: string[] = [];
    const values: any[] = [];
    let paramIndex = 1;

    if (name !== undefined) {
      if (typeof name !== 'string' || name.trim() === '') {
        return NextResponse.json(
          { error: 'Name must be a non-empty string' },
          { status: 400 }
        );
      }
      updates.push(`name = $${paramIndex}`);
      values.push(name.trim());
      paramIndex++;
    }

    if (aliases !== undefined) {
      if (!Array.isArray(aliases)) {
        return NextResponse.json(
          { error: 'Aliases must be an array' },
          { status: 400 }
        );
      }
      updates.push(`aliases = $${paramIndex}`);
      values.push(aliases.filter((a: any) => typeof a === 'string' && a.trim() !== '').map((a: string) => a.trim()));
      paramIndex++;
    }

    if (first_appearance_chapter_id !== undefined) {
      if (first_appearance_chapter_id !== null && typeof first_appearance_chapter_id !== 'number') {
        return NextResponse.json(
          { error: 'first_appearance_chapter_id must be a number or null' },
          { status: 400 }
        );
      }
      updates.push(`first_appearance_chapter_id = $${paramIndex}`);
      values.push(first_appearance_chapter_id);
      paramIndex++;
    }

    if (notes !== undefined) {
      if (notes !== null && typeof notes !== 'string') {
        return NextResponse.json(
          { error: 'Notes must be a string or null' },
          { status: 400 }
        );
      }
      updates.push(`notes = $${paramIndex}`);
      values.push(notes);
      paramIndex++;
    }

    if (updates.length === 0) {
      return NextResponse.json(
        { error: 'No valid fields to update' },
        { status: 400 }
      );
    }

    values.push(characterId);

    const result = await pool.query(
      `UPDATE characters
       SET ${updates.join(', ')}
       WHERE id = $${paramIndex}
       RETURNING id, name, aliases, first_appearance_chapter_id, notes, created_at`,
      values
    );

    if (result.rows.length === 0) {
      return NextResponse.json(
        { error: 'Character not found' },
        { status: 404 }
      );
    }

    return NextResponse.json(result.rows[0]);
  } catch (error: any) {
    console.error('Error updating character:', error);

    // Handle unique constraint violation
    if (error.code === '23505') {
      return NextResponse.json(
        { error: 'A character with this name already exists' },
        { status: 409 }
      );
    }

    return NextResponse.json(
      { error: 'Failed to update character' },
      { status: 500 }
    );
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const characterId = parseInt(id);

    if (isNaN(characterId)) {
      return NextResponse.json(
        { error: 'Invalid character ID' },
        { status: 400 }
      );
    }

    // Check if character has any progression data
    const progressionCheck = await pool.query(
      `SELECT
        (SELECT COUNT(*) FROM character_classes WHERE character_id = $1) as classes,
        (SELECT COUNT(*) FROM character_abilities WHERE character_id = $1) as abilities,
        (SELECT COUNT(*) FROM raw_events WHERE character_id = $1) as events`,
      [characterId]
    );

    const { classes, abilities, events } = progressionCheck.rows[0];
    const totalLinkedData = parseInt(classes) + parseInt(abilities) + parseInt(events);

    if (totalLinkedData > 0) {
      return NextResponse.json(
        {
          error: 'Cannot delete character with linked data',
          details: {
            classes: parseInt(classes),
            abilities: parseInt(abilities),
            events: parseInt(events)
          }
        },
        { status: 409 }
      );
    }

    const result = await pool.query(
      'DELETE FROM characters WHERE id = $1 RETURNING id, name',
      [characterId]
    );

    if (result.rows.length === 0) {
      return NextResponse.json(
        { error: 'Character not found' },
        { status: 404 }
      );
    }

    return NextResponse.json({
      success: true,
      deleted: result.rows[0]
    });
  } catch (error) {
    console.error('Error deleting character:', error);
    return NextResponse.json(
      { error: 'Failed to delete character' },
      { status: 500 }
    );
  }
}
