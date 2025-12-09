-- Migration: Consolidate characters and wiki_characters tables
--
-- The wiki_characters table (scraped from wiki) becomes the canonical source for character identity.
-- The old characters table is removed, and all FKs now reference wiki_characters.
--
-- Prerequisites:
-- - characters table must be empty (no data loss)
-- - raw_events.character_id must all be NULL
-- - character_classes must be empty
-- - character_abilities must be empty

-- ============================================================================
-- STEP 1: Add first_appearance_chapter_id to wiki_characters
-- ============================================================================

ALTER TABLE wiki_characters
ADD COLUMN IF NOT EXISTS first_appearance_chapter_id INTEGER REFERENCES chapters(id);

COMMENT ON COLUMN wiki_characters.first_appearance_chapter_id IS 'Chapter ID where this character first appears (populated during event processing)';

-- ============================================================================
-- STEP 2: Drop old FK constraints from raw_events
-- ============================================================================

-- Drop the FK constraint if it exists (may have different auto-generated names)
DO $$
BEGIN
    -- Try to drop any FK referencing characters on raw_events
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'raw_events'
        AND constraint_type = 'FOREIGN KEY'
        AND constraint_name LIKE '%character%'
    ) THEN
        EXECUTE (
            SELECT 'ALTER TABLE raw_events DROP CONSTRAINT ' || constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'raw_events'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%character%'
            LIMIT 1
        );
    END IF;
END $$;

-- Add new FK to wiki_characters
ALTER TABLE raw_events
ADD CONSTRAINT raw_events_character_fk
FOREIGN KEY (character_id) REFERENCES wiki_characters(id);

-- ============================================================================
-- STEP 3: Drop old FK constraints from character_classes
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'character_classes'
        AND constraint_type = 'FOREIGN KEY'
        AND constraint_name LIKE '%character_id%'
    ) THEN
        EXECUTE (
            SELECT 'ALTER TABLE character_classes DROP CONSTRAINT ' || constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'character_classes'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%character_id%'
            AND constraint_name NOT LIKE '%chapter%'
            LIMIT 1
        );
    END IF;
END $$;

-- Add new FK to wiki_characters
ALTER TABLE character_classes
DROP CONSTRAINT IF EXISTS character_classes_character_fk;

ALTER TABLE character_classes
ADD CONSTRAINT character_classes_character_fk
FOREIGN KEY (character_id) REFERENCES wiki_characters(id) ON DELETE CASCADE;

-- ============================================================================
-- STEP 4: Drop old FK constraints from character_abilities
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'character_abilities'
        AND constraint_type = 'FOREIGN KEY'
        AND constraint_name LIKE '%character_id%'
    ) THEN
        EXECUTE (
            SELECT 'ALTER TABLE character_abilities DROP CONSTRAINT ' || constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'character_abilities'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%character_id%'
            AND constraint_name NOT LIKE '%chapter%'
            AND constraint_name NOT LIKE '%ability%'
            AND constraint_name NOT LIKE '%class%'
            LIMIT 1
        );
    END IF;
END $$;

-- Add new FK to wiki_characters
ALTER TABLE character_abilities
DROP CONSTRAINT IF EXISTS character_abilities_character_fk;

ALTER TABLE character_abilities
ADD CONSTRAINT character_abilities_character_fk
FOREIGN KEY (character_id) REFERENCES wiki_characters(id) ON DELETE CASCADE;

-- ============================================================================
-- STEP 5: Drop and recreate views to use wiki_characters
-- ============================================================================

DROP VIEW IF EXISTS character_current_state;
DROP VIEW IF EXISTS character_abilities_timeline;

-- View: Current character progression (latest state)
CREATE VIEW character_current_state AS
SELECT
    wc.id AS character_id,
    wc.name AS character_name,
    cc.id AS character_class_id,
    cc.class_name,
    MAX(cl.level) AS current_level,
    MAX(cl.chapter_id) AS last_level_chapter_id
FROM wiki_characters wc
JOIN character_classes cc ON wc.id = cc.character_id
LEFT JOIN character_levels cl ON cc.id = cl.character_class_id
WHERE cc.is_active = TRUE
GROUP BY wc.id, wc.name, cc.id, cc.class_name;

-- View: Character abilities timeline
CREATE VIEW character_abilities_timeline AS
SELECT
    wc.name AS character_name,
    a.name AS ability_name,
    a.type AS ability_type,
    ch.order_index AS chapter_number,
    ch.chapter_title AS chapter_title,
    ca.level_at_acquisition,
    cc.class_name,
    ca.acquisition_method
FROM character_abilities ca
JOIN wiki_characters wc ON ca.character_id = wc.id
JOIN abilities a ON ca.ability_id = a.id
JOIN chapters ch ON ca.chapter_id = ch.id
LEFT JOIN character_classes cc ON ca.character_class_id = cc.id
ORDER BY wc.name, ch.order_index;

-- ============================================================================
-- STEP 6: Update functions to use wiki_characters
-- ============================================================================

-- Drop existing functions first (they may have different signatures)
DROP FUNCTION IF EXISTS get_character_abilities_at_chapter(integer,integer);
DROP FUNCTION IF EXISTS get_character_level_at_chapter(integer,character varying,integer);

-- Function: Get all abilities for a character up to a specific chapter
CREATE OR REPLACE FUNCTION get_character_abilities_at_chapter(
    p_character_id INTEGER,
    p_order_index INTEGER
)
RETURNS TABLE (
    ability_name VARCHAR(500),
    ability_type VARCHAR(50),
    acquired_at_chapter INTEGER,
    class_name VARCHAR(255)
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.name,
        a.type,
        ch.order_index,
        cc.class_name
    FROM character_abilities ca
    JOIN abilities a ON ca.ability_id = a.id
    JOIN chapters ch ON ca.chapter_id = ch.id
    LEFT JOIN character_classes cc ON ca.character_class_id = cc.id
    WHERE ca.character_id = p_character_id
      AND ch.order_index <= p_order_index
    ORDER BY ch.order_index;
END;
$$ LANGUAGE plpgsql;

-- Function: Get character level at specific chapter
CREATE OR REPLACE FUNCTION get_character_level_at_chapter(
    p_character_id INTEGER,
    p_class_name VARCHAR(255),
    p_order_index INTEGER
)
RETURNS INTEGER AS $$
DECLARE
    v_level INTEGER;
BEGIN
    SELECT MAX(cl.level) INTO v_level
    FROM character_levels cl
    JOIN character_classes cc ON cl.character_class_id = cc.id
    JOIN chapters ch ON cl.chapter_id = ch.id
    WHERE cc.character_id = p_character_id
      AND cc.class_name = p_class_name
      AND ch.order_index <= p_order_index;

    RETURN COALESCE(v_level, 0);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- STEP 7: Drop the old characters table
-- ============================================================================

DROP TABLE IF EXISTS characters CASCADE;

-- ============================================================================
-- STEP 8: Update comments
-- ============================================================================

COMMENT ON TABLE wiki_characters IS 'Canonical character list from Wandering Inn Wiki - serves as the primary character identity table for all progression tracking';
