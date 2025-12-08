"""Wiki scraper for The Wandering Inn Wiki"""

import requests
from bs4 import BeautifulSoup
import logging
import time
import re
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs
from ..config import Config

logger = logging.getLogger(__name__)


class WikiScraper:
    """Base scraper for The Wandering Inn Wiki"""

    WIKI_BASE_URL = "https://wiki.wanderinginn.com"

    def __init__(self, delay: Optional[float] = None):
        """
        Initialize the wiki scraper

        Args:
            delay: Delay between requests in seconds (defaults to Config.WIKI_REQUEST_DELAY)
        """
        # Use wiki-specific delay (1s) instead of main site delay (10s)
        # Wiki has no crawl-delay in robots.txt
        self.delay = delay if delay is not None else Config.WIKI_REQUEST_DELAY
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': Config.USER_AGENT
        })
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce delay between requests"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            sleep_time = self.delay - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """
        Fetch and parse a wiki page

        Args:
            url: Full URL to fetch

        Returns:
            BeautifulSoup object or None if fetch failed
        """
        self._rate_limit()

        try:
            logger.debug(f"Fetching: {url}")
            response = self.session.get(url, timeout=30)

            if response.status_code != 200:
                logger.error(f"Failed to fetch {url}: HTTP {response.status_code}")
                return None

            return BeautifulSoup(response.content, 'lxml')

        except requests.RequestException as e:
            logger.error(f"Network error fetching {url}: {e}")
            return None

    def close(self):
        """Close the session"""
        self.session.close()
        logger.debug("Wiki scraper session closed")


class WikiCharacterScraper(WikiScraper):
    """Scraper for character list from wiki category pages"""

    CATEGORY_URL = "https://wiki.wanderinginn.com/index.php?title=Category:Characters"

    def fetch_all_characters(self) -> List[Dict[str, str]]:
        """
        Fetch all characters from the wiki category pages

        Returns:
            List of character dictionaries with 'name' and 'wiki_url' keys
        """
        characters = []
        next_url = self.CATEGORY_URL
        page_num = 1

        while next_url:
            logger.info(f"Fetching character page {page_num}...")
            soup = self.fetch_page(next_url)

            if not soup:
                logger.error(f"Failed to fetch page {page_num}")
                break

            # Extract characters from this page
            page_characters = self._extract_characters_from_page(soup)
            characters.extend(page_characters)
            logger.info(f"  Found {len(page_characters)} characters on page {page_num}")

            # Find next page link
            next_url = self._get_next_page_url(soup)
            page_num += 1

        logger.info(f"Total characters found: {len(characters)}")
        return characters

    def _extract_characters_from_page(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract character names and URLs from a category page"""
        characters = []

        # Find the category members section (mw-pages)
        mw_pages = soup.find('div', id='mw-pages')
        if not mw_pages:
            logger.warning("Could not find mw-pages div")
            return characters

        # Find all links in the category listing
        # Characters are in div.mw-category-group sections
        for link in mw_pages.find_all('a'):
            href = link.get('href', '')
            name = link.get_text(strip=True)

            # Skip navigation links and empty names
            if not name or not href:
                continue

            # Skip category navigation links
            if 'Category:' in href or 'pagefrom=' in href or 'pageuntil=' in href:
                continue

            # Build full URL
            if href.startswith('/'):
                full_url = urljoin(self.WIKI_BASE_URL, href)
            else:
                full_url = href

            # Only include wiki pages
            if self.WIKI_BASE_URL in full_url or href.startswith('/wiki/'):
                characters.append({
                    'name': name,
                    'wiki_url': full_url,
                    'wiki_page_title': href.replace('/wiki/', '').replace('_', ' ')
                })

        return characters

    def _get_next_page_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Find the 'next page' link if it exists"""
        # Look for "(next page)" link
        mw_pages = soup.find('div', id='mw-pages')
        if not mw_pages:
            return None

        for link in mw_pages.find_all('a'):
            text = link.get_text(strip=True)
            if text == 'next page':
                href = link.get('href', '')
                if href:
                    return urljoin(self.WIKI_BASE_URL, href)

        return None

    def fetch_character_details(self, wiki_url: str) -> Optional[Dict]:
        """
        Fetch detailed information from a character's wiki page

        Args:
            wiki_url: URL to the character's wiki page

        Returns:
            Dictionary with character details or None if fetch failed
        """
        soup = self.fetch_page(wiki_url)
        if not soup:
            return None

        details = {
            'aliases': [],
            'species': None,
            'status': None,
            'affiliation': [],
            'first_appearance': None,
            'infobox_data': {}
        }

        # Find infobox (usually a table with class 'infobox')
        infobox = soup.find('table', class_='infobox')
        if infobox:
            details = self._parse_infobox(infobox)

        return details

    def _parse_infobox(self, infobox: BeautifulSoup) -> Dict:
        """Parse character infobox for key information"""
        details = {
            'aliases': [],
            'species': None,
            'status': None,
            'affiliation': [],
            'first_appearance': None,
            'infobox_data': {}
        }

        rows = infobox.find_all('tr')
        for row in rows:
            header = row.find('th')
            data = row.find('td')

            if not header or not data:
                continue

            key = header.get_text(strip=True).lower()
            value = data.get_text(separator=', ', strip=True)

            # Store raw in infobox_data
            details['infobox_data'][key] = value

            # Map to specific fields
            if 'alias' in key or 'title' in key or 'nickname' in key:
                # Split on commas and clean up
                aliases = [a.strip() for a in value.split(',') if a.strip()]
                details['aliases'].extend(aliases)
            elif key == 'species':
                details['species'] = value
            elif key == 'status':
                details['status'] = value
            elif 'affiliation' in key or 'allegiance' in key:
                affiliations = [a.strip() for a in value.split(',') if a.strip()]
                details['affiliation'].extend(affiliations)
            elif 'first appearance' in key:
                details['first_appearance'] = value

        return details


class WikiSkillScraper(WikiScraper):
    """Scraper for skills from the wiki Skills pages"""

    SKILLS_ALPHA_URL = "https://wiki.wanderinginn.com/Skills_Effect/{letter}"

    # Local data files for special skills (manually maintained)
    FAKE_SKILLS_FILE = "data/fake_skills.txt"
    COLORED_SKILLS_FILE = "data/colored_skills.txt"

    def fetch_all_skills(self) -> List[Dict[str, any]]:
        """
        Fetch all skills from the wiki using alphabetical subpages.

        Skills are loaded from:
        1. Local text files for special skills (colored, fake) - manually maintained
        2. Alphabetical subpages (/Skills_Effect/A through Z) for all skills

        Returns:
            List of skill dictionaries
        """
        skills = []

        # First, load special skills from local files
        logger.info("Loading special skills from local files...")
        special_skills = self._load_special_skills_from_files()
        skills.extend(special_skills)
        logger.info(f"  Loaded {len(special_skills)} special skills (colored/fake)")

        # Then fetch each alphabetical subpage
        letters = ['Numbers'] + list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        for letter in letters:
            logger.info(f"Fetching skills starting with {letter}...")
            url = self.SKILLS_ALPHA_URL.format(letter=letter)
            soup = self.fetch_page(url)

            if soup:
                letter_skills = self._parse_skill_tables_from_page(soup)
                skills.extend(letter_skills)
                logger.info(f"  Found {len(letter_skills)} skills for {letter}")

        # Deduplicate by normalized name, preferring special skills (they have metadata)
        seen = {}
        for skill in skills:
            norm_name = skill['normalized_name']
            if norm_name not in seen:
                seen[norm_name] = skill
            elif skill.get('is_fake') or skill.get('skill_type'):
                # Prefer the version with special metadata
                seen[norm_name] = skill

        unique_skills = list(seen.values())
        logger.info(f"Total unique skills found: {len(unique_skills)}")
        return unique_skills

    def _load_special_skills_from_files(self) -> List[Dict[str, any]]:
        """Load colored and fake skills from local text files"""
        import os
        skills = []

        # Get the scraper module directory
        module_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        # Load fake skills
        fake_path = os.path.join(module_dir, self.FAKE_SKILLS_FILE)
        if os.path.exists(fake_path):
            fake_names = self._load_skills_from_file(fake_path)
            for name in fake_names:
                skills.append({
                    'name': f"[{name}]",
                    'normalized_name': self._normalize_ability_name(name),
                    'effect': None,
                    'reference_chapters': None,
                    'is_fake': True,
                    'is_conditional': False,
                    'skill_type': 'fake'
                })
            logger.info(f"  Loaded {len(fake_names)} fake skills from {fake_path}")
        else:
            logger.warning(f"Fake skills file not found: {fake_path}")

        # Load colored skills
        colored_path = os.path.join(module_dir, self.COLORED_SKILLS_FILE)
        if os.path.exists(colored_path):
            colored_names = self._load_skills_from_file(colored_path)
            for name in colored_names:
                skills.append({
                    'name': f"[{name}]",
                    'normalized_name': self._normalize_ability_name(name),
                    'effect': None,
                    'reference_chapters': None,
                    'is_fake': False,
                    'is_conditional': False,
                    'skill_type': 'colored'
                })
            logger.info(f"  Loaded {len(colored_names)} colored skills from {colored_path}")
        else:
            logger.warning(f"Colored skills file not found: {colored_path}")

        return skills

    def _load_skills_from_file(self, filepath: str) -> List[str]:
        """Load skill names from a text file (one per line, # comments)"""
        names = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        names.append(line)
        except Exception as e:
            logger.error(f"Error reading {filepath}: {e}")
        return names

    def _parse_skill_tables_from_page(self, soup: BeautifulSoup) -> List[Dict[str, any]]:
        """Parse all skill tables from an alphabetical subpage"""
        skills = []

        tables = soup.find_all('table', class_='wikitable')
        for table in tables:
            table_skills = self._parse_skill_table(table)
            skills.extend(table_skills)

        return skills

    def _parse_skill_table(self, table: BeautifulSoup) -> List[Dict[str, any]]:
        """Parse a skill table"""
        skills = []

        rows = table.find_all('tr')
        if not rows:
            return skills

        # Check header row to determine column structure
        header_row = rows[0]
        headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]

        # Find column indices
        name_idx = None
        effect_idx = None
        ref_idx = None

        for i, h in enumerate(headers):
            if 'name' in h or 'skill' in h:
                name_idx = i
            elif 'effect' in h or 'description' in h:
                effect_idx = i
            elif 'reference' in h or 'chapter' in h:
                ref_idx = i

        # If no clear headers, assume standard format: Name, Effect, Reference
        if name_idx is None:
            name_idx = 0
        if effect_idx is None:
            effect_idx = 1 if len(headers) > 1 else None
        if ref_idx is None:
            ref_idx = 2 if len(headers) > 2 else None

        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) <= name_idx:
                continue

            name = cells[name_idx].get_text(strip=True)
            if not name:
                continue

            skill = {
                'name': name,
                'normalized_name': self._normalize_ability_name(name),
                'effect': None,
                'reference_chapters': None,
                'is_fake': False,
                'is_conditional': False,
                'skill_type': None
            }

            if effect_idx is not None and len(cells) > effect_idx:
                skill['effect'] = cells[effect_idx].get_text(strip=True)

            if ref_idx is not None and len(cells) > ref_idx:
                skill['reference_chapters'] = cells[ref_idx].get_text(strip=True)

            # Detect conditional skills
            if skill['effect']:
                effect_lower = skill['effect'].lower()
                if any(word in effect_lower for word in ['daily', 'weekly', 'monthly', 'once per']):
                    skill['is_conditional'] = True

            skills.append(skill)

        return skills

    def _normalize_ability_name(self, name: str) -> str:
        """Normalize ability name for matching"""
        # Remove brackets
        normalized = re.sub(r'[\[\]]', '', name)
        # Lowercase
        normalized = normalized.lower()
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        return normalized


