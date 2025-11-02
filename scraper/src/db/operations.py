"""Database operations for scraper"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from .connection import get_connection, return_connection

logger = logging.getLogger(__name__)


def chapter_exists(order_index: int) -> bool:
    """Check if a chapter has already been scraped (has content and scraped_at timestamp)"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM chapters WHERE order_index = %s AND scraped_at IS NOT NULL)",
            (order_index,)
        )
        exists = cursor.fetchone()[0]

        cursor.close()
        return exists
    except Exception as e:
        logger.error(f"Error checking if chapter at index {order_index} exists: {e}")
        return False
    finally:
        if conn:
            return_connection(conn)


def get_last_scraped_chapter() -> Optional[int]:
    """Get the last order_index that was scraped"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT MAX(order_index) FROM chapters WHERE scraped_at IS NOT NULL"
        )
        result = cursor.fetchone()

        cursor.close()
        return result[0] if result and result[0] else None
    except Exception as e:
        logger.error(f"Error getting last scraped chapter: {e}")
        return None
    finally:
        if conn:
            return_connection(conn)


def save_chapter(
    order_index: int,
    chapter_number: str,
    url: str,
    content: str,
    published_at: Optional[datetime] = None,
    word_count: Optional[int] = None,
    chapter_title: Optional[str] = None
) -> Optional[int]:
    """
    Save a chapter to the database

    Args:
        order_index: Sequential position in the chapter list
        chapter_number: Chapter identifier (e.g., "1.00", "1.01")
        url: Chapter URL
        content: Chapter content
        published_at: Publication timestamp
        word_count: Word count
        chapter_title: Optional chapter title

    Returns:
        Chapter ID if successful, None otherwise
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO chapters (order_index, chapter_number, url, content, published_at, word_count, chapter_title)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (order_index) DO UPDATE
            SET chapter_number = EXCLUDED.chapter_number,
                url = EXCLUDED.url,
                content = EXCLUDED.content,
                published_at = EXCLUDED.published_at,
                word_count = EXCLUDED.word_count,
                chapter_title = EXCLUDED.chapter_title,
                scraped_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (order_index, chapter_number, url, content, published_at, word_count, chapter_title)
        )

        chapter_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()

        logger.info(f"Saved chapter {chapter_number} (index {order_index})")
        return chapter_id
    except Exception as e:
        logger.error(f"Error saving chapter {chapter_number} (index {order_index}): {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            return_connection(conn)


def save_raw_event(
    chapter_id: int,
    event_type: str,
    raw_text: str,
    parsed_data: Dict[str, Any],
    context: Optional[str] = None
) -> Optional[int]:
    """
    Save a raw progression event to the database

    Args:
        chapter_id: ID of the chapter this event belongs to
        event_type: Type of event (class_obtained, level_up, skill_obtained, spell_obtained)
        raw_text: Original bracketed text
        parsed_data: Structured data extracted from the text
        context: Surrounding text for disambiguation

    Returns:
        Event ID if successful, None otherwise
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO raw_events (chapter_id, event_type, raw_text, parsed_data, context)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (chapter_id, event_type, raw_text, json.dumps(parsed_data), context)
        )

        event_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()

        logger.debug(f"Saved raw event {event_id}: {event_type} - {raw_text}")
        return event_id
    except Exception as e:
        logger.error(f"Error saving raw event: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            return_connection(conn)


def save_raw_events_batch(events: List[Dict[str, Any]]) -> int:
    """
    Save multiple raw events in a batch

    Args:
        events: List of event dictionaries with keys:
            - chapter_id
            - event_type
            - raw_text
            - parsed_data
            - context (optional)

    Returns:
        Number of events saved
    """
    if not events:
        return 0

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Prepare data for batch insert
        values = []
        for event in events:
            values.append((
                event['chapter_id'],
                event['event_type'],
                event['raw_text'],
                json.dumps(event['parsed_data']),
                event.get('context')
            ))

        # Use execute_batch for better performance
        from psycopg2.extras import execute_batch
        execute_batch(
            cursor,
            """
            INSERT INTO raw_events (chapter_id, event_type, raw_text, parsed_data, context)
            VALUES (%s, %s, %s, %s, %s)
            """,
            values
        )

        conn.commit()
        count = len(events)
        cursor.close()

        logger.info(f"Saved {count} raw events in batch")
        return count
    except Exception as e:
        logger.error(f"Error saving raw events batch: {e}")
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            return_connection(conn)


def get_chapter_id(order_index: int) -> Optional[int]:
    """Get chapter ID by order_index"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM chapters WHERE order_index = %s",
            (order_index,)
        )
        result = cursor.fetchone()

        cursor.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting chapter ID for index {order_index}: {e}")
        return None
    finally:
        if conn:
            return_connection(conn)


