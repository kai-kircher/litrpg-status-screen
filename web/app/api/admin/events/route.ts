import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = parseInt(searchParams.get('limit') || '50');
    const offset = parseInt(searchParams.get('offset') || '0');
    const eventType = searchParams.get('type');
    const assigned = searchParams.get('assigned');

    let query = `
      SELECT
        re.id,
        re.event_type,
        re.raw_text,
        re.parsed_data,
        re.context,
        re.is_assigned,
        re.character_id,
        c.order_index,
        c.chapter_number,
        c.chapter_title,
        ch.name as character_name,
        re.created_at
      FROM raw_events re
      JOIN chapters c ON re.chapter_id = c.id
      LEFT JOIN characters ch ON re.character_id = ch.id
      WHERE 1=1
    `;

    const params: any[] = [];
    let paramIndex = 1;

    if (assigned !== null) {
      query += ` AND re.is_assigned = $${paramIndex}`;
      params.push(assigned === 'true');
      paramIndex++;
    }

    if (eventType) {
      query += ` AND re.event_type = $${paramIndex}`;
      params.push(eventType);
      paramIndex++;
    }

    query += ` ORDER BY c.chapter_number ASC, re.id ASC`;
    query += ` LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`;
    params.push(limit, offset);

    const result = await pool.query(query, params);

    // Get total count
    let countQuery = 'SELECT COUNT(*) FROM raw_events re WHERE 1=1';
    const countParams: any[] = [];
    let countParamIndex = 1;

    if (assigned !== null) {
      countQuery += ` AND re.is_assigned = $${countParamIndex}`;
      countParams.push(assigned === 'true');
      countParamIndex++;
    }

    if (eventType) {
      countQuery += ` AND re.event_type = $${countParamIndex}`;
      countParams.push(eventType);
    }

    const countResult = await pool.query(countQuery, countParams);
    const total = parseInt(countResult.rows[0].count);

    return NextResponse.json({
      events: result.rows,
      total,
      limit,
      offset,
    });
  } catch (error) {
    console.error('Error fetching raw events:', error);
    return NextResponse.json(
      { error: 'Failed to fetch raw events' },
      { status: 500 }
    );
  }
}
