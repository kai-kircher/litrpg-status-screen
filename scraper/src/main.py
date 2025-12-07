"""Command-line interface for the Wandering Inn scraper"""

import click
import logging
import colorlog
import sys
from .scraper import WanderingInnScraper
from .db import test_connection, init_pool


def setup_logging(verbose: bool = False):
    """Setup colored logging"""
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create colored formatter
    formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s',
        datefmt=None,
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )

    # Setup handler
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)


@click.group()
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose logging')
def cli(verbose):
    """Wandering Inn Tracker - Web Scraper

    Scrapes chapters from The Wandering Inn and extracts character progression events.
    """
    setup_logging(verbose)


@cli.command()
@click.option(
    '--start', '-s',
    type=int,
    help='Chapter to start from (defaults to 1 or last scraped + 1)'
)
@click.option(
    '--end', '-e',
    type=int,
    help='Chapter to end at (optional)'
)
@click.option(
    '--max', '-m',
    type=int,
    help='Maximum number of chapters to scrape'
)
@click.option(
    '--no-resume',
    is_flag=True,
    help='Do not resume from last scraped chapter'
)
def scrape(start, end, max, no_resume):
    """Scrape chapters from The Wandering Inn"""
    scraper = WanderingInnScraper()

    try:
        stats = scraper.run(
            start_chapter=start,
            end_chapter=end,
            max_chapters=max,
            resume=not no_resume
        )

        # Exit with error code if there were errors
        if stats['errors'] > 0:
            sys.exit(1)

    except Exception as e:
        logging.error(f"Scraper failed: {e}")
        sys.exit(1)


@cli.command()
@click.argument('chapter_number', type=int)
def test(chapter_number):
    """Test the scraper on a specific chapter without saving to database"""
    scraper = WanderingInnScraper()

    try:
        success = scraper.test_scraper(chapter_number)
        if not success:
            logging.error("Test failed")
            sys.exit(1)
        else:
            logging.info("Test successful!")
    except Exception as e:
        logging.error(f"Test failed: {e}")
        sys.exit(1)
    finally:
        scraper.cleanup()


@cli.command()
def check_db():
    """Check database connection"""
    try:
        init_pool()
        if test_connection():
            logging.info("✓ Database connection successful")
        else:
            logging.error("✗ Database connection failed")
            sys.exit(1)
    except Exception as e:
        logging.error(f"✗ Database connection failed: {e}")
        sys.exit(1)


@cli.command()
@click.argument('chapter_number', type=int)
def fetch(chapter_number):
    """Fetch and display a single chapter"""
    from .scrapers import ChapterScraper

    scraper = ChapterScraper()

    try:
        chapter_data = scraper.fetch_chapter(chapter_number)

        if not chapter_data:
            logging.error(f"Failed to fetch chapter {chapter_number}")
            sys.exit(1)

        click.echo("\n" + "=" * 60)
        click.echo(f"Chapter {chapter_data['order_index']}: {chapter_data['chapter_number']}")
        if chapter_data.get('chapter_title'):
            click.echo(f"Title: {chapter_data['chapter_title']}")
        click.echo("=" * 60)
        click.echo(f"URL: {chapter_data['url']}")
        click.echo(f"Word count: {chapter_data['word_count']}")
        if chapter_data.get('published_at'):
            click.echo(f"Published: {chapter_data['published_at']}")
        click.echo("\nContent preview:")
        click.echo(chapter_data['content'][:500] + "...")
        click.echo("=" * 60)

    except Exception as e:
        logging.error(f"Failed to fetch chapter: {e}")
        sys.exit(1)
    finally:
        scraper.close()


@cli.command()
@click.argument('text', type=click.File('r'))
def parse(text):
    """Parse progression events from a text file"""
    from .parsers import EventParser

    parser = EventParser()

    try:
        content = text.read()
        events = parser.parse_and_validate(content)

        stats = parser.get_event_stats(events)

        click.echo(f"\nFound {stats['total']} events:")
        click.echo(f"  Classes: {stats['class_obtained']}")
        click.echo(f"  Levels: {stats['level_up']}")
        click.echo(f"  Skills: {stats['skill_obtained']}")
        click.echo(f"  Spells: {stats['spell_obtained']}")

        if events:
            click.echo("\nEvents:")
            for event in events:
                click.echo(f"  [{event.event_type}] {event.raw_text}")
                click.echo(f"    Data: {event.parsed_data}")
                click.echo(f"    Context: {event.context[:100]}...")
                click.echo()

    except Exception as e:
        logging.error(f"Failed to parse text: {e}")
        sys.exit(1)


