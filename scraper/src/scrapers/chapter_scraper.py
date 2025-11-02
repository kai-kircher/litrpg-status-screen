"""Web scraper for extracting chapter content"""

import requests
from bs4 import BeautifulSoup
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from ..config import Config

logger = logging.getLogger(__name__)


class ChapterScraper:
    """Scraper for extracting chapter content from The Wandering Inn website"""

    def __init__(self, base_url: Optional[str] = None, delay: Optional[float] = None):
        """
        Initialize the chapter scraper

        Args:
            base_url: Base URL for the website (defaults to Config.BASE_URL)
            delay: Delay between requests in seconds (defaults to Config.REQUEST_DELAY)
        """
        self.base_url = base_url or Config.BASE_URL
        self.delay = delay if delay is not None else Config.REQUEST_DELAY
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': Config.USER_AGENT
        })
        self.last_request_time = 0

    def _rate_limit(self):
        """Ensure rate limiting between requests"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            sleep_time = self.delay - elapsed
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def fetch_chapter(self, chapter_number: int, url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch a chapter by order_index

        Args:
            chapter_number: Chapter order_index (sequential position) to fetch
            url: Optional chapter URL (if None, will attempt to get from database)

        Returns:
            Dictionary with chapter data or None if failed
            {
                'order_index': int,
                'chapter_number': str (e.g., "1.00"),
                'chapter_title': str (optional),
                'url': str,
                'content': str,
                'published_at': datetime or None,
                'word_count': int
            }
        """
        try:
            # If URL not provided, try to get it from database or construct it
            if url is None:
                # Try to get URL from database first
                from ..db import get_chapter_url
                url = get_chapter_url(chapter_number)

                if url is None:
                    # Fall back to constructing URL (may not work for Wandering Inn)
                    url = self._build_chapter_url(chapter_number)
                    logger.warning(
                        f"No URL found in database for chapter {chapter_number}, "
                        f"using constructed URL: {url}"
                    )

            # Rate limit
            self._rate_limit()

            # Fetch the page
            logger.info(f"Fetching chapter {chapter_number} from {url}")
            response = self.session.get(url, timeout=30)

            if response.status_code == 404:
                logger.warning(f"Chapter {chapter_number} not found (404)")
                return None
            elif response.status_code != 200:
                logger.error(f"Failed to fetch chapter {chapter_number}: HTTP {response.status_code}")
                return None

            # Parse the HTML
            soup = BeautifulSoup(response.content, 'lxml')

            # Extract chapter data
            chapter_data = self._extract_chapter_data(soup, chapter_number, url)

            if chapter_data:
                logger.info(f"Successfully scraped chapter {chapter_number}: {chapter_data['title']}")
            else:
                logger.warning(f"Failed to extract data from chapter {chapter_number}")

            return chapter_data

        except requests.RequestException as e:
            logger.error(f"Network error fetching chapter {chapter_number}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching chapter {chapter_number}: {e}")
            return None

    def _build_chapter_url(self, chapter_number: int) -> str:
        """
        Build the URL for a specific chapter

        Note: This implementation assumes a pattern. You'll need to adjust
        this based on The Wandering Inn's actual URL structure.

        Common patterns:
        - /chapter-{number}/
        - /volume-{vol}/chapter-{num}/
        - /book-{book}/chapter-{num}/
        """
        # TODO: Adjust this based on actual site structure
        # For now, using a generic pattern
        return f"{self.base_url}/chapter-{chapter_number}/"

    def _extract_chapter_data(
        self,
        soup: BeautifulSoup,
        chapter_number: int,
        url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract chapter data from parsed HTML

        Note: This method contains selectors that may need to be adjusted
        based on The Wandering Inn's actual HTML structure.
        """
        try:
            # Extract title (which contains the chapter number like "1.00")
            # Common selectors: h1.entry-title, .chapter-title, h1.post-title
            scraped_title = None
            for selector in ['h1.entry-title', '.chapter-title', 'h1.post-title', 'h1']:
                title_elem = soup.select_one(selector)
                if title_elem:
                    scraped_title = title_elem.get_text(strip=True)
                    break

            if not scraped_title:
                logger.warning(f"Could not find title for chapter {chapter_number}")
                scraped_title = f"{chapter_number}"

            # Extract chapter number (e.g., "1.00") from the scraped title
            # The Wandering Inn format is usually just the chapter number in the title
            chapter_id = scraped_title
            chapter_title = None  # Could parse full title if format is "1.00 - Title"

            # Extract content
            # Common selectors: .entry-content, .chapter-content, article, .post-content
            content = None
            for selector in ['.entry-content', '.chapter-content', 'article', '.post-content']:
                content_elem = soup.select_one(selector)
                if content_elem:
                    # Get text content, preserving paragraphs
                    content = content_elem.get_text(separator='\n\n', strip=True)
                    break

            if not content:
                logger.error(f"Could not find content for chapter {chapter_number}")
                return None

            # Extract published date (if available)
            published_at = None
            for selector in ['time', '.published', '.post-date']:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date_str = date_elem.get('datetime') or date_elem.get_text(strip=True)
                    try:
                        # Try to parse various date formats
                        from dateutil import parser
                        published_at = parser.parse(date_str)
                    except:
                        logger.debug(f"Could not parse date: {date_str}")
                    break

            # Calculate word count
            word_count = len(content.split())

            return {
                'order_index': chapter_number,  # The parameter is actually order_index
                'chapter_number': chapter_id,    # The scraped chapter identifier (e.g., "1.00")
                'chapter_title': chapter_title,  # Optional full title
                'url': url,
                'content': content,
                'published_at': published_at,
                'word_count': word_count
            }

        except Exception as e:
            logger.error(f"Error extracting chapter data: {e}")
            return None

    def test_scraper(self, chapter_number: int = 1) -> bool:
        """
        Test the scraper on a specific chapter

        Args:
            chapter_number: Chapter to test with

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Testing scraper with chapter {chapter_number}")
        result = self.fetch_chapter(chapter_number)

        if result:
            logger.info("Scraper test successful!")
            logger.info(f"Title: {result['title']}")
            logger.info(f"Word count: {result['word_count']}")
            logger.info(f"Content preview: {result['content'][:200]}...")
            return True
        else:
            logger.error("Scraper test failed!")
            return False

    def fetch_chapter_list(self) -> Optional[list]:
        """
        Fetch a list of all available chapters

        This is useful for discovering the total number of chapters.
        The implementation depends on the site structure.

        Returns:
            List of chapter numbers or None if not supported
        """
        # TODO: Implement based on site structure
        # Some sites have a table of contents or archive page
        logger.warning("fetch_chapter_list not implemented - chapter discovery not supported")
        return None

    def close(self):
        """Close the session"""
        self.session.close()
        logger.debug("Scraper session closed")
