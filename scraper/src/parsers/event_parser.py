"""Parser for extracting potential progression events from chapter text"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BracketEvent:
    """Represents a single bracket occurrence found in text (unclassified)"""
    raw_text: str  # Text from [ to ] (or end of reasonable search)
    surrounding_text: str  # Context around the bracket
    position: int  # Character position in text where [ was found
    event_index: int  # Index of this event in the chapter (0-based)


class EventParser:
    """Parser for extracting ALL bracket occurrences from text"""

    # Context window size (characters before and after the bracket)
    CONTEXT_BEFORE = 150
    CONTEXT_AFTER = 150

    # Maximum length to search for closing bracket
    MAX_BRACKET_LENGTH = 300

    def __init__(self):
        """Initialize the parser"""
        pass

    def parse_text(self, text: str) -> List[BracketEvent]:
        """
        Parse text and extract ALL bracket occurrences

        Args:
            text: Chapter text to parse

        Returns:
            List of BracketEvent objects
        """
        events = []

        # Handle empty or malformed input gracefully
        if not text or not isinstance(text, str):
            logger.warning("Empty or invalid text provided to parser")
            return events

        # Find all '[' occurrences
        position = 0
        event_index = 0

        while position < len(text):
            # Find next '['
            bracket_start = text.find('[', position)

            if bracket_start == -1:
                # No more brackets found
                break

            # Extract the bracket content and surrounding context
            raw_text = self._extract_bracket_text(text, bracket_start)
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

        logger.info(f"Found {len(events)} bracket occurrences in text")
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