class WikiSpellScraper(WikiScraper):
    """Scraper for spells from the wiki Spells pages"""

    SPELLS_MAIN_URL = "https://wiki.wanderinginn.com/Spells"
    SPELLS_ALPHA_URL = "https://wiki.wanderinginn.com/Spells/{letter}"

    def fetch_all_spells(self) -> List[Dict[str, any]]:
        """
        Fetch all spells from the wiki using alphabetical subpages.

        The main Spells page is very large, so we scrape:
        1. Main page for tiered spells with tier info
        2. Alphabetical subpages (/Spells/A through Z) for complete listing

        Returns:
            List of spell dictionaries
        """
        spells = []

        # First, fetch tiered spells from main page (to get tier info)
        logger.info("Fetching tiered spells from main Spells page...")
        tiered_spells = self._fetch_tiered_spells()
        logger.info(f"  Found {len(tiered_spells)} tiered spells")

        # Build a map of spell name -> tier for enrichment
        tier_map = {}
        for spell in tiered_spells:
            if spell.get('tier') is not None:
                tier_map[spell['normalized_name']] = spell['tier']

        # Then fetch each alphabetical subpage
        letters = ['Numbers'] + list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        for letter in letters:
            logger.info(f"Fetching spells starting with {letter}...")
            url = self.SPELLS_ALPHA_URL.format(letter=letter)
            soup = self.fetch_page(url)

            if soup:
                letter_spells = self._parse_spell_tables_from_page(soup)
                # Enrich with tier info from main page
                for spell in letter_spells:
                    if spell['normalized_name'] in tier_map:
                        spell['tier'] = tier_map[spell['normalized_name']]
                spells.extend(letter_spells)
                logger.info(f"  Found {len(letter_spells)} spells for {letter}")

        # Deduplicate by normalized name
        seen = set()
        unique_spells = []
        for spell in spells:
            if spell['normalized_name'] not in seen:
                seen.add(spell['normalized_name'])
                unique_spells.append(spell)

        logger.info(f"Total unique spells found: {len(unique_spells)}")
        return unique_spells

    def _fetch_tiered_spells(self) -> List[Dict[str, any]]:
        """Fetch tiered spells from main page to get tier information"""
        soup = self.fetch_page(self.SPELLS_MAIN_URL)
        if not soup:
            return []

        spells = []
        current_tier = None

        for elem in soup.find_all(['h2', 'h3', 'table']):
            if elem.name in ['h2', 'h3']:
                section_text = elem.get_text(strip=True).lower()
                # Check for tier number
                tier_match = re.search(r'tier\s*(\d+)', section_text)
                if tier_match:
                    current_tier = int(tier_match.group(1))
                elif 'untiered' in section_text:
                    current_tier = None

            elif elem.name == 'table' and 'wikitable' in elem.get('class', []) and current_tier is not None:
                table_spells = self._parse_spell_table(elem, 'tiered', current_tier)
                spells.extend(table_spells)

        return spells

    def _parse_spell_tables_from_page(self, soup: BeautifulSoup) -> List[Dict[str, any]]:
        """Parse all spell tables from an alphabetical subpage"""
        spells = []

        tables = soup.find_all('table', class_='wikitable')
        for table in tables:
            table_spells = self._parse_spell_table(table, None, None)
            spells.extend(table_spells)

        return spells

    def _parse_spell_table(self, table: BeautifulSoup, section: Optional[str], default_tier: Optional[int]) -> List[Dict[str, any]]:
        """Parse a spell table"""
        spells = []

        rows = table.find_all('tr')
        if not rows:
            return spells

        # Check header row
        header_row = rows[0]
        headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]

        # Find column indices
        name_idx = 0
        tier_idx = None
        effect_idx = None
        ref_idx = None

        for i, h in enumerate(headers):
            if 'spell' in h or 'name' in h:
                name_idx = i
            elif 'tier' in h:
                tier_idx = i
            elif 'effect' in h or 'description' in h:
                effect_idx = i
            elif 'reference' in h or 'chapter' in h:
                ref_idx = i

        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) <= name_idx:
                continue

            name = cells[name_idx].get_text(strip=True)
            if not name:
                continue

            spell = {
                'name': name,
                'normalized_name': self._normalize_spell_name(name),
                'tier': default_tier,
                'effect': None,
                'reference_chapters': None,
                'is_tiered': section != 'untiered'
            }

            if tier_idx is not None and len(cells) > tier_idx:
                tier_text = cells[tier_idx].get_text(strip=True)
                try:
                    spell['tier'] = int(tier_text)
                except ValueError:
                    pass  # Keep default tier

            if effect_idx is not None and len(cells) > effect_idx:
                spell['effect'] = cells[effect_idx].get_text(strip=True)

            if ref_idx is not None and len(cells) > ref_idx:
                spell['reference_chapters'] = cells[ref_idx].get_text(strip=True)

            spells.append(spell)

        return spells

    def _normalize_spell_name(self, name: str) -> str:
        """Normalize spell name for matching"""
        # Remove brackets
        normalized = re.sub(r'[\[\]]', '', name)
        # Lowercase
        normalized = normalized.lower()
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        return normalized