@cli.command()
def build_toc():
    """Build chapter list from Table of Contents"""
    from .scrapers import TocScraper
    from .db import init_pool, save_chapters_batch

    try:
        # Initialize database
        init_pool()

        # Fetch ToC
        toc_scraper = TocScraper()
        chapters = toc_scraper.fetch_chapter_list()

        if not chapters:
            logging.error("Failed to fetch chapter list from ToC")
            sys.exit(1)

        # Display summary
        toc_scraper.display_chapter_summary(chapters)

        # Save to database
        logging.info("Saving chapter metadata to database...")
        count = save_chapters_batch(chapters)

        if count > 0:
            logging.info(f"✓ Successfully saved {count} chapters to database")

            # Also save to JSON file as backup
            toc_scraper.save_chapter_list_to_file(chapters, 'chapters.json')
            logging.info("✓ Also saved to chapters.json as backup")
        else:
            logging.error("✗ Failed to save chapters to database")
            sys.exit(1)

    except Exception as e:
        logging.error(f"Failed to build ToC: {e}")
        sys.exit(1)
    finally:
        if 'toc_scraper' in locals():
            toc_scraper.close()


@cli.command()
def show_toc():
    """Show chapter statistics from database"""
    from .db import init_pool, get_total_chapters

    try:
        init_pool()
        total = get_total_chapters()

        if total == 0:
            logging.warning("No chapters found in database")
            logging.info("Run 'python -m src.main build-toc' first to fetch chapter list")
        else:
            logging.info(f"Total chapters in database: {total}")

            # Get some sample chapters
            from .db import get_connection, return_connection
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT order_index, chapter_number, url FROM chapters ORDER BY order_index LIMIT 5"
            )
            first_chapters = cursor.fetchall()

            cursor.execute(
                "SELECT order_index, chapter_number, url FROM chapters ORDER BY order_index DESC LIMIT 5"
            )
            last_chapters = cursor.fetchall()

            cursor.close()
            return_connection(conn)

            click.echo("\nFirst 5 chapters:")
            for order_idx, chapter_num, url in first_chapters:
                click.echo(f"  {order_idx}: {chapter_num}")
                click.echo(f"     {url}")

            click.echo("\nLast 5 chapters:")
            for order_idx, chapter_num, url in reversed(last_chapters):
                click.echo(f"  {order_idx}: {chapter_num}")
                click.echo(f"     {url}")

    except Exception as e:
        logging.error(f"Failed to show ToC: {e}")
        sys.exit(1)


@cli.command()
def version():
    """Show version information"""
    from . import __version__
    click.echo(f"Wandering Inn Tracker Scraper v{__version__}")


# ============================================================================
# AI PROCESSING COMMANDS
# ============================================================================

