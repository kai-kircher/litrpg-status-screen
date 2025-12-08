"""Database operations for wiki reference data"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from .connection import get_connection, return_connection

logger = logging.getLogger(__name__)


# =============================================================================
# WIKI CHARACTERS
# =============================================================================

def save_wiki_character(
    name: str,
    wiki_url: str,
    wiki_page_title: Optional[str] = None,
    aliases: Optional[List[str]] = None,
    species: Optional[str] = None,
    status: Optional[str] = None,
    affiliation: Optional[List[str]] = None,
    first_appearance: Optional[str] = None,
    infobox_data: Optional[Dict] = None
) -> Optional[int]:
    """
    Save a wiki character to the database

    Returns:
        Character ID if successful, None otherwise
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO wiki_characters (
                name, wiki_url, wiki_page_title, aliases, species, status,
                affiliation, first_appearance, infobox_data, scraped_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE
            SET wiki_url = EXCLUDED.wiki_url,
                wiki_page_title = EXCLUDED.wiki_page_title,
                aliases = EXCLUDED.aliases,
                species = EXCLUDED.species,
                status = EXCLUDED.status,
                affiliation = EXCLUDED.affiliation,
                first_appearance = EXCLUDED.first_appearance,
                infobox_data = EXCLUDED.infobox_data,
                scraped_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (
                name, wiki_url, wiki_page_title, aliases, species, status,
                affiliation, first_appearance,
                json.dumps(infobox_data) if infobox_data else '{}'
            )
        )

        char_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()

        logger.debug(f"Saved wiki character: {name}")
        return char_id
    except Exception as e:
        logger.error(f"Error saving wiki character {name}: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            return_connection(conn)


def save_wiki_characters_batch(characters: List[Dict[str, Any]]) -> int:
    """
    Save multiple wiki characters in a batch

    Args:
        characters: List of character dictionaries

    Returns:
        Number of characters saved
    """
    if not characters:
        return 0

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        from psycopg2.extras import execute_batch
        values = []
        for char in characters:
            values.append((
                char['name'],
                char['wiki_url'],
                char.get('wiki_page_title'),
                char.get('aliases'),
                char.get('species'),
                char.get('status'),
                char.get('affiliation'),
                char.get('first_appearance'),
                json.dumps(char.get('infobox_data', {}))
            ))

        execute_batch(
            cursor,
            """
            INSERT INTO wiki_characters (
                name, wiki_url, wiki_page_title, aliases, species, status,
                affiliation, first_appearance, infobox_data, scraped_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE
            SET wiki_url = EXCLUDED.wiki_url,
                wiki_page_title = EXCLUDED.wiki_page_title,
                scraped_at = CURRENT_TIMESTAMP
            """,
            values
        )

        conn.commit()
        count = len(characters)
        cursor.close()

        logger.info(f"Saved {count} wiki characters in batch")
        return count
    except Exception as e:
        logger.error(f"Error saving wiki characters batch: {e}")
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            return_connection(conn)


def get_wiki_character_count() -> int:
    """Get total count of wiki characters"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM wiki_characters")
        count = cursor.fetchone()[0]
        cursor.close()
        return count
    except Exception as e:
        logger.error(f"Error getting wiki character count: {e}")
        return 0
    finally:
        if conn:
            return_connection(conn)


def get_all_wiki_character_names() -> List[str]:
    """Get all wiki character names for matching"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM wiki_characters ORDER BY name")
        names = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return names
    except Exception as e:
        logger.error(f"Error getting wiki character names: {e}")
        return []
    finally:
        if conn:
            return_connection(conn)


