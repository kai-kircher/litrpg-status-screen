import { NextResponse } from 'next/server';
import pool from '@/lib/db';

export async function POST(request: Request) {
  const client = await pool.connect();

  try {
    const { eventId, eventIds } = await request.json();

    // Support both single event and batch processing
    const idsToProcess = eventIds ? eventIds : (eventId ? [eventId] : []);

    if (idsToProcess.length === 0) {
      return NextResponse.json(
        { error: 'eventId or eventIds is required' },
        { status: 400 }
      );
    }

    await client.query('BEGIN');

    // Get all events to process
    const eventResult = await client.query(
      `SELECT re.*, c.order_index, c.chapter_number, c.id as chapter_db_id
       FROM raw_events re
       JOIN chapters c ON re.chapter_id = c.id
       WHERE re.id = ANY($1)
       ORDER BY c.order_index, re.id`,
      [idsToProcess]
    );

    if (eventResult.rows.length === 0) {
      await client.query('ROLLBACK');
      return NextResponse.json(
        { error: 'No events found' },
        { status: 404 }
      );
    }

    const events = eventResult.rows;
    const results = [];
    const errors = [];

    // Process each event
    for (const event of events) {
      try {
        if (!event.character_id) {
          errors.push({
            eventId: event.id,
            error: 'Event must be assigned to a character first',
            rawText: event.raw_text
          });
          continue;
        }

        // Process based on event type
        let result;
        switch (event.event_type) {
          case 'class_obtained':
            result = await processClassObtained(client, event);
            break;
          case 'class_evolution':
            result = await processClassEvolution(client, event);
            break;
          case 'class_consolidation':
            result = await processClassConsolidation(client, event);
            break;
          case 'class_removed':
            result = await processClassRemoved(client, event);
            break;
          case 'level_up':
            result = await processLevelUp(client, event);
            break;
          case 'skill_obtained':
            result = await processAbility(client, event, 'skill');
            break;
          case 'skill_change':
            result = await processSkillChange(client, event);
            break;
          case 'skill_consolidation':
            result = await processSkillConsolidation(client, event);
            break;
          case 'skill_removed':
            result = await processAbilityRemoved(client, event, 'skill');
            break;
          case 'spell_obtained':
            result = await processAbility(client, event, 'spell');
            break;
          case 'spell_removed':
            result = await processAbilityRemoved(client, event, 'spell');
            break;
          case 'condition':
          case 'aspect':
          case 'title':
          case 'rank':
          case 'other':
            result = await processOtherEvent(client, event);
            break;
          case 'false_positive':
            // Archive false positives - they're not real progression events
            await client.query(
              'UPDATE raw_events SET is_processed = true, archived = true WHERE id = $1',
              [event.id]
            );
            results.push({
              eventId: event.id,
              eventType: event.event_type,
              rawText: event.raw_text,
              data: { archived: true, reason: 'false_positive' }
            });
            continue; // Skip the normal "mark as processed" step since we already did it
          default:
            errors.push({
              eventId: event.id,
              error: `Unsupported event type for processing: ${event.event_type}`,
              rawText: event.raw_text
            });
            continue;
        }

        // Mark event as processed and clear needs_review flag
        await client.query(
          'UPDATE raw_events SET is_processed = true, needs_review = false WHERE id = $1',
          [event.id]
        );

        results.push({
          eventId: event.id,
          eventType: event.event_type,
          rawText: event.raw_text,
          data: result
        });
      } catch (error) {
        errors.push({
          eventId: event.id,
          error: (error as Error).message,
          rawText: event.raw_text
        });
      }
    }

    await client.query('COMMIT');

    const isBatch = eventIds && eventIds.length > 1;
    const totalProcessed = results.length;
    const totalErrors = errors.length;

    return NextResponse.json({
      success: totalProcessed > 0,
      message: isBatch
        ? `Processed ${totalProcessed} event(s)${totalErrors > 0 ? `, ${totalErrors} error(s)` : ''}`
        : `Processed ${events[0]?.event_type || 'event'}`,
      processed: totalProcessed,
      failed: totalErrors,
      results,
      errors: errors.length > 0 ? errors : undefined,
    });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Error processing event:', error);
    return NextResponse.json(
      { error: 'Failed to process event(s)', details: (error as Error).message },
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

async function processClassEvolution(client: any, event: any) {
  const oldClass = event.parsed_data?.old_class;
  const newClass = event.parsed_data?.new_class;

  if (!oldClass || !newClass) {
    throw new Error('Could not extract old and new class names from event');
  }

  // Mark old class as inactive
  await client.query(
    `UPDATE character_classes
     SET is_active = false
     WHERE character_id = $1 AND class_name = $2`,
    [event.character_id, oldClass]
  );

  // Create new class and link evolution
  const oldClassResult = await client.query(
    `SELECT id FROM character_classes
     WHERE character_id = $1 AND class_name = $2
     ORDER BY chapter_id DESC LIMIT 1`,
    [event.character_id, oldClass]
  );

  const evolvedFromId = oldClassResult.rows.length > 0 ? oldClassResult.rows[0].id : null;

  const result = await client.query(
    `INSERT INTO character_classes
     (character_id, class_name, chapter_id, raw_event_id, is_active, evolved_from_class_id)
     VALUES ($1, $2, $3, $4, true, $5)
     ON CONFLICT (character_id, class_name, chapter_id) DO UPDATE
     SET raw_event_id = $4, is_active = true, evolved_from_class_id = $5
     RETURNING *`,
    [event.character_id, newClass, event.chapter_id, event.id, evolvedFromId]
  );

  return { old_class: oldClass, new_class: newClass, character_class: result.rows[0] };
}

async function processClassConsolidation(client: any, event: any) {
  const oldClasses = event.parsed_data?.old_classes || [];

  if (oldClasses.length === 0) {
    throw new Error('Could not extract old class names from consolidation event');
  }

  // Mark all old classes as inactive and get their IDs
  const consolidatedIds = [];
  for (const oldClass of oldClasses) {
    const updateResult = await client.query(
      `UPDATE character_classes
       SET is_active = false
       WHERE character_id = $1 AND class_name = $2
       RETURNING id`,
      [event.character_id, oldClass]
    );
    if (updateResult.rows.length > 0) {
      consolidatedIds.push(updateResult.rows[0].id);
    }
  }

  // Note: The consolidated class should be added with a separate class_obtained event
  // This event just marks the old classes as inactive

  return { consolidated_classes: oldClasses, consolidated_ids: consolidatedIds };
}

async function processClassRemoved(client: any, event: any) {
  const className = event.parsed_data?.class_name;

  if (!className) {
    throw new Error('Could not extract class name from removal event');
  }

  // Mark class as inactive
  await client.query(
    `UPDATE character_classes
     SET is_active = false
     WHERE character_id = $1 AND class_name = $2`,
    [event.character_id, className]
  );

  return { removed_class: className };
}

async function processSkillChange(client: any, event: any) {
  const oldSkill = event.parsed_data?.old_skill;
  const newSkill = event.parsed_data?.new_skill;

  if (!oldSkill || !newSkill) {
    throw new Error('Could not extract old and new skill names from event');
  }

  // Remove old skill (mark as removed in a tracking table or delete)
  // For now, we'll just add the new skill - the summary query will handle deduplication

  // Add new skill
  const normalizedName = newSkill.toLowerCase().trim();
  const abilityResult = await client.query(
    `INSERT INTO abilities (name, type, normalized_name, first_seen_chapter_id)
     VALUES ($1, 'skill', $2, $3)
     ON CONFLICT (normalized_name, type) DO UPDATE
     SET name = EXCLUDED.name
     RETURNING id`,
    [newSkill, normalizedName, event.chapter_id]
  );

  const abilityId = abilityResult.rows[0].id;

  // Find the most recent active class
  const classResult = await client.query(
    `SELECT id FROM character_classes
     WHERE character_id = $1 AND is_active = true
     ORDER BY chapter_id DESC LIMIT 1`,
    [event.character_id]
  );

  const characterClassId = classResult.rows.length > 0 ? classResult.rows[0].id : null;

  // Insert character ability
  const characterAbilityResult = await client.query(
    `INSERT INTO character_abilities
     (character_id, ability_id, chapter_id, character_class_id, raw_event_id, acquisition_method)
     VALUES ($1, $2, $3, $4, $5, 'level_up')
     ON CONFLICT (character_id, ability_id, chapter_id) DO UPDATE
     SET raw_event_id = $5, character_class_id = $4
     RETURNING *`,
    [event.character_id, abilityId, event.chapter_id, characterClassId, event.id]
  );

  return {
    old_skill: oldSkill,
    new_skill: newSkill,
    character_ability: characterAbilityResult.rows[0]
  };
}

async function processSkillConsolidation(client: any, event: any) {
  const skillName = event.parsed_data?.skill_name;

  if (!skillName) {
    throw new Error('Could not extract skill name from consolidation event');
  }

  // Note: This event represents an old skill being removed during consolidation
  // The new consolidated skill should be added with a separate skill_obtained event
  // We'll store this for tracking but the summary query will handle filtering

  return { consolidated_skill: skillName };
}

async function processAbilityRemoved(client: any, event: any, type: 'skill' | 'spell') {
  const abilityName = event.parsed_data?.skill_name || event.parsed_data?.spell_name;

  if (!abilityName) {
    throw new Error(`Could not extract ${type} name from removal event`);
  }

  // Note: We track the removal event but don't delete from character_abilities
  // The summary query will filter based on whether a removal event exists after the acquisition

  return { removed_ability: abilityName, type };
}

async function processOtherEvent(client: any, event: any) {
  // For condition, aspect, title, rank, and other event types
  // Store them as 'skill' type abilities so they appear in the UI

  // Extract the name from parsed_data based on event type
  let abilityName = event.parsed_data?.name ||
                    event.parsed_data?.ability_name ||
                    event.parsed_data?.condition_name ||
                    event.parsed_data?.aspect_name ||
                    event.parsed_data?.title_name ||
                    event.parsed_data?.content;

  // For rank events, construct a name
  if (!abilityName && event.event_type === 'rank') {
    const rankNum = event.parsed_data?.rank_number;
    const rankType = event.parsed_data?.rank_type;
    const rankName = event.parsed_data?.rank_name;
    if (rankNum && rankType) {
      abilityName = `Rank ${rankNum} ${rankType}${rankName ? ' - ' + rankName : ''}`;
    }
  }

  if (!abilityName) {
    // Try to extract from raw text - remove brackets and common prefixes
    const rawText = event.raw_text.replace(/[\[\]]/g, '').trim();
    // Remove common suffixes like "obtained!", "gained!", etc.
    abilityName = rawText.replace(/\s+(obtained|gained|received|lost|removed)[!.]?$/i, '').trim();
  }

  if (!abilityName) {
    throw new Error(`Could not extract name from ${event.event_type} event`);
  }

  const normalizedName = abilityName.toLowerCase().trim();

  // Insert or get the ability - store as 'skill' type so it appears with skills
  const abilityResult = await client.query(
    `INSERT INTO abilities (name, type, normalized_name, first_seen_chapter_id)
     VALUES ($1, 'skill', $2, $3)
     ON CONFLICT (normalized_name, type) DO UPDATE
     SET name = EXCLUDED.name
     RETURNING id`,
    [abilityName, normalizedName, event.chapter_id]
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
    event_type: event.event_type,
    ability: { id: abilityId, name: abilityName, type: 'skill' },
    character_ability: characterAbilityResult.rows[0]
  };
}
