import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function POST(request: Request) {
  const client = await pool.connect();

  try {
    const { eventId } = await request.json();

    if (!eventId) {
      return NextResponse.json(
        { error: 'eventId is required' },
        { status: 400 }
      );
    }

    await client.query('BEGIN');

    // Get the raw event
    const eventResult = await client.query(
      `SELECT re.*, c.order_index, c.chapter_number, c.id as chapter_db_id
       FROM raw_events re
       JOIN chapters c ON re.chapter_id = c.id
       WHERE re.id = $1`,
      [eventId]
    );

    if (eventResult.rows.length === 0) {
      await client.query('ROLLBACK');
      return NextResponse.json(
        { error: 'Event not found' },
        { status: 404 }
      );
    }

    const event = eventResult.rows[0];

    if (!event.is_assigned || !event.character_id) {
      await client.query('ROLLBACK');
      return NextResponse.json(
        { error: 'Event must be assigned to a character first' },
        { status: 400 }
      );
    }

    // Process based on event type
    let result;
    switch (event.event_type) {
      case 'class_obtained':
        result = await processClassObtained(client, event);
        break;
      case 'level_up':
        result = await processLevelUp(client, event);
        break;
      case 'skill_obtained':
        result = await processAbility(client, event, 'skill');
        break;
      case 'spell_obtained':
        result = await processAbility(client, event, 'spell');
        break;
      default:
        await client.query('ROLLBACK');
        return NextResponse.json(
          { error: `Unknown event type: ${event.event_type}` },
          { status: 400 }
        );
    }

    // Mark event as processed
    await client.query(
      'UPDATE raw_events SET is_processed = true WHERE id = $1',
      [eventId]
    );

    await client.query('COMMIT');

    return NextResponse.json({
      success: true,
      message: `Processed ${event.event_type}`,
      data: result,
    });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Error processing event:', error);
    return NextResponse.json(
      { error: 'Failed to process event', details: (error as Error).message },
      { status: 500 }
    );
  } finally {
    client.release();
  }
}

async function processClassObtained(client: any, event: any) {
  const className = event.parsed_data?.class_name || extractClassName(event.raw_text);

  if (!className) {
    throw new Error('Could not extract class name from event');
  }

  // Insert into character_classes
  const result = await client.query(
    `INSERT INTO character_classes
     (character_id, class_name, chapter_id, raw_event_id, is_active)
     VALUES ($1, $2, $3, $4, true)
     ON CONFLICT (character_id, class_name, chapter_id) DO UPDATE
     SET raw_event_id = $4, is_active = true
     RETURNING *`,
    [event.character_id, className, event.chapter_id, event.id]
  );

  return { character_class: result.rows[0] };
}

async function processLevelUp(client: any, event: any) {
  const className = event.parsed_data?.class_name || extractClassName(event.raw_text);
  const level = event.parsed_data?.level || extractLevel(event.raw_text);

  if (!className || !level) {
    throw new Error('Could not extract class name or level from event');
  }

  // Find or create the character class
  let classResult = await client.query(
    `SELECT id FROM character_classes
     WHERE character_id = $1 AND class_name = $2
     ORDER BY chapter_id DESC
     LIMIT 1`,
    [event.character_id, className]
  );

  let characterClassId;
  if (classResult.rows.length === 0) {
    // Create the class if it doesn't exist
    const newClass = await client.query(
      `INSERT INTO character_classes
       (character_id, class_name, chapter_id, is_active)
       VALUES ($1, $2, $3, true)
       RETURNING id`,
      [event.character_id, className, event.chapter_id]
    );
    characterClassId = newClass.rows[0].id;
  } else {
    characterClassId = classResult.rows[0].id;
  }

  // Insert the level
  const levelResult = await client.query(
    `INSERT INTO character_levels
     (character_class_id, level, chapter_id, raw_event_id)
     VALUES ($1, $2, $3, $4)
     ON CONFLICT (character_class_id, chapter_id, level) DO UPDATE
     SET raw_event_id = $4
     RETURNING *`,
    [characterClassId, level, event.chapter_id, event.id]
  );

  return { character_level: levelResult.rows[0], character_class_id: characterClassId };
}

async function processAbility(client: any, event: any, type: 'skill' | 'spell') {
  const abilityName = event.parsed_data?.ability_name ||
                      event.parsed_data?.skill_name ||
                      event.parsed_data?.spell_name ||
                      extractAbilityName(event.raw_text);

  if (!abilityName) {
    throw new Error(`Could not extract ${type} name from event`);
  }

  const normalizedName = abilityName.toLowerCase().trim();

  // Insert or get the ability
  const abilityResult = await client.query(
    `INSERT INTO abilities (name, type, normalized_name, first_seen_chapter_id)
     VALUES ($1, $2, $3, $4)
     ON CONFLICT (normalized_name, type) DO UPDATE
     SET name = EXCLUDED.name
     RETURNING id`,
    [abilityName, type, normalizedName, event.chapter_id]
  );

  const abilityId = abilityResult.rows[0].id;

  // Find the most recent active class for this character (if any)
  const classResult = await client.query(
    `SELECT id FROM character_classes
     WHERE character_id = $1 AND is_active = true
     ORDER BY chapter_id DESC
     LIMIT 1`,
    [event.character_id]
  );

  const characterClassId = classResult.rows.length > 0 ? classResult.rows[0].id : null;

  // Get the current level if we have a class
  let levelAtAcquisition = null;
  if (characterClassId) {
    const levelResult = await client.query(
      `SELECT level FROM character_levels
       WHERE character_class_id = $1 AND chapter_id <= $2
       ORDER BY chapter_id DESC, level DESC
       LIMIT 1`,
      [characterClassId, event.chapter_id]
    );
    if (levelResult.rows.length > 0) {
      levelAtAcquisition = levelResult.rows[0].level;
    }
  }

  // Insert character ability
  const characterAbilityResult = await client.query(
    `INSERT INTO character_abilities
     (character_id, ability_id, chapter_id, character_class_id, level_at_acquisition, raw_event_id, acquisition_method)
     VALUES ($1, $2, $3, $4, $5, $6, 'level_up')
     ON CONFLICT (character_id, ability_id, chapter_id) DO UPDATE
     SET raw_event_id = $6, character_class_id = $4, level_at_acquisition = $5
     RETURNING *`,
    [event.character_id, abilityId, event.chapter_id, characterClassId, levelAtAcquisition, event.id]
  );

  return {
    ability: { id: abilityId, name: abilityName, type },
    character_ability: characterAbilityResult.rows[0]
  };
}

// Helper functions to extract data from raw text
function extractClassName(rawText: string): string | null {
  // Pattern: [Class Name class obtained!] or [Class Name level X!]
  const classMatch = rawText.match(/\[([^\]]+?)\s+(?:class|level)/i);
  return classMatch ? classMatch[1].trim() : null;
}

function extractLevel(rawText: string): number | null {
  // Pattern: [Class Name level X!]
  const levelMatch = rawText.match(/level\s+(\d+)/i);
  return levelMatch ? parseInt(levelMatch[1]) : null;
}

function extractAbilityName(rawText: string): string | null {
  // Pattern: [Skill - Ability Name obtained!] or [Spell - Ability Name obtained!]
  const abilityMatch = rawText.match(/\[(?:Skill|Spell)\s*[-–—:]\s*([^\]]+?)\s+obtained/i);
  return abilityMatch ? abilityMatch[1].trim() : null;
}