def get_wiki_character_with_aliases() -> List[Dict[str, Any]]:
    """Get all wiki characters with their aliases for matching"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, aliases FROM wiki_characters ORDER BY name"
        )
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'name': row[1],
                'aliases': row[2] or []
            })
        cursor.close()
        return results
    except Exception as e:
        logger.error(f"Error getting wiki characters with aliases: {e}")
        return []
    finally:
        if conn:
            return_connection(conn)


# =============================================================================
# WIKI SKILLS
# =============================================================================

def save_wiki_skill(
    name: str,
    normalized_name: str,
    effect: Optional[str] = None,
    reference_chapters: Optional[str] = None,
    is_fake: bool = False,
    is_conditional: bool = False,
    skill_type: Optional[str] = None
) -> Optional[int]:
    """Save a wiki skill to the database"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO wiki_skills (
                name, normalized_name, effect, reference_chapters,
                is_fake, is_conditional, skill_type, scraped_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (normalized_name) DO UPDATE
            SET name = EXCLUDED.name,
                effect = EXCLUDED.effect,
                reference_chapters = EXCLUDED.reference_chapters,
                is_fake = EXCLUDED.is_fake,
                is_conditional = EXCLUDED.is_conditional,
                skill_type = EXCLUDED.skill_type,
                scraped_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (name, normalized_name, effect, reference_chapters, is_fake, is_conditional, skill_type)
        )

        skill_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()

        logger.debug(f"Saved wiki skill: {name}")
        return skill_id
    except Exception as e:
        logger.error(f"Error saving wiki skill {name}: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            return_connection(conn)


def save_wiki_skills_batch(skills: List[Dict[str, Any]]) -> int:
    """Save multiple wiki skills in a batch"""
    if not skills:
        return 0

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        from psycopg2.extras import execute_batch
        values = []
        for skill in skills:
            values.append((
                skill['name'],
                skill['normalized_name'],
                skill.get('effect'),
                skill.get('reference_chapters'),
                skill.get('is_fake', False),
                skill.get('is_conditional', False),
                skill.get('skill_type')
            ))

        execute_batch(
            cursor,
            """
            INSERT INTO wiki_skills (
                name, normalized_name, effect, reference_chapters,
                is_fake, is_conditional, skill_type, scraped_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (normalized_name) DO UPDATE
            SET name = EXCLUDED.name,
                effect = EXCLUDED.effect,
                reference_chapters = EXCLUDED.reference_chapters,
                is_fake = EXCLUDED.is_fake,
                is_conditional = EXCLUDED.is_conditional,
                skill_type = EXCLUDED.skill_type,
                scraped_at = CURRENT_TIMESTAMP
            """,
            values
        )

        conn.commit()
        count = len(skills)
        cursor.close()

        logger.info(f"Saved {count} wiki skills in batch")
        return count
    except Exception as e:
        logger.error(f"Error saving wiki skills batch: {e}")
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            return_connection(conn)


def get_wiki_skill_count() -> int:
    """Get total count of wiki skills"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM wiki_skills")
        count = cursor.fetchone()[0]
        cursor.close()
        return count
    except Exception as e:
        logger.error(f"Error getting wiki skill count: {e}")
        return 0
    finally:
        if conn:
            return_connection(conn)


def get_all_wiki_skills() -> List[Dict[str, Any]]:
    """Get all wiki skills for matching"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, normalized_name, is_fake
            FROM wiki_skills
            ORDER BY normalized_name
            """
        )
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'name': row[1],
                'normalized_name': row[2],
                'is_fake': row[3]
            })
        cursor.close()
        return results
    except Exception as e:
        logger.error(f"Error getting wiki skills: {e}")
        return []
    finally:
        if conn:
            return_connection(conn)


def is_fake_skill(normalized_name: str) -> bool:
    """Check if a skill name matches a fake/imaginary skill"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT is_fake FROM wiki_skills
            WHERE normalized_name = %s
            """,
            (normalized_name,)
        )
        result = cursor.fetchone()
        cursor.close()
        return result[0] if result else False
    except Exception as e:
        logger.error(f"Error checking fake skill: {e}")
        return False
    finally:
        if conn:
            return_connection(conn)


# =============================================================================
# WIKI SPELLS
# =============================================================================

def save_wiki_spell(
    name: str,
    normalized_name: str,
    tier: Optional[int] = None,
    effect: Optional[str] = None,
    reference_chapters: Optional[str] = None,
    is_tiered: bool = True
) -> Optional[int]:
    """Save a wiki spell to the database"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO wiki_spells (
                name, normalized_name, tier, effect, reference_chapters,
                is_tiered, scraped_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (normalized_name) DO UPDATE
            SET name = EXCLUDED.name,
                tier = EXCLUDED.tier,
                effect = EXCLUDED.effect,
                reference_chapters = EXCLUDED.reference_chapters,
                is_tiered = EXCLUDED.is_tiered,
                scraped_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (name, normalized_name, tier, effect, reference_chapters, is_tiered)
        )

        spell_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()

        logger.debug(f"Saved wiki spell: {name}")
        return spell_id
    except Exception as e:
        logger.error(f"Error saving wiki spell {name}: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            return_connection(conn)


def save_wiki_spells_batch(spells: List[Dict[str, Any]]) -> int:
    """Save multiple wiki spells in a batch"""
    if not spells:
        return 0

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        from psycopg2.extras import execute_batch
        values = []
        for spell in spells:
            values.append((
                spell['name'],
                spell['normalized_name'],
                spell.get('tier'),
                spell.get('effect'),
                spell.get('reference_chapters'),
                spell.get('is_tiered', True)
            ))

        execute_batch(
            cursor,
            """
            INSERT INTO wiki_spells (
                name, normalized_name, tier, effect, reference_chapters,
                is_tiered, scraped_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (normalized_name) DO UPDATE
            SET name = EXCLUDED.name,
                tier = EXCLUDED.tier,
                effect = EXCLUDED.effect,
                reference_chapters = EXCLUDED.reference_chapters,
                is_tiered = EXCLUDED.is_tiered,
                scraped_at = CURRENT_TIMESTAMP
            """,
            values
        )

        conn.commit()
        count = len(spells)
        cursor.close()

        logger.info(f"Saved {count} wiki spells in batch")
        return count
    except Exception as e:
        logger.error(f"Error saving wiki spells batch: {e}")
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            return_connection(conn)


def get_wiki_spell_count() -> int:
    """Get total count of wiki spells"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM wiki_spells")
        count = cursor.fetchone()[0]
        cursor.close()
        return count
    except Exception as e:
        logger.error(f"Error getting wiki spell count: {e}")
        return 0
    finally:
        if conn:
            return_connection(conn)


def get_all_wiki_spells() -> List[Dict[str, Any]]:
    """Get all wiki spells for matching"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, normalized_name, tier
            FROM wiki_spells
            ORDER BY normalized_name
            """
        )
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'name': row[1],
                'normalized_name': row[2],
                'tier': row[3]
            })
        cursor.close()
        return results
    except Exception as e:
        logger.error(f"Error getting wiki spells: {e}")
        return []
    finally:
        if conn:
            return_connection(conn)


# =============================================================================
# WIKI CLASSES
# =============================================================================

def save_wiki_class(
    name: str,
    normalized_name: str,
    description: Optional[str] = None,
    known_characters: Optional[str] = None,
    reference_chapters: Optional[str] = None,
    is_fake: bool = False,
    class_type: Optional[str] = None
) -> Optional[int]:
    """Save a wiki class to the database"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO wiki_classes (
                name, normalized_name, description, known_characters,
                reference_chapters, is_fake, class_type, scraped_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (normalized_name) DO UPDATE
            SET name = EXCLUDED.name,
                description = EXCLUDED.description,
                known_characters = EXCLUDED.known_characters,
                reference_chapters = EXCLUDED.reference_chapters,
                is_fake = EXCLUDED.is_fake,
                class_type = EXCLUDED.class_type,
                scraped_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (name, normalized_name, description, known_characters, reference_chapters, is_fake, class_type)
        )

        class_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()

        logger.debug(f"Saved wiki class: {name}")
        return class_id
    except Exception as e:
        logger.error(f"Error saving wiki class {name}: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            return_connection(conn)


def save_wiki_classes_batch(classes: List[Dict[str, Any]]) -> int:
    """Save multiple wiki classes in a batch"""
    if not classes:
        return 0

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        from psycopg2.extras import execute_batch
        values = []
        for cls in classes:
            values.append((
                cls['name'],
                cls['normalized_name'],
                cls.get('description'),
                cls.get('known_characters'),
                cls.get('reference_chapters'),
                cls.get('is_fake', False),
                cls.get('class_type')
            ))

        execute_batch(
            cursor,
            """
            INSERT INTO wiki_classes (
                name, normalized_name, description, known_characters,
                reference_chapters, is_fake, class_type, scraped_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (normalized_name) DO UPDATE
            SET name = EXCLUDED.name,
                description = EXCLUDED.description,
                known_characters = EXCLUDED.known_characters,
                reference_chapters = EXCLUDED.reference_chapters,
                is_fake = EXCLUDED.is_fake,
                class_type = EXCLUDED.class_type,
                scraped_at = CURRENT_TIMESTAMP
            """,
            values
        )

        conn.commit()
        count = len(classes)
        cursor.close()

        logger.info(f"Saved {count} wiki classes in batch")
        return count
    except Exception as e:
        logger.error(f"Error saving wiki classes batch: {e}")
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            return_connection(conn)


def get_wiki_class_count() -> int:
    """Get total count of wiki classes"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM wiki_classes")
        count = cursor.fetchone()[0]
        cursor.close()
        return count
    except Exception as e:
        logger.error(f"Error getting wiki class count: {e}")
        return 0
    finally:
        if conn:
            return_connection(conn)


def get_all_wiki_classes() -> List[Dict[str, Any]]:
    """Get all wiki classes for matching"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, normalized_name, is_fake
            FROM wiki_classes
            ORDER BY normalized_name
            """
        )
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'name': row[1],
                'normalized_name': row[2],
                'is_fake': row[3]
            })
        cursor.close()
        return results
    except Exception as e:
        logger.error(f"Error getting wiki classes: {e}")
        return []
    finally:
        if conn:
            return_connection(conn)


def is_fake_class(normalized_name: str) -> bool:
    """Check if a class name matches a fake/hypothetical class"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT is_fake FROM wiki_classes
            WHERE normalized_name = %s
            """,
            (normalized_name,)
        )
        result = cursor.fetchone()
        cursor.close()
        return result[0] if result else False
    except Exception as e:
        logger.error(f"Error checking fake class: {e}")
        return False
    finally:
        if conn:
            return_connection(conn)


# =============================================================================
# WIKI SCRAPE STATE
# =============================================================================

def update_wiki_scrape_state(
    entity_type: str,
    total_count: int,
    last_page_url: Optional[str] = None
):
    """Update the wiki scrape state for an entity type"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO wiki_scrape_state (entity_type, last_scraped_at, total_count, last_page_url)
            VALUES (%s, CURRENT_TIMESTAMP, %s, %s)
            ON CONFLICT (entity_type) DO UPDATE
            SET last_scraped_at = CURRENT_TIMESTAMP,
                total_count = EXCLUDED.total_count,
                last_page_url = EXCLUDED.last_page_url
            """,
            (entity_type, total_count, last_page_url)
        )

        conn.commit()
        cursor.close()
        logger.info(f"Updated wiki scrape state for {entity_type}: {total_count} items")
    except Exception as e:
        logger.error(f"Error updating wiki scrape state: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            return_connection(conn)


def get_wiki_scrape_state(entity_type: str) -> Optional[Dict[str, Any]]:
    """Get the wiki scrape state for an entity type"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT entity_type, last_scraped_at, total_count, last_page_url
            FROM wiki_scrape_state
            WHERE entity_type = %s
            """,
            (entity_type,)
        )
        result = cursor.fetchone()
        cursor.close()

        if result:
            return {
                'entity_type': result[0],
                'last_scraped_at': result[1],
                'total_count': result[2],
                'last_page_url': result[3]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting wiki scrape state: {e}")
        return None
    finally:
        if conn:
            return_connection(conn)


def get_all_wiki_scrape_states() -> List[Dict[str, Any]]:
    """Get all wiki scrape states"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT entity_type, last_scraped_at, total_count
            FROM wiki_scrape_state
            ORDER BY entity_type
            """
        )
        results = []
        for row in cursor.fetchall():
            results.append({
                'entity_type': row[0],
                'last_scraped_at': row[1],
                'total_count': row[2]
            })
        cursor.close()
        return results
    except Exception as e:
        logger.error(f"Error getting wiki scrape states: {e}")
        return []
    finally:
        if conn:
            return_connection(conn)
