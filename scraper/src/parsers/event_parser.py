"""Parser for extracting progression events from chapter text"""

import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProgressionEvent:
    """Represents a single progression event found in text"""
    event_type: str  # class_obtained, class_evolution, class_consolidation, class_removed, level_up, skill_change, skill_consolidation, skill_obtained, skill_removed, spell_obtained, spell_removed, condition, aspect, title, rank, other
    raw_text: str  # Original bracketed text
    parsed_data: Dict[str, Any]  # Structured data
    context: str  # Surrounding text for disambiguation
    position: int  # Character position in text
    is_incomplete: bool = False  # Flag for intentionally incomplete/cancelled events


class EventParser:
    """Parser for extracting LitRPG progression events from text"""

    # Regex patterns for different event types
    # Note: The series uses various bracket styles, so we match \[ or [
    PATTERNS = {
        'class_obtained': [
            r'\[([^\]]+?)\s+[Cc]lass\s+[Oo]btained!?\]',
            r'\[([^\]]+?)\s+[Cc]lass\s+[Gg]ained!?\]',
            r'\[([^\]]+?)\s+[Cc]lass\s+[Aa]cquired!?\]',
        ],
        'class_evolution': [
            # Matches: [Conditions Met: Warrior → Weapon Expert!]
            r'\[[Cc]onditions\s+[Mm]et:\s*([^\]]+?)\s*[→>-]+\s*([^\]]+?)!?\]',
            # Matches: [Warrior → Weapon Expert Class!]
            # Also matches: [Class A -> Class B Class!]
            r'\[([^\]]+?)\s*[→>-]+\s*([^\]]+?)\s+[Cc]lass!?\]',
        ],
        'class_consolidation': [
            # Matches: [Warrior + Soldier Class Consolidated!]
            # Also matches: [Class A + Class B Class Consolidated!]
            r'\[([^\]]+?)\s*\+\s*([^\]]+?)\s+[Cc]lass\s+[Cc]onsolidated!?\]',
        ],
        'class_removed': [
            # Matches: [Innkeeper Class Removed!]
            r'\[([^\]]+?)\s+[Cc]lass\s+[Rr]emoved!?\]',
            r'\[([^\]]+?)\s+[Cc]lass\s+[Ll]ost\.?\]',
        ],
        'level_up': [
            r'\[([^\]]+?)\s+[Ll]evel\s+(\d+)!?\]',
            r'\[([^\]]+?)\s+[Ll]v\.?\s+(\d+)!?\]',
        ],
        'skill_change': [
            # Matches: [Skill Change - Royal Slap → Ghost's Hand!]
            r'\[[Ss]kill\s+[Cc]hange\s*[-–—:]\s*([^\]]+?)\s*[→>-]+\s*([^\]]+?)!?\]',
        ],
        'skill_consolidation': [
            # Matches: [Skill Consolidation: Deft Hand removed!]
            # Note: This captures the OLD skill being removed during consolidation
            r'\[[Ss]kill\s+[Cc]onsolidation:\s*([^\]]+?)\s+[Rr]emoved!?\]',
        ],
        'skill_obtained': [
            r'\[[Ss]kill\s*[-–—:]\s*([^\]]+?)\s+[Oo]btained!?\]',
            r'\[[Ss]kill\s*[-–—:]\s*([^\]]+?)\s+[Gg]ained!?\]',
            r'\[[Ss]kill\s*[-–—:]\s*([^\]]+?)\s+[Aa]cquired!?\]',
            r'\[[Ss]kill\s*[-–—:]\s*([^\]]+?)\s+[Ll]earned!?\]',
        ],
        'skill_removed': [
            # Matches: [Skill - Aroma of Spring Lost.]
            r'\[[Ss]kill\s*[-–—:]\s*([^\]]+?)\s+[Ll]ost\.?\]',
            r'\[[Ss]kill\s*[-–—:]\s*([^\]]+?)\s+[Rr]emoved!?\]',
        ],
        'spell_obtained': [
            r'\[[Ss]pell\s*[-–—:]\s*([^\]]+?)\s+[Oo]btained!?\]',
            r'\[[Ss]pell\s*[-–—:]\s*([^\]]+?)\s+[Gg]ained!?\]',
            r'\[[Ss]pell\s*[-–—:]\s*([^\]]+?)\s+[Aa]cquired!?\]',
            r'\[[Ss]pell\s*[-–—:]\s*([^\]]+?)\s+[Ll]earned!?\]',
        ],
        'spell_removed': [
            # Matches: [Spell - Fireball Lost.]
            r'\[[Ss]pell\s*[-–—:]\s*([^\]]+?)\s+[Ll]ost\.?\]',
            r'\[[Ss]pell\s*[-–—:]\s*([^\]]+?)\s+[Rr]emoved!?\]',
        ],
        'condition': [
            # Matches: [Condition - Terrible Hunger Received.]
            r'\[[Cc]ondition\s*[-–—:]\s*([^\]]+?)\s+[Rr]eceived\.?\]',
            r'\[[Cc]ondition\s*[-–—:]\s*([^\]]+?)\s+[Oo]btained\.?\]',
            r'\[[Cc]ondition\s*[-–—:]\s*([^\]]+?)\s+[Gg]ained\.?\]',
        ],
        'aspect': [
            # Matches: [Aspect - Body of the Eater Obtained.]
            r'\[[Aa]spect\s*[-–—:]\s*([^\]]+?)\s+[Oo]btained\.?\]',
            r'\[[Aa]spect\s*[-–—:]\s*([^\]]+?)\s+[Gg]ained\.?\]',
            r'\[[Aa]spect\s*[-–—:]\s*([^\]]+?)\s+[Rr]eceived\.?\]',
        ],
        'title': [
            # Matches: [Title - Hero Obtained!]
            r'\[[Tt]itle\s*[-–—:]\s*([^\]]+?)\s+[Oo]btained!?\]',
            r'\[[Tt]itle\s*[-–—:]\s*([^\]]+?)\s+[Gg]ained!?\]',
            r'\[[Tt]itle\s*[-–—:]\s*([^\]]+?)\s+[Aa]cquired!?\]',
        ],
        'rank': [
            # Matches: [Rank 1 Horror - Corpse Eater.]
            # Matches: [Rank 5 General]
            r'\[[Rr]ank\s+(\d+)\s+([^\]]+?)[-–—:]?\s*([^\]]*?)\.?\]',
        ],
        'other': [
            # Catch-all for other bracketed progression events
            # Matches things like [Reputation Increased] or other unknown formats
            # This should be LAST to avoid false positives
            r'\[([A-Z][^\]]{10,150}(?:[Oo]btained|[Gg]ained|[Rr]eceived|[Aa]cquired|[Ll]earned|[Ii]ncreased|[Dd]ecreased|[Uu]nlocked))\.?\]',
        ],
    }

    # Patterns for incomplete/cancelled events (intentional malformed brackets)
    INCOMPLETE_PATTERNS = [
        r'\[([^\]]+?)\s+[Cc]lass\s*$',  # Unclosed class bracket
        r'\[[Ss]kill\s*[-–—:]\s*([^\]]*?)$',  # Unclosed skill bracket
        r'\[([^\]]+?)\s+[Ll]evel\s*$',  # Unclosed level bracket
    ]

    # Context window size (characters before and after)
    CONTEXT_WINDOW = 150

    def __init__(self):
        """Initialize the parser with compiled regex patterns"""
        self.compiled_patterns = {}
        for event_type, patterns in self.PATTERNS.items():
            self.compiled_patterns[event_type] = [
                re.compile(pattern) for pattern in patterns
            ]

        # Compile incomplete patterns
        self.incomplete_patterns = [
            re.compile(pattern) for pattern in self.INCOMPLETE_PATTERNS
        ]

        # Track parsing errors for debugging
        self.parse_errors = []

    def parse_text(self, text: str) -> List[ProgressionEvent]:
        """
        Parse text and extract all progression events

        Args:
            text: Chapter text to parse

        Returns:
            List of ProgressionEvent objects (continues even if some events fail)
        """
        # Reset error tracking
        self.parse_errors = []

        events = []

        # Handle empty or malformed input gracefully
        if not text or not isinstance(text, str):
            logger.warning("Empty or invalid text provided to parser")
            return events

        # Parse regular events
        for event_type, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    try:
                        event = self._create_event(event_type, match, text)
                        if event:
                            events.append(event)
                    except Exception as e:
                        error_msg = f"Error parsing {event_type} event at position {match.start()}: {e}"
                        logger.debug(error_msg)
                        self.parse_errors.append({
                            'position': match.start(),
                            'raw_text': match.group(0) if match else 'N/A',
                            'error': str(e),
                            'event_type': event_type
                        })
                        # Continue parsing despite error
                        continue

        # Also look for incomplete/cancelled events (intentionally malformed)
        for pattern in self.incomplete_patterns:
            for match in pattern.finditer(text):
                try:
                    event = self._create_incomplete_event(match, text)
                    if event:
                        events.append(event)
                except Exception as e:
                    logger.debug(f"Error parsing incomplete event: {e}")
                    continue

        # Sort events by position in text
        events.sort(key=lambda x: x.position)

        if self.parse_errors:
            logger.warning(f"Parsed {len(events)} events with {len(self.parse_errors)} errors")
        else:
            logger.info(f"Parsed {len(events)} events from text")

        return events

    def _create_event(
        self,
        event_type: str,
        match: re.Match,
        full_text: str
    ) -> Optional[ProgressionEvent]:
        """
        Create a ProgressionEvent from a regex match

        Handles malformed data gracefully - returns None on failure
        """
        try:
            raw_text = match.group(0)
            position = match.start()

            # Extract context (gracefully handle errors)
            try:
                context = self._extract_context(full_text, position)
            except Exception as e:
                logger.debug(f"Error extracting context: {e}")
                context = raw_text  # Fall back to raw text

            # Parse specific data based on event type
            parsed_data = {}

            if event_type == 'class_obtained':
                class_name = match.group(1).strip() if match.lastindex >= 1 else ''
                if not class_name:
                    logger.debug(f"Empty class name in: {raw_text}")
                    return None
                parsed_data = {'class_name': class_name}

            elif event_type == 'class_evolution':
                if match.lastindex < 2:
                    logger.debug(f"Insufficient groups in class_evolution match: {raw_text}")
                    return None
                old_class = match.group(1).strip()
                new_class = match.group(2).strip()
                if not old_class or not new_class:
                    logger.debug(f"Empty class name in class evolution: {raw_text}")
                    return None
                parsed_data = {
                    'old_class': old_class,
                    'new_class': new_class
                }

            elif event_type == 'class_consolidation':
                if match.lastindex < 2:
                    logger.debug(f"Insufficient groups in class_consolidation match: {raw_text}")
                    return None
                # Could be multiple classes consolidating, but for now handle two
                class_1 = match.group(1).strip()
                class_2 = match.group(2).strip()
                if not class_1 or not class_2:
                    logger.debug(f"Empty class name in class consolidation: {raw_text}")
                    return None
                parsed_data = {
                    'old_classes': [class_1, class_2],
                    'consolidated': True
                }

            elif event_type == 'class_removed':
                class_name = match.group(1).strip() if match.lastindex >= 1 else ''
                if not class_name:
                    logger.debug(f"Empty class name in: {raw_text}")
                    return None
                parsed_data = {'class_name': class_name}

            elif event_type == 'level_up':
                if match.lastindex < 2:
                    logger.debug(f"Insufficient groups in level_up match: {raw_text}")
                    return None
                class_name = match.group(1).strip()
                try:
                    level = int(match.group(2))
                except (ValueError, IndexError) as e:
                    logger.debug(f"Invalid level number in: {raw_text} - {e}")
                    return None
                parsed_data = {
                    'class_name': class_name,
                    'level': level
                }

            elif event_type == 'skill_change':
                if match.lastindex < 2:
                    logger.debug(f"Insufficient groups in skill_change match: {raw_text}")
                    return None
                old_skill = match.group(1).strip()
                new_skill = match.group(2).strip()
                if not old_skill or not new_skill:
                    logger.debug(f"Empty skill name in skill change: {raw_text}")
                    return None
                parsed_data = {
                    'old_skill': old_skill,
                    'new_skill': new_skill
                }

            elif event_type == 'skill_consolidation':
                # This captures the old skill being removed during consolidation
                skill_name = match.group(1).strip() if match.lastindex >= 1 else ''
                if not skill_name:
                    logger.debug(f"Empty skill name in: {raw_text}")
                    return None
                parsed_data = {'skill_name': skill_name, 'consolidated': True}

            elif event_type == 'skill_obtained':
                skill_name = match.group(1).strip() if match.lastindex >= 1 else ''
                if not skill_name:
                    logger.debug(f"Empty skill name in: {raw_text}")
                    return None
                parsed_data = {'skill_name': skill_name}

            elif event_type == 'skill_removed':
                skill_name = match.group(1).strip() if match.lastindex >= 1 else ''
                if not skill_name:
                    logger.debug(f"Empty skill name in: {raw_text}")
                    return None
                parsed_data = {'skill_name': skill_name}

            elif event_type == 'spell_obtained':
                spell_name = match.group(1).strip() if match.lastindex >= 1 else ''
                if not spell_name:
                    logger.debug(f"Empty spell name in: {raw_text}")
                    return None
                parsed_data = {'spell_name': spell_name}

            elif event_type == 'spell_removed':
                spell_name = match.group(1).strip() if match.lastindex >= 1 else ''
                if not spell_name:
                    logger.debug(f"Empty spell name in: {raw_text}")
                    return None
                parsed_data = {'spell_name': spell_name}

            elif event_type == 'condition':
                condition_name = match.group(1).strip() if match.lastindex >= 1 else ''
                if not condition_name:
                    logger.debug(f"Empty condition name in: {raw_text}")
                    return None
                parsed_data = {'condition_name': condition_name}

            elif event_type == 'aspect':
                aspect_name = match.group(1).strip() if match.lastindex >= 1 else ''
                if not aspect_name:
                    logger.debug(f"Empty aspect name in: {raw_text}")
                    return None
                parsed_data = {'aspect_name': aspect_name}

            elif event_type == 'title':
                title_name = match.group(1).strip() if match.lastindex >= 1 else ''
                if not title_name:
                    logger.debug(f"Empty title name in: {raw_text}")
                    return None
                parsed_data = {'title_name': title_name}

            elif event_type == 'rank':
                if match.lastindex < 2:
                    logger.debug(f"Insufficient groups in rank match: {raw_text}")
                    return None
                try:
                    rank_number = int(match.group(1))
                except (ValueError, IndexError) as e:
                    logger.debug(f"Invalid rank number in: {raw_text} - {e}")
                    return None
                rank_type = match.group(2).strip()
                rank_name = match.group(3).strip() if match.lastindex >= 3 else ''
                if not rank_type:
                    logger.debug(f"Empty rank type in: {raw_text}")
                    return None
                parsed_data = {
                    'rank_number': rank_number,
                    'rank_type': rank_type,
                    'rank_name': rank_name
                }

            elif event_type == 'other':
                # Catch-all for unrecognized progression events
                content = match.group(1).strip() if match.lastindex >= 1 else raw_text
                parsed_data = {'content': content}

            return ProgressionEvent(
                event_type=event_type,
                raw_text=raw_text,
                parsed_data=parsed_data,
                context=context,
                position=position,
                is_incomplete=False
            )

        except Exception as e:
            logger.debug(f"Error creating event from match: {e}")
            return None

    def _create_incomplete_event(
        self,
        match: re.Match,
        full_text: str
    ) -> Optional[ProgressionEvent]:
        """
        Create an event for intentionally incomplete/cancelled progressions

        These are marked as incomplete and saved for manual review
        """
        try:
            raw_text = match.group(0)
            position = match.start()
            context = self._extract_context(full_text, position)

            # Try to determine what type of incomplete event this is
            text_lower = raw_text.lower()
            if 'class' in text_lower:
                event_type = 'class_obtained'
                parsed_data = {'class_name': match.group(1).strip() if match.lastindex >= 1 else '[incomplete]'}
            elif 'skill' in text_lower:
                event_type = 'skill_obtained'
                parsed_data = {'skill_name': match.group(1).strip() if match.lastindex >= 1 else '[incomplete]'}
            elif 'level' in text_lower:
                event_type = 'level_up'
                parsed_data = {'class_name': match.group(1).strip() if match.lastindex >= 1 else '[incomplete]'}
            else:
                return None

            return ProgressionEvent(
                event_type=event_type,
                raw_text=raw_text,
                parsed_data=parsed_data,
                context=context,
                position=position,
                is_incomplete=True
            )
        except Exception as e:
            logger.debug(f"Error creating incomplete event: {e}")
            return None

    def _extract_context(self, text: str, position: int) -> str:
        """Extract surrounding context for an event"""
        start = max(0, position - self.CONTEXT_WINDOW)
        end = min(len(text), position + self.CONTEXT_WINDOW)

        context = text[start:end]

        # Clean up context (remove excess whitespace, newlines)
        context = ' '.join(context.split())

        # Add ellipsis if truncated
        if start > 0:
            context = '...' + context
        if end < len(text):
            context = context + '...'

        return context

    def parse_and_validate(self, text: str) -> List[ProgressionEvent]:
        """
        Parse text and validate events

        This method applies additional validation rules to filter out
        false positives (e.g., character dialogue about skills)
        """
        events = self.parse_text(text)
        validated_events = []

        for event in events:
            if self._validate_event(event, text):
                validated_events.append(event)
            else:
                logger.debug(f"Event failed validation: {event.raw_text}")

        logger.info(
            f"Validated {len(validated_events)}/{len(events)} events"
        )
        return validated_events

    def _validate_event(self, event: ProgressionEvent, full_text: str) -> bool:
        """
        Validate an event to reduce false positives

        Returns:
            True if event appears to be genuine, False otherwise
        """
        # Basic validation: check if parsed data is reasonable

        if event.event_type == 'class_obtained':
            class_name = event.parsed_data.get('class_name', '')
            # Class names shouldn't be too long or too short
            if len(class_name) < 3 or len(class_name) > 100:
                return False

        elif event.event_type == 'level_up':
            level = event.parsed_data.get('level', 0)
            # Reasonable level range (The Wandering Inn has high levels)
            if level < 1 or level > 100:
                return False

        elif event.event_type in ['skill_obtained', 'spell_obtained']:
            name = event.parsed_data.get('skill_name') or event.parsed_data.get('spell_name', '')
            # Skill/spell names shouldn't be too short or too long
            if len(name) < 3 or len(name) > 200:
                return False

        # Additional validation could be added here:
        # - Check if event is inside dialogue quotes
        # - Check for common false positive patterns
        # - Use NLP to verify context

        return True

    def get_event_stats(self, events: List[ProgressionEvent]) -> Dict[str, int]:
        """Get statistics about parsed events"""
        stats = {
            'total': len(events),
            'class_obtained': 0,
            'class_evolution': 0,
            'class_consolidation': 0,
            'class_removed': 0,
            'level_up': 0,
            'skill_change': 0,
            'skill_consolidation': 0,
            'skill_obtained': 0,
            'skill_removed': 0,
            'spell_obtained': 0,
            'spell_removed': 0,
            'condition': 0,
            'aspect': 0,
            'title': 0,
            'rank': 0,
            'other': 0,
        }

        for event in events:
            if event.event_type in stats:
                stats[event.event_type] += 1

        return stats
