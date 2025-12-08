"""Extract characters from chapter text using AI"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .client import AIClient, AIResponse, AIError
from .cost_tracker import CostTracker
from .prompts import CHARACTER_EXTRACTION_SYSTEM
from .wiki_reference import get_wiki_cache
from ..db import get_connection, return_connection

logger = logging.getLogger(__name__)


@dataclass
class ExtractedCharacter:
    """A character mentioned in text"""
    name: str
    confidence: float
    alias_used: Optional[str] = None
    is_new: bool = False
    species: Optional[str] = None
    description: Optional[str] = None


class CharacterExtractor:
    """Extract and manage characters from chapter text"""

    # Maximum chapter text length to send to AI (in characters)
    MAX_TEXT_LENGTH = 100000  # ~25k tokens

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        cost_tracker: Optional[CostTracker] = None
    ):
        """
        Initialize the character extractor.

        Args:
            ai_client: AIClient instance (created if not provided)
            cost_tracker: CostTracker instance (created if not provided)
        """
        self.ai_client = ai_client or AIClient()
        self.cost_tracker = cost_tracker or CostTracker()

        # Cache of known characters {name: {aliases: [], id: int}}
        self._character_cache: Dict[str, Dict] = {}
        self._cache_loaded = False

    def _load_character_cache(self):
        """Load existing characters from database into cache"""
        if self._cache_loaded:
            return

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, name, aliases, knowledge
                FROM characters
                """
            )

            for row in cursor.fetchall():
                char_id, name, aliases, knowledge = row
                self._character_cache[name.lower()] = {
                    'id': char_id,
                    'name': name,
                    'aliases': aliases or [],
                    'knowledge': knowledge or {}
                }

                # Also index by aliases
                if aliases:
                    for alias in aliases:
                        self._character_cache[alias.lower()] = {
                            'id': char_id,
                            'name': name,
                            'aliases': aliases,
                            'knowledge': knowledge or {}
                        }

            cursor.close()
            self._cache_loaded = True
            logger.info(f"Loaded {len(set(c['id'] for c in self._character_cache.values()))} characters into cache")

        except Exception as e:
            logger.error(f"Failed to load character cache: {e}")
        finally:
            if conn:
                return_connection(conn)

    def extract_characters(
        self,
        chapter_text: str,
        chapter_id: int,
        chapter_number: str
    ) -> Tuple[List[ExtractedCharacter], AIResponse]:
        """
        Extract characters mentioned in a chapter.

        Args:
            chapter_text: Full chapter text
            chapter_id: Database ID of the chapter
            chapter_number: Chapter number for display

        Returns:
            Tuple of (list of extracted characters, AI response)
        """
        self._load_character_cache()

        # Truncate text if too long
        text_to_analyze = chapter_text
        if len(chapter_text) > self.MAX_TEXT_LENGTH:
            logger.warning(
                f"Chapter {chapter_number} text truncated from {len(chapter_text)} "
                f"to {self.MAX_TEXT_LENGTH} characters"
            )
            text_to_analyze = chapter_text[:self.MAX_TEXT_LENGTH]

        # Build list of known characters for the prompt
        # First, get wiki characters (canonical source)
        wiki_cache = get_wiki_cache()
        wiki_characters = wiki_cache.get_all_character_names()

        # Also include characters from our database (may have characters not yet in wiki)
        db_characters = list(set(c['name'] for c in self._character_cache.values()))
        known_aliases = {
            c['name']: c['aliases']
            for c in self._character_cache.values()
            if c['aliases']
        }

        # Combine, preferring wiki names
        all_known_characters = list(set(wiki_characters + db_characters))

        # Build wiki character context with species info
        wiki_context = wiki_cache.get_character_context_for_prompt(wiki_characters[:100])

        # Build user message
        user_message = f"""Analyze this chapter and identify all characters mentioned.

Chapter Number: {chapter_number}

=== WIKI CHARACTERS (authoritative source - use these exact names) ===
The wiki has {len(wiki_characters)} known characters. Here are some with details:
{wiki_context}

Full list of known character names:
{json.dumps(all_known_characters[:300], indent=2)}

Known Aliases (alternative names for characters):
{json.dumps(known_aliases, indent=2) if len(known_aliases) < 50 else "(many aliases, use best judgment)"}

=== CHAPTER TEXT ===
{text_to_analyze}

=== INSTRUCTIONS ===
Identify all characters mentioned in this chapter.
- Match to wiki characters whenever possible (use exact wiki name)
- Only mark as "new" if character is NOT in the wiki or database lists
- For new characters, provide species and description"""

        # Call AI
        try:
            response = self.ai_client.send_message(
                system_prompt=CHARACTER_EXTRACTION_SYSTEM,
                user_message=user_message,
                max_tokens=4096,
                expect_json=True
            )

            # Log the request
            self.cost_tracker.log_request(
                response=response,
                chapter_id=chapter_id,
                processing_type='character_extraction'
            )

            # Parse response
            characters = self._parse_extraction_response(response)

            logger.info(
                f"Chapter {chapter_number}: Found {len(characters)} characters "
                f"({sum(1 for c in characters if c.is_new)} new)"
            )

            return characters, response

        except AIError as e:
            logger.error(f"AI error extracting characters from chapter {chapter_number}: {e}")
            raise

    def _parse_extraction_response(
        self,
        response: AIResponse
    ) -> List[ExtractedCharacter]:
        """Parse the AI response into ExtractedCharacter objects"""
        characters = []

        if not response.parsed_json:
            logger.warning("No JSON in extraction response")
            return characters

        data = response.parsed_json

        # Process mentioned characters
        for char in data.get('characters_mentioned', []):
            characters.append(ExtractedCharacter(
                name=char.get('name', 'Unknown'),
                confidence=char.get('confidence', 0.5),
                alias_used=char.get('alias_used'),
                is_new=False
            ))

        # Process new characters
        for char in data.get('new_characters', []):
            characters.append(ExtractedCharacter(
                name=char.get('name', 'Unknown'),
                confidence=0.8,  # New characters have moderate confidence
                is_new=True,
                species=char.get('species'),
                description=char.get('description')
            ))

        return characters

    def save_new_characters(
        self,
        characters: List[ExtractedCharacter],
        chapter_id: int
    ) -> int:
        """
        Save new characters to the database.

        Args:
            characters: List of extracted characters
            chapter_id: Chapter where they first appeared

        Returns:
            Number of new characters created
        """
        new_count = 0
        conn = None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            for char in characters:
                if not char.is_new:
                    continue

                # Check if character already exists (case-insensitive)
                if char.name.lower() in self._character_cache:
                    continue

                # Build initial knowledge
                knowledge = {}
                if char.species:
                    knowledge['species'] = char.species
                if char.description:
                    knowledge['summary'] = char.description

                # Insert new character
                cursor.execute(
                    """
                    INSERT INTO characters (name, first_appearance_chapter_id, knowledge)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (name) DO NOTHING
                    RETURNING id
                    """,
                    (char.name, chapter_id, json.dumps(knowledge) if knowledge else '{}')
                )

                result = cursor.fetchone()
                if result:
                    new_count += 1
                    # Update cache
                    self._character_cache[char.name.lower()] = {
                        'id': result[0],
                        'name': char.name,
                        'aliases': [],
                        'knowledge': knowledge
                    }
                    logger.info(f"Created new character: {char.name}")

            conn.commit()
            cursor.close()

            return new_count

        except Exception as e:
            logger.error(f"Failed to save new characters: {e}")
            if conn:
                conn.rollback()
            return 0
        finally:
            if conn:
                return_connection(conn)

    def update_chapter_state(
        self,
        chapter_id: int,
        characters_found: int,
        new_characters: int
    ):
        """Update the AI processing state for a chapter"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO ai_chapter_state (
                    chapter_id, characters_extracted, characters_extracted_at,
                    characters_found, new_characters_created
                )
                VALUES (%s, TRUE, CURRENT_TIMESTAMP, %s, %s)
                ON CONFLICT (chapter_id) DO UPDATE
                SET characters_extracted = TRUE,
                    characters_extracted_at = CURRENT_TIMESTAMP,
                    characters_found = EXCLUDED.characters_found,
                    new_characters_created = EXCLUDED.new_characters_created
                """,
                (chapter_id, characters_found, new_characters)
            )

            conn.commit()
            cursor.close()

        except Exception as e:
            logger.error(f"Failed to update chapter state: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                return_connection(conn)

    def get_character_id(self, name: str) -> Optional[int]:
        """Get character ID by name or alias"""
        self._load_character_cache()

        cached = self._character_cache.get(name.lower())
        if cached:
            return cached['id']
        return None

    def get_character_context(self, name: str) -> Optional[Dict[str, Any]]:
        """Get character context for event attribution"""
        self._load_character_cache()

        cached = self._character_cache.get(name.lower())
        if cached:
            return {
                'id': cached['id'],
                'name': cached['name'],
                'knowledge': cached['knowledge']
            }
        return None
