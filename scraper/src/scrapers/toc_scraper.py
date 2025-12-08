"""Table of Contents scraper for building ordered chapter list"""

import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin
from ..config import Config

logger = logging.getLogger(__name__)


class TocScraper:
    """Scraper for extracting chapter list from Table of Contents"""

    TOC_URL = "https://wanderinginn.com/table-of-contents/"

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the ToC scraper

        Args:
            base_url: Base URL for the website (defaults to Config.BASE_URL)
        """
        self.base_url = base_url or Config.BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': Config.USER_AGENT
        })

    def fetch_chapter_list(self) -> Optional[List[Dict[str, any]]]:
        """
        Fetch the complete ordered list of chapters from the ToC page

        Returns:
            List of chapter dictionaries with:
            {
                'order_index': int,
                'chapter_number': str,
                'url': str,
                'is_interlude': bool
            }
            Returns None if scraping fails
        """
        try:
            logger.info(f"Fetching table of contents from {self.TOC_URL}")
            response = self.session.get(self.TOC_URL, timeout=30)

            if response.status_code != 200:
                logger.error(f"Failed to fetch ToC: HTTP {response.status_code}")
                return None

            soup = BeautifulSoup(response.content, 'lxml')

            # Extract chapter links
            chapters = self._extract_chapters(soup)

            if not chapters:
                logger.error("No chapters found in ToC")
                return None

            logger.info(f"Successfully extracted {len(chapters)} chapters from ToC")
            return chapters

        except requests.RequestException as e:
            logger.error(f"Network error fetching ToC: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching ToC: {e}")
            return None

    def _extract_chapters(self, soup: BeautifulSoup) -> List[Dict[str, any]]:
        """
        Extract chapter links from the ToC page

        The Wandering Inn ToC structure typically has:
        - Links to chapters in chronological order
        - Mix of regular chapters and interludes
        - Chapter URLs follow date pattern: /YYYY/MM/DD/chapter-slug/

        This method specifically looks for chapter links with date-based URLs.
        """
        import re

        chapters = []
        order_index = 1

        # Try to find the main content area
        content_selectors = [
            '.entry-content',
            '.chapter-list',
            'article',
            '.post-content',
            'main',
        ]

        content_elem = None
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                logger.debug(f"Found content with selector: {selector}")
                break

        if not content_elem:
            logger.warning("Could not find content container, searching entire page")
            content_elem = soup

        # Find all links
        links = content_elem.find_all('a', href=True)
        logger.info(f"Found {len(links)} total links in ToC")

        # Pattern for chapter URLs: /YYYY/MM/DD/something/
        # This matches the date-based URL structure used by Wandering Inn
        chapter_url_pattern = re.compile(r'/\d{4}/\d{2}/\d{2}/[^/]+/?$')

        seen_urls = set()  # Avoid duplicates

        for link in links:
            href = link['href']
            title = link.get_text(strip=True)

            # Skip empty links
            if not href or not title:
                continue

            # Normalize URL
            if not href.startswith('http'):
                href = urljoin(self.base_url, href)

            # Only include links from the same domain
            if not href.startswith(self.base_url):
                continue

            # Only include links that match the chapter URL pattern (date-based)
            # Extract the path from the URL for matching
            url_path = href.replace(self.base_url, '')
            if not chapter_url_pattern.search(url_path):
                continue

            # Skip duplicates
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Detect if this is an interlude
            is_interlude = self._is_interlude(title, href)

            chapter_data = {
                'order_index': order_index,
                'chapter_number': title,
                'url': href,
                'is_interlude': is_interlude
            }

            chapters.append(chapter_data)
            order_index += 1

            if order_index % 100 == 0:
                logger.debug(f"Processed {order_index} chapters...")

        return chapters

    def _is_interlude(self, title: str, url: str) -> bool:
        """
        Determine if a chapter is an interlude based on title or URL

        Args:
            title: Chapter title
            url: Chapter URL

        Returns:
            True if chapter is an interlude
        """
        interlude_keywords = [
            'interlude',
            'side story',
            'epilogue',
            'prologue',
            'afterword',
            'glossary',
        ]

        title_lower = title.lower()
        url_lower = url.lower()

        for keyword in interlude_keywords:
            if keyword in title_lower or keyword in url_lower:
                return True

        return False

    def save_chapter_list_to_file(self, chapters: List[Dict[str, any]], filepath: str) -> bool:
        """
        Save chapter list to a JSON file for later use

        Args:
            chapters: List of chapter dictionaries
            filepath: Path to save the JSON file

        Returns:
            True if successful, False otherwise
        """
        import json

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(chapters, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved {len(chapters)} chapters to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to save chapter list: {e}")
            return False

    def load_chapter_list_from_file(self, filepath: str) -> Optional[List[Dict[str, any]]]:
        """
        Load chapter list from a JSON file

        Args:
            filepath: Path to the JSON file

        Returns:
            List of chapter dictionaries or None if loading fails
        """
        import json

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                chapters = json.load(f)

            logger.info(f"Loaded {len(chapters)} chapters from {filepath}")
            return chapters
        except FileNotFoundError:
            logger.error(f"Chapter list file not found: {filepath}")
            return None
        except Exception as e:
            logger.error(f"Failed to load chapter list: {e}")
            return None

    def get_chapter_by_index(self, chapters: List[Dict[str, any]], order_index: int) -> Optional[Dict[str, any]]:
        """
        Get chapter data by order_index

        Args:
            chapters: List of chapter dictionaries
            order_index: Order index to retrieve

        Returns:
            Chapter dictionary or None if not found
        """
        for chapter in chapters:
            if chapter['order_index'] == order_index:
                return chapter

        return None

    def display_chapter_summary(self, chapters: List[Dict[str, any]]) -> None:
        """
        Display a summary of the chapter list

        Args:
            chapters: List of chapter dictionaries
        """
        total = len(chapters)
        interludes = sum(1 for ch in chapters if ch.get('is_interlude', False))
        regular = total - interludes

        logger.info("=" * 60)
        logger.info("Chapter List Summary")
        logger.info("=" * 60)
        logger.info(f"Total chapters: {total}")
        logger.info(f"Regular chapters: {regular}")
        logger.info(f"Interludes: {interludes}")
        logger.info("=" * 60)

        # Show first few chapters
        logger.info("First 5 chapters:")
        for chapter in chapters[:5]:
            marker = " [Interlude]" if chapter.get('is_interlude') else ""
            logger.info(f"  [{chapter['order_index']}] {chapter['chapter_number']}{marker}")
            logger.info(f"     URL: {chapter['url']}")

        # Show last few chapters
        if total > 5:
            logger.info("\nLast 5 chapters:")
            for chapter in chapters[-5:]:
                marker = " [Interlude]" if chapter.get('is_interlude') else ""
                logger.info(f"  [{chapter['order_index']}] {chapter['chapter_number']}{marker}")
                logger.info(f"     URL: {chapter['url']}")

        logger.info("=" * 60)

    def close(self):
        """Close the session"""
        self.session.close()
        logger.debug("ToC scraper session closed")