@cli.command('extract-characters')
@click.option('--start', '-s', type=int, default=1, help='Starting chapter index')
@click.option('--end', '-e', type=int, help='Ending chapter index')
@click.option('--chapter', '-c', type=int, help='Process single chapter')
@click.option('--dry-run', is_flag=True, help='Preview without saving to database')
def extract_characters(start, end, chapter, dry_run):
    """Extract characters from chapters using AI"""
    from .db import init_pool, get_connection, return_connection
    from .ai import CharacterExtractor, CostTracker

    try:
        init_pool()

        # Get chapters to process
        conn = get_connection()
        cursor = conn.cursor()

        if chapter:
            cursor.execute(
                """
                SELECT id, order_index, chapter_number, content
                FROM chapters
                WHERE order_index = %s AND content IS NOT NULL
                """,
                (chapter,)
            )
        else:
            query = """
                SELECT c.id, c.order_index, c.chapter_number, c.content
                FROM chapters c
                LEFT JOIN ai_chapter_state acs ON c.id = acs.chapter_id
                WHERE c.content IS NOT NULL
                  AND c.order_index >= %s
                  AND (acs.characters_extracted IS NULL OR acs.characters_extracted = FALSE)
            """
            params = [start]
            if end:
                query += " AND c.order_index <= %s"
                params.append(end)
            query += " ORDER BY c.order_index"
            cursor.execute(query, params)

        chapters = cursor.fetchall()
        cursor.close()
        return_connection(conn)

        if not chapters:
            logging.info("No chapters to process")
            return

        logging.info(f"Processing {len(chapters)} chapters for character extraction")

        if dry_run:
            logging.info("DRY RUN - no changes will be saved")

        # Initialize extractor
        cost_tracker = CostTracker()
        extractor = CharacterExtractor(cost_tracker=cost_tracker)

        total_characters = 0
        total_new = 0

        for chapter_id, order_index, chapter_number, content in chapters:
            try:
                logging.info(f"Processing chapter {order_index}: {chapter_number}")

                characters, response = extractor.extract_characters(
                    chapter_text=content,
                    chapter_id=chapter_id,
                    chapter_number=chapter_number
                )

                new_chars = [c for c in characters if c.is_new]

                if not dry_run:
                    # Save new characters
                    new_count = extractor.save_new_characters(characters, chapter_id)

                    # Update chapter state
                    extractor.update_chapter_state(
                        chapter_id=chapter_id,
                        characters_found=len(characters),
                        new_characters=new_count
                    )

                    total_new += new_count
                else:
                    logging.info(f"  Would create {len(new_chars)} new characters")

                total_characters += len(characters)

                # Show sample characters
                if characters[:5]:
                    logging.info(f"  Sample characters: {[c.name for c in characters[:5]]}")
                if new_chars[:3]:
                    logging.info(f"  New characters: {[c.name for c in new_chars[:3]]}")

            except Exception as e:
                logging.error(f"Failed to process chapter {chapter_number}: {e}")
                continue

        # Show summary
        click.echo("\n" + "=" * 60)
        click.echo("Character Extraction Summary")
        click.echo("=" * 60)
        click.echo(f"Chapters processed: {len(chapters)}")
        click.echo(f"Characters found: {total_characters}")
        click.echo(f"New characters created: {total_new}")

        # Show costs
        summary = cost_tracker.get_session_summary()
        click.echo(f"\nAI Usage:")
        click.echo(f"  Requests: {summary['total_requests']}")
        click.echo(f"  Input tokens: {summary['total_input_tokens']:,}")
        click.echo(f"  Output tokens: {summary['total_output_tokens']:,}")
        click.echo(f"  Estimated cost: ${summary['total_cost_usd']:.4f}")

    except Exception as e:
        logging.error(f"Character extraction failed: {e}")
        sys.exit(1)


