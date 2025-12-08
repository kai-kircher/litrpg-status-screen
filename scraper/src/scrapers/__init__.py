"""Web scraping module"""

from .chapter_scraper import ChapterScraper
from .toc_scraper import TocScraper
from .wiki_scraper import (
    WikiScraper,
    WikiCharacterScraper,
    WikiSkillScraper,
    WikiSpellScraper,
    WikiClassScraper,
)

__all__ = [
    "ChapterScraper",
    "TocScraper",
    "WikiScraper",
    "WikiCharacterScraper",
    "WikiSkillScraper",
    "WikiSpellScraper",
    "WikiClassScraper",
]
