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

    // Get all unique skills, excluding those that were removed/changed/consolidated
    const skillQuery = `
      WITH skill_acquisitions AS (
        SELECT DISTINCT
          a.id as ability_id,
          a.name,
          ca.chapter_id,
          c.order_index as acquired_at
        FROM character_abilities ca
        JOIN abilities a ON ca.ability_id = a.id
        JOIN chapters c ON ca.chapter_id = c.id
        WHERE ca.character_id = $1
          ${maxOrderIndex ? 'AND c.order_index <= $2' : ''}
          AND a.type = 'skill'
      ),
      skill_removals AS (
        SELECT DISTINCT
          LOWER(TRIM(re.parsed_data->>'skill_name')) as skill_name,
          c.order_index as removed_at
        FROM raw_events re
        JOIN chapters c ON re.chapter_id = c.id
        WHERE re.character_id = $1
          ${maxOrderIndex ? 'AND c.order_index <= $2' : ''}
          AND re.event_type IN ('skill_removed', 'skill_change', 'skill_consolidation')
          AND re.is_processed = true
      )
      SELECT sa.name
      FROM skill_acquisitions sa
      LEFT JOIN skill_removals sr
        ON LOWER(TRIM(sa.name)) = sr.skill_name
        AND sr.removed_at >= sa.acquired_at
      WHERE sr.skill_name IS NULL
      ORDER BY sa.name ASC
    `;

    const skillParams = maxOrderIndex ? [characterId, maxOrderIndex] : [characterId];
    const skillResult = await pool.query(skillQuery, skillParams);

    // Get all unique spells, excluding those that were removed
    const spellQuery = `
      WITH spell_acquisitions AS (
        SELECT DISTINCT
          a.id as ability_id,
          a.name,
          ca.chapter_id,
          c.order_index as acquired_at
        FROM character_abilities ca
        JOIN abilities a ON ca.ability_id = a.id
        JOIN chapters c ON ca.chapter_id = c.id
        WHERE ca.character_id = $1
          ${maxOrderIndex ? 'AND c.order_index <= $2' : ''}
          AND a.type = 'spell'
      ),
      spell_removals AS (
        SELECT DISTINCT
          LOWER(TRIM(re.parsed_data->>'spell_name')) as spell_name,
          c.order_index as removed_at
        FROM raw_events re
        JOIN chapters c ON re.chapter_id = c.id
        WHERE re.character_id = $1
          ${maxOrderIndex ? 'AND c.order_index <= $2' : ''}
          AND re.event_type = 'spell_removed'
          AND re.is_processed = true
      )
      SELECT sa.name
      FROM spell_acquisitions sa
      LEFT JOIN spell_removals sr
        ON LOWER(TRIM(sa.name)) = sr.spell_name
        AND sr.removed_at >= sa.acquired_at
      WHERE sr.spell_name IS NULL
      ORDER BY sa.name ASC
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
