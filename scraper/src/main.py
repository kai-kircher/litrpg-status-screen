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


if __name__ == '__main__':
    cli()
