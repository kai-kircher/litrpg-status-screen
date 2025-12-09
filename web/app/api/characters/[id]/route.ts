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
      `SELECT id, name, aliases, species, status, wiki_url, first_appearance_chapter_id, scraped_at as created_at
       FROM wiki_characters
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

export async function PATCH() {
  // Characters are sourced from the wiki - manual editing is no longer supported
  return NextResponse.json(
    { error: 'Characters are managed via wiki scraping. Manual editing is disabled.' },
    { status: 403 }
  );
}

export async function DELETE() {
  // Characters are sourced from the wiki - deletion is no longer supported
  return NextResponse.json(
    { error: 'Characters are managed via wiki scraping. Deletion is disabled.' },
    { status: 403 }
  );
}