class WikiClassScraper(WikiScraper):
    """Scraper for classes from the wiki List of Classes pages"""

    CLASSES_ALPHA_URL = "https://wiki.wanderinginn.com/List_of_Classes/{letter}"

    # Local data file for fake classes (manually maintained)
    FAKE_CLASSES_FILE = "data/fake_classes.txt"

    def fetch_all_classes(self) -> List[Dict[str, any]]:
        """
        Fetch all classes from the wiki

        Classes are loaded from:
        1. Local text file for fake classes - manually maintained
        2. Alphabetical subpages (/List_of_Classes/A through Z) for all classes

        Returns:
            List of class dictionaries
        """
        classes = []

        # First, load fake classes from local file
        logger.info("Loading fake classes from local file...")
        fake_classes = self._load_fake_classes_from_file()
        classes.extend(fake_classes)
        logger.info(f"  Loaded {len(fake_classes)} fake classes")

        # Then fetch each alphabetical page
        letters = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        for letter in letters:
            logger.info(f"Fetching classes starting with {letter}...")
            url = self.CLASSES_ALPHA_URL.format(letter=letter)
            soup = self.fetch_page(url)

            if soup:
                letter_classes = self._parse_class_table(soup, is_fake=False)
                classes.extend(letter_classes)
                logger.info(f"  Found {len(letter_classes)} classes for {letter}")

        # Deduplicate by normalized name, preferring fake classes (they have metadata)
        seen = {}
        for cls in classes:
            norm_name = cls['normalized_name']
            if norm_name not in seen:
                seen[norm_name] = cls
            elif cls.get('is_fake'):
                # Prefer the version marked as fake
                seen[norm_name] = cls

        unique_classes = list(seen.values())
        logger.info(f"Total unique classes found: {len(unique_classes)}")
        return unique_classes

    def _load_fake_classes_from_file(self) -> List[Dict[str, any]]:
        """Load fake classes from local text file"""
        import os
        classes = []

        # Get the scraper module directory
        module_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        fake_path = os.path.join(module_dir, self.FAKE_CLASSES_FILE)
        if os.path.exists(fake_path):
            fake_names = self._load_classes_from_file(fake_path)
            for name in fake_names:
                classes.append({
                    'name': f"[{name}]",
                    'normalized_name': self._normalize_class_name(name),
                    'description': None,
                    'known_characters': None,
                    'reference_chapters': None,
                    'is_fake': True,
                    'class_type': 'fake'
                })
            logger.info(f"  Loaded {len(fake_names)} fake classes from {fake_path}")
        else:
            logger.warning(f"Fake classes file not found: {fake_path}")

        return classes

    def _load_classes_from_file(self, filepath: str) -> List[str]:
        """Load class names from a text file (one per line, # comments)"""
        names = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        names.append(line)
        except Exception as e:
            logger.error(f"Error reading {filepath}: {e}")
        return names

    def _parse_class_table(self, soup: BeautifulSoup, is_fake: bool = False) -> List[Dict[str, any]]:
        """Parse all class tables on a page"""
        classes = []

        tables = soup.find_all('table', class_='wikitable')
        for table in tables:
            table_classes = self._parse_class_table_from_element(table, is_fake)
            classes.extend(table_classes)

        return classes

    def _parse_class_table_from_element(self, table: BeautifulSoup, is_fake: bool) -> List[Dict[str, any]]:
        """Parse a single class table"""
        classes = []

        rows = table.find_all('tr')
        if not rows:
            return classes

        # Check header row
        header_row = rows[0]
        headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]

        # Find column indices
        name_idx = 0
        chars_idx = None
        info_idx = None
        ref_idx = None

        for i, h in enumerate(headers):
            if 'name' in h or 'class' in h:
                name_idx = i
            elif 'character' in h or 'known' in h:
                chars_idx = i
            elif 'info' in h or 'description' in h:
                info_idx = i
            elif 'reference' in h or 'chapter' in h:
                ref_idx = i

        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) <= name_idx:
                continue

            name = cells[name_idx].get_text(strip=True)
            if not name:
                continue

            cls = {
                'name': name,
                'normalized_name': self._normalize_class_name(name),
                'description': None,
                'known_characters': None,
                'reference_chapters': None,
                'is_fake': is_fake,
                'class_type': None
            }

            if chars_idx is not None and len(cells) > chars_idx:
                cls['known_characters'] = cells[chars_idx].get_text(strip=True)

            if info_idx is not None and len(cells) > info_idx:
                cls['description'] = cells[info_idx].get_text(strip=True)

            if ref_idx is not None and len(cells) > ref_idx:
                cls['reference_chapters'] = cells[ref_idx].get_text(strip=True)

            classes.append(cls)

        return classes

    def _normalize_class_name(self, name: str) -> str:
        """Normalize class name for matching"""
        # Remove brackets
        normalized = re.sub(r'[\[\]]', '', name)
        # Lowercase
        normalized = normalized.lower()
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        return normalized
