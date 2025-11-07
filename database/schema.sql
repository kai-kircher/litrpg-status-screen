-- Wandering Inn Tracker Database Schema
-- PostgreSQL

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- CORE ENTITIES
-- ============================================================================

-- Chapters from the web serial
CREATE TABLE chapters (
    id SERIAL PRIMARY KEY,
    chapter_number INTEGER NOT NULL UNIQUE,
    title VARCHAR(500),
    url TEXT NOT NULL,
    content TEXT, -- Full chapter text for re-parsing if needed
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP WITH TIME ZONE,
    word_count INTEGER,
    CONSTRAINT chapters_chapter_number_positive CHECK (chapter_number > 0)
);

-- Characters in the series
CREATE TABLE characters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    aliases TEXT[], -- Array of alternate names/nicknames
    first_appearance_chapter_id INTEGER REFERENCES chapters(id),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- RAW SCRAPING DATA (Unprocessed)
-- ============================================================================

-- Raw events extracted from chapters (before manual assignment)
CREATE TABLE raw_events (
    id SERIAL PRIMARY KEY,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL, -- 'class_obtained', 'class_evolution', 'class_consolidation', 'level_up', 'skill_change', 'skill_obtained', 'spell_obtained', 'condition', 'aspect', 'title', 'rank', 'other'
    raw_text TEXT NOT NULL, -- The original bracketed text
    parsed_data JSONB, -- Structured extraction: {class_name, level, skill_name, etc}
    character_id INTEGER REFERENCES characters(id), -- NULL until manually assigned
    is_assigned BOOLEAN DEFAULT FALSE,
    is_processed BOOLEAN DEFAULT FALSE, -- TRUE when event has been processed into progression tables
    archived BOOLEAN DEFAULT FALSE, -- TRUE for false positives that should be hidden
    context TEXT, -- Surrounding text for disambiguation
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT raw_events_event_type_check CHECK (
        event_type IN (
            'class_obtained',
            'class_evolution',
            'class_consolidation',
            'level_up',
            'skill_change',
            'skill_obtained',
            'spell_obtained',
            'condition',
            'aspect',
            'title',
            'rank',
            'other'
        )
    )
);

-- ============================================================================
-- CHARACTER PROGRESSION (Processed)
-- ============================================================================

-- Character class assignments (one row per class obtained)
CREATE TABLE character_classes (
    id SERIAL PRIMARY KEY,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    class_name VARCHAR(255) NOT NULL,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    raw_event_id INTEGER REFERENCES raw_events(id),

    -- Class evolution tracking
    evolved_from_class_id INTEGER REFERENCES character_classes(id), -- If this class evolved from another
    consolidated_class_ids INTEGER[], -- If this class consolidated multiple classes
    is_active BOOLEAN DEFAULT TRUE, -- FALSE if the class evolved/consolidated into another

    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT character_classes_unique_class UNIQUE (character_id, class_name, chapter_id)
);

