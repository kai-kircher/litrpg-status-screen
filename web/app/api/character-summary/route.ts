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

    // Get all unique abilities (skills, spells, conditions, aspects, titles, ranks, other)
    // Bundle everything that's not a class into "skills" array, but preserve type information
    const abilityQuery = `
      WITH ability_acquisitions AS (
        SELECT DISTINCT
          a.id as ability_id,
          a.name,
          CASE
            WHEN a.type = 'spell' THEN 'spell'
            ELSE re.event_type
          END as display_type,
          ca.chapter_id,
          c.order_index as acquired_at
        FROM character_abilities ca
        JOIN abilities a ON ca.ability_id = a.id
        JOIN chapters c ON ca.chapter_id = c.id
        LEFT JOIN raw_events re ON ca.raw_event_id = re.id
        WHERE ca.character_id = $1
          ${maxOrderIndex ? 'AND c.order_index <= $2' : ''}
      ),
      ability_removals AS (
        SELECT DISTINCT
          COALESCE(
            LOWER(TRIM(re.parsed_data->>'skill_name')),
            LOWER(TRIM(re.parsed_data->>'spell_name')),
            LOWER(TRIM(re.parsed_data->>'name')),
            LOWER(TRIM(re.parsed_data->>'ability_name'))
          ) as ability_name,
          c.order_index as removed_at
        FROM raw_events re
        JOIN chapters c ON re.chapter_id = c.id
        WHERE re.character_id = $1
          ${maxOrderIndex ? 'AND c.order_index <= $2' : ''}
          AND re.event_type IN ('skill_removed', 'skill_change', 'skill_consolidation', 'spell_removed')
          AND re.is_processed = true
      )
      SELECT aa.name, COALESCE(aa.display_type, 'skill_obtained') as type
      FROM ability_acquisitions aa
      LEFT JOIN ability_removals ar
        ON LOWER(TRIM(aa.name)) = ar.ability_name
        AND ar.removed_at >= aa.acquired_at
      WHERE ar.ability_name IS NULL
      ORDER BY aa.name ASC
    `;

    const abilityParams = maxOrderIndex ? [characterId, maxOrderIndex] : [characterId];
    const abilityResult = await pool.query(abilityQuery, abilityParams);

    return NextResponse.json({
      classes: classResult.rows,
      skills: abilityResult.rows.map(r => ({ name: r.name, type: r.type })),
      spells: [], // Keep for backwards compatibility but empty
    });
  } catch (error) {
    console.error('Error fetching character summary:', error);
    return NextResponse.json(
      { error: 'Failed to fetch character summary' },
      { status: 500 }
    );
  }
}