def save_chapter_metadata(order_index: int, chapter_number: str, url: str) -> Optional[int]:
    """
    Save chapter metadata (from ToC) without content

    This creates a chapter record with just the URL and chapter_number,
    which will be filled in later during scraping.

    Args:
        order_index: Sequential position in chapter list
        chapter_number: Chapter identifier (e.g., "1.00", "1.01")
        url: Chapter URL

    Returns:
        Chapter ID if successful, None otherwise
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO chapters (order_index, chapter_number, url, scraped_at)
            VALUES (%s, %s, %s, NULL)
            ON CONFLICT (order_index) DO UPDATE
            SET chapter_number = EXCLUDED.chapter_number,
                url = EXCLUDED.url,
                scraped_at = NULL
            RETURNING id
            """,
            (order_index, chapter_number, url)
        )

        chapter_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()

        logger.debug(f"Saved chapter metadata {chapter_number} (index {order_index})")
        return chapter_id
    except Exception as e:
        logger.error(f"Error saving chapter metadata {chapter_number} (index {order_index}): {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            return_connection(conn)


def save_chapters_batch(chapters: List[Dict[str, any]]) -> int:
    """
    Save multiple chapter metadata records in a batch (from ToC)

    Args:
        chapters: List of chapter dictionaries with keys:
            - order_index (or chapter_number for backward compatibility)
            - chapter_number (or title for backward compatibility)
            - url

    Returns:
        Number of chapters saved
    """
    if not chapters:
        return 0

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Prepare data for batch insert
        values = []
        for chapter in chapters:
            # Support both old and new key names
            order_index = chapter.get('order_index', chapter.get('chapter_number'))
            chapter_number = chapter.get('chapter_number', chapter.get('title'))
            url = chapter['url']

            values.append((
                order_index,
                chapter_number,
                url
            ))

        # Use execute_batch for better performance
        from psycopg2.extras import execute_batch
        execute_batch(
            cursor,
            """
            INSERT INTO chapters (order_index, chapter_number, url, scraped_at)
            VALUES (%s, %s, %s, NULL)
            ON CONFLICT (order_index) DO UPDATE
            SET chapter_number = EXCLUDED.chapter_number,
                url = EXCLUDED.url,
                scraped_at = NULL
            """,
            values
        )

        conn.commit()
        count = len(chapters)
        cursor.close()

        logger.info(f"Saved {count} chapter metadata records in batch")
        return count
    except Exception as e:
        logger.error(f"Error saving chapters batch: {e}")
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            return_connection(conn)


def get_chapter_url(order_index: int) -> Optional[str]:
    """Get chapter URL by order_index"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT url FROM chapters WHERE order_index = %s",
            (order_index,)
        )
        result = cursor.fetchone()

        cursor.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting chapter URL for index {order_index}: {e}")
        return None
    finally:
        if conn:
            return_connection(conn)


def get_total_chapters() -> int:
    """Get total number of chapters with metadata"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM chapters")
        result = cursor.fetchone()

        cursor.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting total chapters: {e}")
        return 0
    finally:
        if conn:
            return_connection(conn)