@cli.command('attribute-events')
@click.option('--start', '-s', type=int, default=1, help='Starting chapter index')
@click.option('--end', '-e', type=int, help='Ending chapter index')
@click.option('--chapter', '-c', type=int, help='Process single chapter')
@click.option('--dry-run', is_flag=True, help='Preview without saving to database')
def attribute_events(start, end, chapter, dry_run):
    """Attribute events to characters using AI"""
    from .db import init_pool, get_connection, return_connection
    from .ai import EventAttributor, CharacterExtractor, CostTracker
    from .ai.event_attributor import get_unprocessed_events

    try:
        init_pool()

        # Get chapters to process
        conn = get_connection()
        cursor = conn.cursor()

        if chapter:
            cursor.execute(
                """
                SELECT c.id, c.order_index, c.chapter_number
                FROM chapters c
                WHERE c.order_index = %s
                """,
                (chapter,)
            )
        else:
            query = """
                SELECT c.id, c.order_index, c.chapter_number
                FROM chapters c
                WHERE c.order_index >= %s
                  AND EXISTS (
                      SELECT 1 FROM raw_events re
                      WHERE re.chapter_id = c.id
                        AND re.ai_confidence IS NULL
                        AND re.archived = FALSE
                  )
            """
            params = [start]
            if end:
                query += " AND c.order_index <= %s"
                params.append(end)
            query += " ORDER BY c.order_index"
            cursor.execute(query, params)

        chapters = cursor.fetchall()
        cursor.close()
        return_connection(conn)

        if not chapters:
            logging.info("No chapters with unprocessed events")
            return

        logging.info(f"Processing {len(chapters)} chapters for event attribution")

        if dry_run:
            logging.info("DRY RUN - no changes will be saved")

        # Initialize
        cost_tracker = CostTracker()
        extractor = CharacterExtractor(cost_tracker=cost_tracker)
        attributor = EventAttributor(
            cost_tracker=cost_tracker,
            character_extractor=extractor
        )

        total_events = 0
        total_auto_accepted = 0
        total_flagged = 0

        for chapter_id, order_index, chapter_number in chapters:
            try:
                # Get unprocessed events for this chapter
                events = get_unprocessed_events(chapter_id)

                if not events:
                    continue

                logging.info(f"Chapter {order_index} ({chapter_number}): {len(events)} events to process")

                # Get characters mentioned in this chapter (from cache/db)
                # For now, use all known characters
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM characters ORDER BY name")
                chapter_characters = [row[0] for row in cursor.fetchall()]
                cursor.close()
                return_connection(conn)

                # Attribute events
                attributions, responses = attributor.attribute_events(
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    events=events,
                    chapter_characters=chapter_characters
                )

                if not dry_run:
                    # Save attributions
                    stats = attributor.save_attributions(attributions)

                    # Update chapter state
                    attributor.update_chapter_state(
                        chapter_id=chapter_id,
                        events_processed=len(events),
                        auto_accepted=stats['auto_accepted'],
                        flagged_review=stats['flagged_review']
                    )

                    total_auto_accepted += stats['auto_accepted']
                    total_flagged += stats['flagged_review']
                else:
                    auto = sum(1 for a in attributions if a.auto_accepted)
                    flagged = sum(1 for a in attributions if a.needs_review)
                    logging.info(f"  Would auto-accept: {auto}, flag for review: {flagged}")

                total_events += len(events)

                # Show sample attributions
                for attr in attributions[:3]:
                    logging.info(
                        f"  [{attr.event_type}] -> {attr.character_name or 'Unknown'} "
                        f"(conf: {attr.confidence:.2f})"
                    )

            except Exception as e:
                logging.error(f"Failed to process chapter {chapter_number}: {e}")
                continue

        # Show summary
        click.echo("\n" + "=" * 60)
        click.echo("Event Attribution Summary")
        click.echo("=" * 60)
        click.echo(f"Chapters processed: {len(chapters)}")
        click.echo(f"Events processed: {total_events}")
        click.echo(f"Auto-accepted (>=0.93): {total_auto_accepted}")
        click.echo(f"Flagged for review (<0.93): {total_flagged}")

        # Show costs
        summary = cost_tracker.get_session_summary()
        click.echo(f"\nAI Usage:")
        click.echo(f"  Requests: {summary['total_requests']}")
        click.echo(f"  Input tokens: {summary['total_input_tokens']:,}")
        click.echo(f"  Output tokens: {summary['total_output_tokens']:,}")
        click.echo(f"  Estimated cost: ${summary['total_cost_usd']:.4f}")

    except Exception as e:
        logging.error(f"Event attribution failed: {e}")
        sys.exit(1)


