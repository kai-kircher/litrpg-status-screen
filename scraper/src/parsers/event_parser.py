"""Parser for extracting potential progression events from chapter text"""

import logging
import re
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Words that indicate a bracket is likely an actual progression event
# Used to distinguish "[Warrior Level 5!]" from just "[Warrior]"
EVENT_INDICATOR_WORDS: Set[str] = {
    # Acquisition/loss verbs
    'obtained', 'gained', 'earned', 'lost', 'removed',
    # Level-related
    'level', 'levels',
    # Type prefixes (Skill - X, Spell - X, etc.)
    'skill', 'spell', 'condition', 'class', 'classes',
    # Change/upgrade indicators
    'change', 'changed', 'consolidated', 'merged', 'upgraded', 'evolved',
    # Completion indicators
    'complete', 'completed', 'restored', 'unlocked',
    # Cancellation
    'cancelled', 'canceled',
}


@dataclass
class BracketEvent:
    """Represents a single bracket occurrence found in text (unclassified)"""
    raw_text: str  # Text from [ to ] (or end of reasonable search)
    surrounding_text: str  # Context around the bracket
    position: int  # Character position in text where [ was found
    event_index: int  # Index of this event in the chapter (0-based)


class EventParser:
    """Parser for extracting likely progression events from bracket occurrences in text"""

    # Context window size (characters before and after the bracket)
    CONTEXT_BEFORE = 150
    CONTEXT_AFTER = 150

    # Maximum length to search for closing bracket
    MAX_BRACKET_LENGTH = 300

    def __init__(self):
        """Initialize the parser"""
        pass

    def _is_likely_event(self, bracket_text: str) -> bool:
        """
        Determine if a bracket occurrence is likely an actual progression event
        vs. a casual mention of a class/skill/spell name.

        Filtering rules:
        - Single-word brackets are skipped (e.g., [Warrior], [Fireball])
        - Two-word brackets are skipped UNLESS one word is an event indicator
        - Three+ word brackets are kept (likely real events)

        Args:
            bracket_text: The text including brackets, e.g., "[Warrior Level 5!]"

        Returns:
            True if this looks like a real event, False if it's likely just a mention
        """
        # Extract content between brackets
        if not bracket_text.startswith('['):
            return False

        # Find the closing bracket
        close_pos = bracket_text.find(']')
        if close_pos == -1:
            # Unclosed bracket - might be interesting, keep it for review
            return True

        content = bracket_text[1:close_pos].strip()
        if not content:
            return False

        # Tokenize: split on whitespace and punctuation, keep only words
        words = re.findall(r'[a-zA-Z]+', content.lower())

        if len(words) == 0:
            # No actual words (e.g., "[???]" or "[—]")
            return False

        if len(words) == 1:
            # Single word - almost certainly just a class/skill mention
            # e.g., [Warrior], [Fireball], [Mage]
            return False

        if len(words) == 2:
            # Two words - only keep if one is an event indicator
            # e.g., "[Power Strike]" -> skip, "[Warrior obtained!]" -> keep
            for word in words:
                if word in EVENT_INDICATOR_WORDS:
                    return True
            return False

        # Three or more words - likely a real event
        # e.g., "[Skill - Power Strike obtained!]", "[Warrior Level 5!]"
        return True

    def parse_text(self, text: str) -> List[BracketEvent]:
        """
        Parse text and extract bracket occurrences that are likely progression events.

        Filters out casual mentions of classes/skills/spells (single-word or
        two-word brackets without event indicators).

        Args:
            text: Chapter text to parse

        Returns:
            List of BracketEvent objects for likely events
        """
        events = []

        # Handle empty or malformed input gracefully
        if not text or not isinstance(text, str):
            logger.warning("Empty or invalid text provided to parser")
            return events

        # Find all '[' occurrences
        position = 0
        event_index = 0
        total_brackets = 0
        skipped_brackets = 0

        while position < len(text):
            # Find next '['
            bracket_start = text.find('[', position)

            if bracket_start == -1:
                # No more brackets found
                break

            total_brackets += 1

            # Extract the bracket content
            raw_text = self._extract_bracket_text(text, bracket_start)

            # Filter out non-events (casual mentions)
            if not self._is_likely_event(raw_text):
                skipped_brackets += 1
                position = bracket_start + 1
                continue

            # Extract surrounding context
            surrounding_text = self._extract_surrounding_text(text, bracket_start)

            # Create event
            event = BracketEvent(
                raw_text=raw_text,
                surrounding_text=surrounding_text,
                position=bracket_start,
                event_index=event_index
            )
            events.append(event)

            # Move to next position
            position = bracket_start + 1
            event_index += 1

        logger.info(f"Found {len(events)} likely events out of {total_brackets} brackets (skipped {skipped_brackets} mentions)")
        return events

    def _extract_bracket_text(self, text: str, bracket_start: int) -> str:
        """
        Extract text from opening bracket to closing bracket (or reasonable cutoff)

        Args:
            text: Full text
            bracket_start: Position of '['

        Returns:
            The bracketed text including brackets
        """
        # Look for closing bracket within reasonable distance
        search_end = min(len(text), bracket_start + self.MAX_BRACKET_LENGTH)
        bracket_end = text.find(']', bracket_start, search_end)

        if bracket_end != -1:
            # Found closing bracket
            return text[bracket_start:bracket_end + 1]
        else:
            # No closing bracket found within range, take up to max length or newline
            end_pos = bracket_start + self.MAX_BRACKET_LENGTH
            newline_pos = text.find('\n', bracket_start, search_end)
            if newline_pos != -1:
                end_pos = min(end_pos, newline_pos)

            return text[bracket_start:end_pos]

    def _extract_surrounding_text(self, text: str, bracket_start: int) -> str:
        """
        Extract surrounding context for a bracket

        Args:
            text: Full text
            bracket_start: Position of '['

        Returns:
            Surrounding text with context before and after
        """
        # Get context before
        context_start = max(0, bracket_start - self.CONTEXT_BEFORE)
        context_end = min(len(text), bracket_start + self.MAX_BRACKET_LENGTH + self.CONTEXT_AFTER)

        surrounding = text[context_start:context_end]

        # Clean up (normalize whitespace but preserve structure)
        surrounding = ' '.join(surrounding.split())

        # Add ellipsis if truncated
        if context_start > 0:
            surrounding = '...' + surrounding
        if context_end < len(text):
            surrounding = surrounding + '...'

        return surrounding
