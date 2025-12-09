import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const search = searchParams.get('search');
    const limit = searchParams.get('limit');

    let query = `
      SELECT id, name, aliases, species, status, wiki_url, first_appearance_chapter_id, scraped_at as created_at
      FROM wiki_characters
    `;

    const params: any[] = [];
    let paramIndex = 1;

    if (search) {
      query += ` WHERE LOWER(name) LIKE LOWER($${paramIndex})`;
      params.push(`%${search}%`);
      paramIndex++;
    }

    query += ` ORDER BY name ASC`;

    if (limit) {
      query += ` LIMIT $${paramIndex}`;
      params.push(parseInt(limit));
    }

    const result = await pool.query(query, params);

    return NextResponse.json(result.rows);
  } catch (error) {
    console.error('Error fetching characters:', error);
    return NextResponse.json(
      { error: 'Failed to fetch characters' },
      { status: 500 }
    );
  }
}

export async function POST() {
  // Characters are sourced from the wiki - manual creation is no longer supported
  return NextResponse.json(
    { error: 'Characters are managed via wiki scraping. Manual creation is disabled.' },
    { status: 403 }
  );
}
