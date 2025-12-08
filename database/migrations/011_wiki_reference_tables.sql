-- Migration: Add wiki reference tables
-- These tables store canonical data scraped from the Wandering Inn Wiki
-- Used by AI processing to match against known entities instead of free-form extraction

-- Wiki Characters: Canonical character list from wiki
CREATE TABLE IF NOT EXISTS wiki_characters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    wiki_url TEXT NOT NULL,
    wiki_page_title VARCHAR(500),

    -- Data from individual character pages (populated in second pass)
    aliases TEXT[],                              -- Alternate names/titles
    species VARCHAR(255),
    status VARCHAR(100),                         -- Alive, Deceased, Unknown
    affiliation TEXT[],                          -- Organizations, nations
    first_appearance VARCHAR(255),               -- Chapter reference from wiki

    -- Raw infobox data for anything we don't explicitly model
    infobox_data JSONB DEFAULT '{}',

    -- Metadata
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    page_scraped_at TIMESTAMP WITH TIME ZONE,   -- When individual page was scraped

    CONSTRAINT wiki_characters_name_unique UNIQUE(name)
);

-- Wiki Skills: Canonical skill list from wiki
CREATE TABLE IF NOT EXISTS wiki_skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,                  -- Full name including brackets: [Skill Name]
    normalized_name VARCHAR(500) NOT NULL,       -- Lowercase, no brackets for matching
    effect TEXT,                                 -- Description of what the skill does
    reference_chapters TEXT,                     -- Chapter references from wiki

    -- Classification
    is_fake BOOLEAN DEFAULT FALSE,              -- From "Fake and Imaginary Skills" section
    is_conditional BOOLEAN DEFAULT FALSE,        -- Daily, Weekly, etc.
    skill_type VARCHAR(100),                     -- Combination, Inheritance, Legacy, etc.

    -- Metadata
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT wiki_skills_normalized_unique UNIQUE(normalized_name)
);

-- Wiki Spells: Canonical spell list from wiki
CREATE TABLE IF NOT EXISTS wiki_spells (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,                  -- Full name including brackets: [Spell Name]
    normalized_name VARCHAR(500) NOT NULL,       -- Lowercase, no brackets for matching
    tier INTEGER,                                -- Spell tier (0-9), NULL for untiered
    effect TEXT,                                 -- Description of what the spell does
    reference_chapters TEXT,                     -- Chapter references from wiki

    -- Classification
    is_tiered BOOLEAN DEFAULT TRUE,             -- FALSE for untiered spells section

    -- Metadata
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT wiki_spells_normalized_unique UNIQUE(normalized_name)
);

-- Wiki Classes: Canonical class list from wiki
CREATE TABLE IF NOT EXISTS wiki_classes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,                  -- Full name including brackets: [Class Name]
    normalized_name VARCHAR(500) NOT NULL,       -- Lowercase, no brackets for matching
    description TEXT,                            -- Information about the class
    known_characters TEXT,                       -- Characters with this class (from wiki)
    reference_chapters TEXT,                     -- Chapter references from wiki

    -- Classification
    is_fake BOOLEAN DEFAULT FALSE,              -- From "Hypothetical and Fake Classes" section
    class_type VARCHAR(100),                     -- umbrella, prestige, colored, comma, etc.

    -- Metadata
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT wiki_classes_normalized_unique UNIQUE(normalized_name)
);

-- Indexes for efficient lookups during AI processing
CREATE INDEX IF NOT EXISTS idx_wiki_characters_name ON wiki_characters(name);
CREATE INDEX IF NOT EXISTS idx_wiki_characters_aliases ON wiki_characters USING GIN(aliases);

CREATE INDEX IF NOT EXISTS idx_wiki_skills_normalized ON wiki_skills(normalized_name);
CREATE INDEX IF NOT EXISTS idx_wiki_skills_is_fake ON wiki_skills(is_fake) WHERE is_fake = TRUE;

CREATE INDEX IF NOT EXISTS idx_wiki_spells_normalized ON wiki_spells(normalized_name);
CREATE INDEX IF NOT EXISTS idx_wiki_spells_tier ON wiki_spells(tier);

CREATE INDEX IF NOT EXISTS idx_wiki_classes_normalized ON wiki_classes(normalized_name);
CREATE INDEX IF NOT EXISTS idx_wiki_classes_is_fake ON wiki_classes(is_fake) WHERE is_fake = TRUE;

-- Track wiki scrape state
CREATE TABLE IF NOT EXISTS wiki_scrape_state (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,            -- 'characters', 'skills', 'spells', 'classes'
    last_scraped_at TIMESTAMP WITH TIME ZONE,
    total_count INTEGER DEFAULT 0,
    last_page_url TEXT,                          -- For resuming paginated scrapes

    CONSTRAINT wiki_scrape_state_type_unique UNIQUE(entity_type),
    CONSTRAINT wiki_scrape_state_type_check CHECK (
        entity_type IN ('characters', 'skills', 'spells', 'classes')
    )
);

-- Comments
COMMENT ON TABLE wiki_characters IS 'Canonical character list from Wandering Inn Wiki - used as reference for AI character matching';
COMMENT ON TABLE wiki_skills IS 'Canonical skill list from wiki - includes fake/imaginary skills for filtering';
COMMENT ON TABLE wiki_spells IS 'Canonical spell list from wiki with tier information';
COMMENT ON TABLE wiki_classes IS 'Canonical class list from wiki - includes fake/hypothetical classes for filtering';
COMMENT ON TABLE wiki_scrape_state IS 'Tracks wiki scraping progress for each entity type';

COMMENT ON COLUMN wiki_characters.aliases IS 'Alternate names, titles, nicknames from character infobox';
COMMENT ON COLUMN wiki_skills.is_fake IS 'TRUE for skills from "Fake and Imaginary Skills" section - used to filter false positives';
COMMENT ON COLUMN wiki_classes.is_fake IS 'TRUE for classes from "Hypothetical and Fake Classes" section';