-- Level progression for each character class
CREATE TABLE character_levels (
    id SERIAL PRIMARY KEY,
    character_class_id INTEGER NOT NULL REFERENCES character_classes(id) ON DELETE CASCADE,
    level INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    raw_event_id INTEGER REFERENCES raw_events(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT character_levels_level_positive CHECK (level > 0),
    CONSTRAINT character_levels_unique_level UNIQUE (character_class_id, chapter_id, level)
);

-- Catalog of all abilities (skills and spells)
CREATE TABLE abilities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    type VARCHAR(50) NOT NULL, -- 'skill' or 'spell'
    normalized_name VARCHAR(500) NOT NULL, -- Lowercase, trimmed for matching
    description TEXT,
    first_seen_chapter_id INTEGER REFERENCES chapters(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT abilities_type_check CHECK (type IN ('skill', 'spell')),
    CONSTRAINT abilities_unique_name UNIQUE (normalized_name, type)
);

-- Character ability acquisitions
CREATE TABLE character_abilities (
    id SERIAL PRIMARY KEY,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    ability_id INTEGER NOT NULL REFERENCES abilities(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    character_class_id INTEGER REFERENCES character_classes(id), -- Which class granted this (may be NULL if learned manually)
    level_at_acquisition INTEGER, -- Character level when acquired (may be NULL)
    raw_event_id INTEGER REFERENCES raw_events(id),
    acquisition_method VARCHAR(50) DEFAULT 'level_up', -- 'level_up', 'learned', 'unknown'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT character_abilities_unique UNIQUE (character_id, ability_id, chapter_id),
    CONSTRAINT character_abilities_method_check CHECK (
        acquisition_method IN ('level_up', 'learned', 'unknown')
    )
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Chapters
CREATE INDEX idx_chapters_chapter_number ON chapters(chapter_number);
CREATE INDEX idx_chapters_scraped_at ON chapters(scraped_at);

-- Characters
CREATE INDEX idx_characters_name ON characters(name);

-- Raw events
CREATE INDEX idx_raw_events_chapter ON raw_events(chapter_id);
CREATE INDEX idx_raw_events_character ON raw_events(character_id);
CREATE INDEX idx_raw_events_assigned ON raw_events(is_assigned) WHERE is_assigned = FALSE;
CREATE INDEX idx_raw_events_type ON raw_events(event_type);
CREATE INDEX idx_raw_events_archived ON raw_events(archived) WHERE archived = FALSE;
CREATE INDEX idx_raw_events_processing_status ON raw_events(is_assigned, is_processed, archived);

-- Character classes
CREATE INDEX idx_character_classes_character ON character_classes(character_id);
CREATE INDEX idx_character_classes_chapter ON character_classes(chapter_id);
CREATE INDEX idx_character_classes_active ON character_classes(is_active) WHERE is_active = TRUE;

-- Character levels
CREATE INDEX idx_character_levels_character_class ON character_levels(character_class_id);
CREATE INDEX idx_character_levels_chapter ON character_levels(chapter_id);

-- Abilities
CREATE INDEX idx_abilities_normalized_name ON abilities(normalized_name);
CREATE INDEX idx_abilities_type ON abilities(type);

-- Character abilities
CREATE INDEX idx_character_abilities_character ON character_abilities(character_id);
CREATE INDEX idx_character_abilities_ability ON character_abilities(ability_id);
CREATE INDEX idx_character_abilities_chapter ON character_abilities(chapter_id);
CREATE INDEX idx_character_abilities_character_chapter ON character_abilities(character_id, chapter_id);

-- ============================================================================
-- USEFUL VIEWS
-- ============================================================================

-- View: Unassigned events that need manual character assignment
CREATE VIEW unassigned_events AS
SELECT
    re.id,
    re.event_type,
    re.raw_text,
    re.parsed_data,
    re.context,
    c.chapter_number,
    c.title AS chapter_title
FROM raw_events re
JOIN chapters c ON re.chapter_id = c.id
WHERE re.is_assigned = FALSE AND re.archived = FALSE
ORDER BY c.chapter_number, re.id;

-- View: Current character progression (latest state)
CREATE VIEW character_current_state AS
SELECT
    char.id AS character_id,
    char.name AS character_name,
    cc.id AS character_class_id,
    cc.class_name,
    MAX(cl.level) AS current_level,
    MAX(cl.chapter_id) AS last_level_chapter_id
FROM characters char
JOIN character_classes cc ON char.id = cc.character_id
LEFT JOIN character_levels cl ON cc.id = cl.character_class_id
WHERE cc.is_active = TRUE
GROUP BY char.id, char.name, cc.id, cc.class_name;

-- View: Character abilities timeline
CREATE VIEW character_abilities_timeline AS
SELECT
    char.name AS character_name,
    a.name AS ability_name,
    a.type AS ability_type,
    ch.chapter_number,
    ch.title AS chapter_title,
    ca.level_at_acquisition,
    cc.class_name,
    ca.acquisition_method
FROM character_abilities ca
JOIN characters char ON ca.character_id = char.id
JOIN abilities a ON ca.ability_id = a.id
JOIN chapters ch ON ca.chapter_id = ch.id
LEFT JOIN character_classes cc ON ca.character_class_id = cc.id
ORDER BY char.name, ch.chapter_number;

-- ============================================================================
-- UTILITY FUNCTIONS
-- ============================================================================

-- Function: Get all abilities for a character up to a specific chapter
CREATE OR REPLACE FUNCTION get_character_abilities_at_chapter(
    p_character_id INTEGER,
    p_chapter_number INTEGER
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
        ch.chapter_number,
        cc.class_name
    FROM character_abilities ca
    JOIN abilities a ON ca.ability_id = a.id
    JOIN chapters ch ON ca.chapter_id = ch.id
    LEFT JOIN character_classes cc ON ca.character_class_id = cc.id
    WHERE ca.character_id = p_character_id
      AND ch.chapter_number <= p_chapter_number
    ORDER BY ch.chapter_number;
END;
$$ LANGUAGE plpgsql;

-- Function: Get character level at specific chapter
CREATE OR REPLACE FUNCTION get_character_level_at_chapter(
    p_character_id INTEGER,
    p_class_name VARCHAR(255),
    p_chapter_number INTEGER
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
      AND ch.chapter_number <= p_chapter_number;

    RETURN COALESCE(v_level, 0);
END;
$$ LANGUAGE plpgsql;
