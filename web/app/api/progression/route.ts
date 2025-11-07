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

    // Get character progression: classes, levels, and abilities
    const query = `
      WITH progression_timeline AS (
        -- Get class acquisitions
        SELECT
          ch.order_index,
          ch.chapter_number,
          'class' as event_type,
          cc.class_name as name,
          NULL as level,
          cc.id as class_id
        FROM character_classes cc
        JOIN chapters ch ON cc.chapter_id = ch.id
        WHERE cc.character_id = $1
          ${maxOrderIndex ? 'AND ch.order_index <= $2' : ''}

        UNION ALL

        -- Get level ups
        SELECT
          ch.order_index,
          ch.chapter_number,
          'level' as event_type,
          cc.class_name as name,
          cl.level,
          cc.id as class_id
        FROM character_levels cl
        JOIN character_classes cc ON cl.character_class_id = cc.id
        JOIN chapters ch ON cl.chapter_id = ch.id
        WHERE cc.character_id = $1
          ${maxOrderIndex ? 'AND ch.order_index <= $2' : ''}

        UNION ALL

        -- Get abilities (skills, spells, conditions, aspects, titles, ranks, other)
        -- Preserve type information for display
        SELECT
          ch.order_index,
          ch.chapter_number,
          CASE
            WHEN a.type = 'spell' THEN 'spell'
            ELSE COALESCE(re.event_type, 'skill_obtained')
          END as event_type,
          a.name,
          NULL as level,
          ca.character_class_id as class_id
        FROM character_abilities ca
        JOIN abilities a ON ca.ability_id = a.id
        JOIN chapters ch ON ca.chapter_id = ch.id
        LEFT JOIN raw_events re ON ca.raw_event_id = re.id
        WHERE ca.character_id = $1
          ${maxOrderIndex ? 'AND ch.order_index <= $2' : ''}
      )
      SELECT * FROM progression_timeline
      ORDER BY order_index ASC,
               CASE event_type
                 WHEN 'class' THEN 1
                 WHEN 'level' THEN 2
                 ELSE 3
               END;
    `;

    const params = maxOrderIndex ? [characterId, maxOrderIndex] : [characterId];
    const result = await pool.query(query, params);

    // Group events by chapter
    const progressionByChapter: Record<string, any> = {};

    for (const event of result.rows) {
      const key = `${event.order_index}|${event.chapter_number}`;

      if (!progressionByChapter[key]) {
        progressionByChapter[key] = {
          order_index: event.order_index,
          chapter_number: event.chapter_number,
          classes: [],
          skills: [],
          spells: []
        };
      }

      if (event.event_type === 'class') {
        progressionByChapter[key].classes.push({
          name: event.name,
          level: null
        });
      } else if (event.event_type === 'level') {
        // Update or add class with level
        const existing = progressionByChapter[key].classes.find(
          (c: any) => c.name === event.name
        );
        if (existing) {
          existing.level = event.level;
        } else {
          progressionByChapter[key].classes.push({
            name: event.name,
            level: event.level
          });
        }
      } else {
        // All abilities (skills, spells, conditions, aspects, titles, ranks, other)
        // are grouped in "skills" array with type information
        progressionByChapter[key].skills.push({
          name: event.name,
          type: event.event_type
        });
      }
    }

    // Convert to array and sort
    const progression = Object.values(progressionByChapter).sort(
      (a: any, b: any) => a.order_index - b.order_index
    );

    return NextResponse.json(progression);
  } catch (error) {
    console.error('Error fetching character progression:', error);
    return NextResponse.json(
      { error: 'Failed to fetch character progression' },
      { status: 500 }
    );
  }
}
