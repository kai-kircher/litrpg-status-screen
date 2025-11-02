import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const characterId = searchParams.get('characterId');
    const maxOrderIndex = searchParams.get('maxOrderIndex');

    if (!characterId) {
      return NextResponse.json(
        { error: 'characterId is required' },
        { status: 400 }
      );
    }

    // Get highest level for each class
    const classQuery = `
      WITH latest_classes AS (
        SELECT DISTINCT ON (cc.class_name)
          cc.class_name,
          cl.level,
          c.chapter_number
        FROM character_classes cc
        LEFT JOIN character_levels cl ON cc.id = cl.character_class_id
        LEFT JOIN chapters c ON cl.chapter_id = c.id
        WHERE cc.character_id = $1
          ${maxOrderIndex ? 'AND c.order_index <= $2' : ''}
          AND cc.is_active = true
        ORDER BY cc.class_name, cl.level DESC NULLS LAST, c.order_index DESC
      )
      SELECT class_name, level, chapter_number
      FROM latest_classes
      ORDER BY class_name ASC
    `;

    const classParams = maxOrderIndex ? [characterId, maxOrderIndex] : [characterId];
    const classResult = await pool.query(classQuery, classParams);

    // Get all unique skills
    const skillQuery = `
      SELECT DISTINCT a.name, a.type
      FROM character_abilities ca
      JOIN abilities a ON ca.ability_id = a.id
      JOIN chapters c ON ca.chapter_id = c.id
      WHERE ca.character_id = $1
        ${maxOrderIndex ? 'AND c.order_index <= $2' : ''}
        AND a.type = 'skill'
      ORDER BY a.name ASC
    `;

    const skillParams = maxOrderIndex ? [characterId, maxOrderIndex] : [characterId];
    const skillResult = await pool.query(skillQuery, skillParams);

    // Get all unique spells
    const spellQuery = `
      SELECT DISTINCT a.name, a.type
      FROM character_abilities ca
      JOIN abilities a ON ca.ability_id = a.id
      JOIN chapters c ON ca.chapter_id = c.id
      WHERE ca.character_id = $1
        ${maxOrderIndex ? 'AND c.order_index <= $2' : ''}
        AND a.type = 'spell'
      ORDER BY a.name ASC
    `;

    const spellParams = maxOrderIndex ? [characterId, maxOrderIndex] : [characterId];
    const spellResult = await pool.query(spellQuery, spellParams);

    return NextResponse.json({
      classes: classResult.rows,
      skills: skillResult.rows.map(r => r.name),
      spells: spellResult.rows.map(r => r.name),
    });
  } catch (error) {
    console.error('Error fetching character summary:', error);
    return NextResponse.json(
      { error: 'Failed to fetch character summary' },
      { status: 500 }
    );
  }
}