@cli.command('process-ai')
@click.option('--start', '-s', type=int, default=1, help='Starting chapter index')
@click.option('--end', '-e', type=int, help='Ending chapter index')
@click.option('--chapter', '-c', type=int, help='Process single chapter')
@click.option('--dry-run', is_flag=True, help='Preview without saving to database')
def process_ai(start, end, chapter, dry_run):
    """Run full AI processing (characters + events) on chapters"""
    from .db import init_pool, get_connection, return_connection
    from .ai import CharacterExtractor, EventAttributor, CostTracker
    from .ai.event_attributor import get_unprocessed_events

    try:
        init_pool()

        # Get chapters to process
        conn = get_connection()
        cursor = conn.cursor()

        if chapter:
            cursor.execute(
                """
                SELECT id, order_index, chapter_number, content
                FROM chapters
                WHERE order_index = %s AND content IS NOT NULL
                """,
                (chapter,)
            )
        else:
            query = """
                SELECT id, order_index, chapter_number, content
                FROM chapters
                WHERE content IS NOT NULL
                  AND order_index >= %s
            """
            params = [start]
            if end:
                query += " AND order_index <= %s"
                params.append(end)
            query += " ORDER BY order_index"
            cursor.execute(query, params)

        chapters = cursor.fetchall()
        cursor.close()
        return_connection(conn)

        if not chapters:
            logging.info("No chapters to process")
            return

        logging.info(f"Processing {len(chapters)} chapters with AI")

        if dry_run:
            logging.info("DRY RUN - no changes will be saved")

        # Initialize
        cost_tracker = CostTracker()
        extractor = CharacterExtractor(cost_tracker=cost_tracker)
        attributor = EventAttributor(
            cost_tracker=cost_tracker,
            character_extractor=extractor
        )

        stats = {
            'chapters': 0,
            'characters_found': 0,
            'new_characters': 0,
            'events_processed': 0,
            'auto_accepted': 0,
            'flagged_review': 0
        }

        for chapter_id, order_index, chapter_number, content in chapters:
            try:
                logging.info(f"\n{'='*40}")
                logging.info(f"Chapter {order_index}: {chapter_number}")
                logging.info(f"{'='*40}")

                # Step 1: Extract characters
                logging.info("Step 1: Extracting characters...")
                characters, _ = extractor.extract_characters(
                    chapter_text=content,
                    chapter_id=chapter_id,
                    chapter_number=chapter_number
                )

                new_chars = [c for c in characters if c.is_new]

                if not dry_run:
                    new_count = extractor.save_new_characters(characters, chapter_id)
                    extractor.update_chapter_state(
                        chapter_id=chapter_id,
                        characters_found=len(characters),
                        new_characters=new_count
                    )
                    stats['new_characters'] += new_count
                else:
                    new_count = len(new_chars)

                stats['characters_found'] += len(characters)
                logging.info(f"  Found {len(characters)} characters ({new_count} new)")

                # Step 2: Attribute events
                events = get_unprocessed_events(chapter_id)

                if events:
                    logging.info(f"Step 2: Attributing {len(events)} events...")

                    # Get chapter characters for attribution
                    chapter_characters = [c.name for c in characters]

                    attributions, _ = attributor.attribute_events(
                        chapter_id=chapter_id,
                        chapter_number=chapter_number,
                        events=events,
                        chapter_characters=chapter_characters
                    )

                    if not dry_run:
                        result = attributor.save_attributions(attributions)
                        attributor.update_chapter_state(
                            chapter_id=chapter_id,
                            events_processed=len(events),
                            auto_accepted=result['auto_accepted'],
                            flagged_review=result['flagged_review']
                        )
                        stats['auto_accepted'] += result['auto_accepted']
                        stats['flagged_review'] += result['flagged_review']
                    else:
                        auto = sum(1 for a in attributions if a.auto_accepted)
                        flagged = sum(1 for a in attributions if a.needs_review)
                        stats['auto_accepted'] += auto
                        stats['flagged_review'] += flagged

                    stats['events_processed'] += len(events)
                    logging.info(f"  Processed {len(events)} events")
                else:
                    logging.info("Step 2: No events to process")

                stats['chapters'] += 1

            except Exception as e:
                logging.error(f"Failed to process chapter {chapter_number}: {e}")
                continue

        # Show summary
        click.echo("\n" + "=" * 60)
        click.echo("AI Processing Summary")
        click.echo("=" * 60)
        click.echo(f"Chapters processed: {stats['chapters']}")
        click.echo(f"Characters found: {stats['characters_found']}")
        click.echo(f"New characters: {stats['new_characters']}")
        click.echo(f"Events processed: {stats['events_processed']}")
        click.echo(f"  Auto-accepted: {stats['auto_accepted']}")
        click.echo(f"  Flagged for review: {stats['flagged_review']}")

        # Show costs
        summary = cost_tracker.get_session_summary()
        click.echo(f"\nAI Usage:")
        click.echo(f"  Requests: {summary['total_requests']}")
        click.echo(f"  Input tokens: {summary['total_input_tokens']:,}")
        click.echo(f"  Output tokens: {summary['total_output_tokens']:,}")
        click.echo(f"  Estimated cost: ${summary['total_cost_usd']:.4f}")

    except Exception as e:
        logging.error(f"AI processing failed: {e}")
        sys.exit(1)


