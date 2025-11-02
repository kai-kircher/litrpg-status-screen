import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function GET() {
  try {
    const result = await pool.query(`
      SELECT
        id,
        order_index,
        chapter_number,
        chapter_title,
        url,
        published_at,
        scraped_at
      FROM chapters
      ORDER BY order_index ASC
      LIMIT 100
    `);

    return NextResponse.json(result.rows);
  } catch (error) {
    console.error('Error fetching chapters:', error);
    return NextResponse.json(
      { error: 'Failed to fetch chapters' },
      { status: 500 }
    );
  }
}
