import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = parseInt(searchParams.get('limit') || '50');
    const offset = parseInt(searchParams.get('offset') || '0');
    const eventType = searchParams.get('type');
    const assigned = searchParams.get('assigned');
    const processed = searchParams.get('processed');
    const search = searchParams.get('search');
    const archived = searchParams.get('archived');

    let query = `
      SELECT
        re.id,
        re.event_type,
        re.raw_text,
        re.parsed_data,
        re.context,
        re.is_assigned,
        re.is_processed,
        re.character_id,
        re.archived,
        c.order_index,
        c.chapter_number,
        c.chapter_title,
        ch.name as character_name,
        re.created_at
      FROM raw_events re
      JOIN chapters c ON re.chapter_id = c.id
      LEFT JOIN wiki_characters ch ON re.character_id = ch.id
      WHERE 1=1
    `;

    const params: any[] = [];
    let paramIndex = 1;

    // Filter out archived events by default unless explicitly requesting them
    if (archived === 'true') {
      query += ` AND re.archived = TRUE`;
    } else if (archived === 'false' || archived === null) {
      query += ` AND re.archived = FALSE`;
    }
    // If archived === 'all', no filter is applied

    if (assigned !== null) {
      query += ` AND re.is_assigned = $${paramIndex}`;
      params.push(assigned === 'true');
      paramIndex++;
    }

    if (processed !== null) {
      query += ` AND re.is_processed = $${paramIndex}`;
      params.push(processed === 'true');
      paramIndex++;
    }

    if (eventType) {
      query += ` AND re.event_type = $${paramIndex}`;
      params.push(eventType);
      paramIndex++;
    }

    if (search) {
      query += ` AND (
        LOWER(re.raw_text) LIKE LOWER($${paramIndex}) OR
        LOWER(c.chapter_number) LIKE LOWER($${paramIndex}) OR
        LOWER(re.event_type) LIKE LOWER($${paramIndex}) OR
        LOWER(ch.name) LIKE LOWER($${paramIndex})
      )`;
      params.push(`%${search}%`);
      paramIndex++;
    }

    query += ` ORDER BY c.order_index ASC, re.id ASC`;
    query += ` LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`;
    params.push(limit, offset);

    const result = await pool.query(query, params);

    // Get total count
    let countQuery = `
      SELECT COUNT(*)
      FROM raw_events re
      JOIN chapters c ON re.chapter_id = c.id
      LEFT JOIN wiki_characters ch ON re.character_id = ch.id
      WHERE 1=1
    `;
    const countParams: any[] = [];
    let countParamIndex = 1;

    // Apply same archived filter to count
    if (archived === 'true') {
      countQuery += ` AND re.archived = TRUE`;
    } else if (archived === 'false' || archived === null) {
      countQuery += ` AND re.archived = FALSE`;
    }

    if (assigned !== null) {
      countQuery += ` AND re.is_assigned = $${countParamIndex}`;
      countParams.push(assigned === 'true');
      countParamIndex++;
    }

    if (processed !== null) {
      countQuery += ` AND re.is_processed = $${countParamIndex}`;
      countParams.push(processed === 'true');
      countParamIndex++;
    }

    if (eventType) {
      countQuery += ` AND re.event_type = $${countParamIndex}`;
      countParams.push(eventType);
      countParamIndex++;
    }

    if (search) {
      countQuery += ` AND (
        LOWER(re.raw_text) LIKE LOWER($${countParamIndex}) OR
        LOWER(c.chapter_number) LIKE LOWER($${countParamIndex}) OR
        LOWER(re.event_type) LIKE LOWER($${countParamIndex}) OR
        LOWER(ch.name) LIKE LOWER($${countParamIndex})
      )`;
      countParams.push(`%${search}%`);
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
