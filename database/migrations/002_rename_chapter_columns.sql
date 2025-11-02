-- Rename chapter columns to be more accurate
-- chapter_number -> order_index (sequential position in the scraped list)
-- title -> chapter_number (actual chapter identifier like "1.00", "1.01")
-- Add chapter_title for actual chapter titles (optional, to be populated later)

BEGIN;

-- Rename chapter_number to order_index
ALTER TABLE chapters RENAME COLUMN chapter_number TO order_index;

-- Rename title to chapter_number
ALTER TABLE chapters RENAME COLUMN title TO chapter_number;

-- Add chapter_title column for actual chapter titles
ALTER TABLE chapters ADD COLUMN chapter_title VARCHAR(500);

-- Update constraint names to match new column names
ALTER TABLE chapters DROP CONSTRAINT chapters_chapter_number_positive;
ALTER TABLE chapters ADD CONSTRAINT chapters_order_index_positive CHECK (order_index > 0);

-- Update the unique constraint
ALTER TABLE chapters DROP CONSTRAINT chapters_chapter_number_key;
ALTER TABLE chapters ADD CONSTRAINT chapters_order_index_key UNIQUE (order_index);

-- Drop and recreate indexes with new column names
DROP INDEX idx_chapters_chapter_number;
CREATE INDEX idx_chapters_order_index ON chapters(order_index);

-- Update the unassigned_events view to use new column names
DROP VIEW IF EXISTS unassigned_events;
CREATE VIEW unassigned_events AS
SELECT
    re.id,
    re.event_type,
    re.raw_text,
    re.parsed_data,
    re.context,
    c.order_index,
    c.chapter_number,
    c.chapter_title
FROM raw_events re
JOIN chapters c ON re.chapter_id = c.id
WHERE re.is_assigned = FALSE
ORDER BY c.order_index, re.id;

-- Update other views that reference chapter_number
DROP VIEW IF EXISTS character_abilities_timeline;
CREATE VIEW character_abilities_timeline AS
SELECT
    char.name AS character_name,
    a.name AS ability_name,
    a.type AS ability_type,
    ch.order_index,
    ch.chapter_number,
    ch.chapter_title,
    ca.level_at_acquisition,
    cc.class_name,
    ca.acquisition_method
FROM character_abilities ca
JOIN characters char ON ca.character_id = char.id
JOIN abilities a ON ca.ability_id = a.id
JOIN chapters ch ON ca.chapter_id = ch.id
LEFT JOIN character_classes cc ON ca.character_class_id = cc.id
ORDER BY char.name, ch.order_index;

-- Update the function to use new column names
DROP FUNCTION IF EXISTS get_character_abilities_at_chapter(INTEGER, INTEGER);
CREATE OR REPLACE FUNCTION get_character_abilities_at_chapter(
    p_character_id INTEGER,
    p_order_index INTEGER
)
RETURNS TABLE (
    ability_name VARCHAR(500),
    ability_type VARCHAR(50),
    acquired_at_order_index INTEGER,
    acquired_at_chapter_number VARCHAR(500),
    class_name VARCHAR(255)
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.name,
        a.type,
        ch.order_index,
        ch.chapter_number,
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

-- Update the other function
DROP FUNCTION IF EXISTS get_character_level_at_chapter(INTEGER, VARCHAR, INTEGER);
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

COMMIT;