@cli.command('ai-stats')
@click.option('--days', '-d', type=int, default=30, help='Number of days to look back')
def ai_stats(days):
    """Show AI usage statistics"""
    from .db import init_pool
    from .ai.cost_tracker import get_cost_stats

    try:
        init_pool()
        stats = get_cost_stats(days=days)

        if 'error' in stats:
            logging.error(f"Failed to get stats: {stats['error']}")
            sys.exit(1)

        click.echo("\n" + "=" * 60)
        click.echo(f"AI Usage Statistics (Last {days} days)")
        click.echo("=" * 60)
        click.echo(f"Total requests: {stats['total_requests']}")
        click.echo(f"Chapters processed: {stats['chapters_processed']}")
        click.echo(f"Input tokens: {stats['total_input_tokens']:,}")
        click.echo(f"Output tokens: {stats['total_output_tokens']:,}")
        click.echo(f"Total cost: ${stats['total_cost_usd']:.4f}")

        if stats.get('by_model'):
            click.echo("\nBy Model:")
            for model, data in stats['by_model'].items():
                click.echo(f"  {model}:")
                click.echo(f"    Requests: {data['requests']}, Cost: ${data['cost']:.4f}")

        if stats.get('by_type'):
            click.echo("\nBy Processing Type:")
            for ptype, data in stats['by_type'].items():
                click.echo(f"  {ptype}:")
                click.echo(f"    Requests: {data['requests']}, Cost: ${data['cost']:.4f}")

    except Exception as e:
        logging.error(f"Failed to get AI stats: {e}")
        sys.exit(1)


@cli.command('review-queue')
@click.option('--limit', '-l', type=int, default=20, help='Number of events to show')
def review_queue(limit):
    """Show events that need manual review"""
    from .db import init_pool, get_connection, return_connection

    try:
        init_pool()
        conn = get_connection()
        cursor = conn.cursor()

        # Get count of events needing review
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM raw_events
            WHERE needs_review = TRUE AND archived = FALSE
            """
        )
        total = cursor.fetchone()[0]

        # Get sample events
        cursor.execute(
            """
            SELECT
                re.id, re.raw_text, re.event_type, re.ai_confidence, re.ai_reasoning,
                c.chapter_number, ch.name as character_name
            FROM raw_events re
            JOIN chapters c ON re.chapter_id = c.id
            LEFT JOIN characters ch ON re.character_id = ch.id
            WHERE re.needs_review = TRUE AND re.archived = FALSE
            ORDER BY re.ai_confidence DESC NULLS LAST
            LIMIT %s
            """,
            (limit,)
        )
        events = cursor.fetchall()

        cursor.close()
        return_connection(conn)

        click.echo("\n" + "=" * 60)
        click.echo(f"Review Queue ({total} events total)")
        click.echo("=" * 60)

        if not events:
            click.echo("No events need review!")
            return

        for event_id, raw_text, event_type, confidence, reasoning, chapter, character in events:
            click.echo(f"\nEvent #{event_id} (Chapter {chapter})")
            click.echo(f"  Type: {event_type or 'unclassified'}")
            click.echo(f"  Text: {raw_text[:80]}...")
            click.echo(f"  Character: {character or 'Unassigned'}")
            click.echo(f"  Confidence: {confidence:.2f if confidence else 'N/A'}")
            if reasoning:
                click.echo(f"  AI Reasoning: {reasoning[:100]}...")

        if total > limit:
            click.echo(f"\n... and {total - limit} more events")

    except Exception as e:
        logging.error(f"Failed to get review queue: {e}")
        sys.exit(1)


if __name__ == '__main__':
    cli()
