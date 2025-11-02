"""Database operations module"""

from .connection import get_connection, close_connection, return_connection, close_all_connections, init_pool, test_connection
from .operations import (
    save_chapter,
    save_raw_event,
    chapter_exists,
    get_last_scraped_chapter,
    save_chapter_metadata,
    save_chapters_batch,
    get_chapter_url,
    get_total_chapters,
    save_raw_events_batch,
)

__all__ = [
    "get_connection",
    "close_connection",
    "return_connection",
    "close_all_connections",
    "init_pool",
    "test_connection",
    "save_chapter",
    "save_raw_event",
    "chapter_exists",
    "get_last_scraped_chapter",
    "save_chapter_metadata",
    "save_chapters_batch",
    "get_chapter_url",
    "get_total_chapters",
    "save_raw_events_batch",
]
