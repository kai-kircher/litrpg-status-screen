"""Main scraper orchestration"""

import logging
from typing import Optional
from .scrapers import ChapterScraper
from .parsers import EventParser
from .db import (
    init_pool,
    close_all_connections,
    test_connection,
    chapter_exists,
    get_last_scraped_chapter,
    save_chapter,
    save_raw_events_batch,
)
from .config import Config

logger = logging.getLogger(__name__)


class WanderingInnScraper:
    """Main scraper orchestrator for The Wandering Inn"""

    def __init__(self):
        """Initialize the scraper"""
        self.chapter_scraper = ChapterScraper()
        self.event_parser = EventParser()
        self.stats = {
            'chapters_scraped': 0,
            'chapters_skipped': 0,
            'chapters_failed': 0,  # Completely failed to scrape
            'chapters_partial': 0,  # Scraped but parsing had issues
            'events_found': 0,
            'events_incomplete': 0,  # Intentionally incomplete/cancelled
            'parsing_errors': 0,  # Events that failed to parse
            'errors': 0  # General errors
        }

    def run(
        self,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None,
        max_chapters: Optional[int] = None,
        resume: bool = True
    ) -> dict:
        """
        Run the scraper

        Args:
            start_chapter: Chapter to start from (defaults to Config.START_CHAPTER or 1)
            end_chapter: Chapter to end at (None = scrape until 404)
            max_chapters: Maximum number of chapters to scrape (None = unlimited)
            resume: Whether to resume from last scraped chapter

        Returns:
            Dictionary with scraping statistics
        """
        logger.info("Starting Wandering Inn scraper")

        # Initialize database connection
        try:
            init_pool()
            if not test_connection():
                logger.error("Database connection test failed")
                return self.stats
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return self.stats

        # Determine starting chapter
        if resume and start_chapter is None:
            last_chapter = get_last_scraped_chapter()
            if last_chapter:
                start_chapter = last_chapter + 1
                logger.info(f"Resuming from chapter {start_chapter}")
            else:
                start_chapter = Config.START_CHAPTER or 1
        else:
            start_chapter = start_chapter or Config.START_CHAPTER or 1

        # Apply max_chapters if specified
        if max_chapters:
            max_chapters = max_chapters or Config.MAX_CHAPTERS
            if max_chapters > 0:
                end_chapter = start_chapter + max_chapters - 1
                logger.info(f"Limiting to {max_chapters} chapters")

        logger.info(f"Starting scrape from chapter {start_chapter}")
        if end_chapter:
            logger.info(f"Ending at chapter {end_chapter}")

        # Scrape chapters
        current_chapter = start_chapter
        consecutive_failures = 0
        max_consecutive_failures = 5

        try:
            while True:
                # Check if we've reached the end
                if end_chapter and current_chapter > end_chapter:
                    logger.info(f"Reached end chapter {end_chapter}")
                    break

                # Check if chapter already exists (unless forcing re-scrape)
                if chapter_exists(current_chapter):
                    logger.info(f"Chapter {current_chapter} already exists, skipping")
                    self.stats['chapters_skipped'] += 1
                    current_chapter += 1
                    continue

                # Scrape the chapter
                success = self.scrape_chapter(current_chapter)

                if success:
                    consecutive_failures = 0
                    current_chapter += 1
                else:
                    consecutive_failures += 1
                    logger.warning(
                        f"Failed to scrape chapter {current_chapter} "
                        f"({consecutive_failures}/{max_consecutive_failures} failures)"
                    )

                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(
                            f"Stopping after {max_consecutive_failures} consecutive failures"
                        )
                        break

                    # Still try the next chapter
                    current_chapter += 1

                # Check max_chapters limit
                if max_chapters and self.stats['chapters_scraped'] >= max_chapters:
                    logger.info(f"Reached max chapters limit ({max_chapters})")
                    break

        except KeyboardInterrupt:
            logger.warning("Scraping interrupted by user")
        except Exception as e:
            logger.error(f"Unexpected error during scraping: {e}")
        finally:
            self.cleanup()

        # Log final statistics
        self._log_final_stats()

        return self.stats

    def scrape_chapter(self, chapter_number: int) -> bool:
        """
        Scrape a single chapter and save to database

        This method is resilient to partial failures - it will save the chapter
        even if event parsing fails or has issues.

        Args:
            chapter_number: Chapter number to scrape

        Returns:
            True if chapter was fetched and saved (even if events failed),
            False only if chapter fetch/save completely failed
        """
        chapter_saved = False
        parsing_had_issues = False

        try:
            # Fetch chapter
            chapter_data = self.chapter_scraper.fetch_chapter(chapter_number)

            if not chapter_data:
                logger.error(f"Failed to fetch chapter {chapter_number}")
                self.stats['chapters_failed'] += 1
                self.stats['errors'] += 1
                return False

            # Validate chapter data
            if not chapter_data.get('content'):
                logger.warning(f"Chapter {chapter_number} has no content")
                # Still try to save metadata
                parsing_had_issues = True

            # Save chapter to database (even if content is empty)
            try:
                chapter_id = save_chapter(
                    order_index=chapter_data['order_index'],
                    chapter_number=chapter_data['chapter_number'],
                    url=chapter_data['url'],
                    content=chapter_data.get('content', ''),
                    published_at=chapter_data.get('published_at'),
                    word_count=chapter_data.get('word_count', 0),
                    chapter_title=chapter_data.get('chapter_title')
                )

                if not chapter_id:
                    logger.error(f"Failed to save chapter {chapter_number} to database")
                    self.stats['chapters_failed'] += 1
                    self.stats['errors'] += 1
                    return False

                chapter_saved = True

            except Exception as e:
                logger.error(f"Database error saving chapter {chapter_number}: {e}")
                self.stats['chapters_failed'] += 1
                self.stats['errors'] += 1
                return False

            # Parse events from chapter content (continue even if this fails)
            events = []
            try:
                if chapter_data.get('content'):
                    events = self.event_parser.parse_and_validate(chapter_data['content'])

                    # Check for parsing errors
                    if hasattr(self.event_parser, 'parse_errors') and self.event_parser.parse_errors:
                        parsing_had_issues = True
                        self.stats['parsing_errors'] += len(self.event_parser.parse_errors)
                        logger.warning(
                            f"Chapter {chapter_number}: {len(self.event_parser.parse_errors)} "
                            f"events failed to parse"
                        )

            except Exception as e:
                logger.warning(f"Event parsing failed for chapter {chapter_number}: {e}")
                parsing_had_issues = True
                self.stats['parsing_errors'] += 1
                # Continue - chapter is still saved

            # Log event statistics
            event_stats = self.event_parser.get_event_stats(events)
            incomplete_count = sum(1 for e in events if e.is_incomplete)

            logger.info(
                f"Chapter {chapter_number} ({chapter_data.get('title', 'Unknown')}): "
                f"Found {event_stats['total']} events - "
                f"{event_stats['class_obtained']} classes, "
                f"{event_stats['level_up']} levels, "
                f"{event_stats['skill_obtained']} skills, "
                f"{event_stats['spell_obtained']} spells"
            )

            if incomplete_count > 0:
                logger.info(f"  ({incomplete_count} incomplete/cancelled events)")
                self.stats['events_incomplete'] += incomplete_count

            # Save events to database (continue even if this fails)
            if events:
                try:
                    event_dicts = [
                        {
                            'chapter_id': chapter_id,
                            'event_type': event.event_type,
                            'raw_text': event.raw_text,
                            'parsed_data': event.parsed_data,
                            'context': event.context
                        }
                        for event in events
                    ]

                    saved_count = save_raw_events_batch(event_dicts)
                    self.stats['events_found'] += saved_count

                except Exception as e:
                    logger.warning(f"Failed to save events for chapter {chapter_number}: {e}")
                    parsing_had_issues = True
                    # Continue - chapter is still saved

            # Update statistics
            if parsing_had_issues:
                self.stats['chapters_partial'] += 1
            else:
                self.stats['chapters_scraped'] += 1

            return True

        except Exception as e:
            logger.error(f"Unexpected error scraping chapter {chapter_number}: {e}")
            if not chapter_saved:
                self.stats['chapters_failed'] += 1
            else:
                self.stats['chapters_partial'] += 1
            self.stats['errors'] += 1
            return chapter_saved  # Return True if we at least saved the chapter

    def test_scraper(self, chapter_number: int = 1) -> bool:
        """
        Test the scraper on a specific chapter without saving to database

        Args:
            chapter_number: Chapter to test with

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Testing scraper with chapter {chapter_number}")

        # Test chapter fetching
        chapter_data = self.chapter_scraper.fetch_chapter(chapter_number)
        if not chapter_data:
            logger.error("Failed to fetch chapter")
            return False

        logger.info(f"Successfully fetched chapter: {chapter_data['chapter_number']}")
        logger.info(f"Word count: {chapter_data['word_count']}")

        # Test event parsing
        events = self.event_parser.parse_and_validate(chapter_data['content'])
        event_stats = self.event_parser.get_event_stats(events)

        logger.info(f"Found {event_stats['total']} events:")
        logger.info(f"  - Classes: {event_stats['class_obtained']}")
        logger.info(f"  - Levels: {event_stats['level_up']}")
        logger.info(f"  - Skills: {event_stats['skill_obtained']}")
        logger.info(f"  - Spells: {event_stats['spell_obtained']}")

        # Show sample events
        if events:
            logger.info("Sample events:")
            for event in events[:5]:
                logger.info(f"  - {event.event_type}: {event.raw_text}")

        return True

    def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up resources")
        self.chapter_scraper.close()
        close_all_connections()

    def _log_final_stats(self):
        """Log final scraping statistics"""
        total_processed = (
            self.stats['chapters_scraped'] +
            self.stats['chapters_partial'] +
            self.stats['chapters_failed']
        )

        logger.info("=" * 60)
        logger.info("Scraping completed")
        logger.info("=" * 60)
        logger.info(f"Chapters processed: {total_processed}")
        logger.info(f"  ✓ Fully scraped: {self.stats['chapters_scraped']}")
        logger.info(f"  ⚠ Partial (with issues): {self.stats['chapters_partial']}")
        logger.info(f"  ✗ Failed: {self.stats['chapters_failed']}")
        logger.info(f"  ⊘ Skipped (already existed): {self.stats['chapters_skipped']}")
        logger.info("")
        logger.info(f"Events found: {self.stats['events_found']}")
        if self.stats['events_incomplete'] > 0:
            logger.info(f"  Incomplete/cancelled: {self.stats['events_incomplete']}")
        if self.stats['parsing_errors'] > 0:
            logger.warning(f"  Parsing errors: {self.stats['parsing_errors']}")
        logger.info("")
        if self.stats['errors'] > 0:
            logger.warning(f"Total errors: {self.stats['errors']}")
        logger.info("=" * 60)
