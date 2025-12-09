"""Attribute progression events to characters using AI"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .client import AIClient, AIResponse, AIError
from .cost_tracker import CostTracker
from .prompts import EVENT_ATTRIBUTION_SYSTEM
from .wiki_reference import get_wiki_cache
from ..db import get_connection, return_connection

logger = logging.getLogger(__name__)

# Confidence thresholds
AUTO_ACCEPT_THRESHOLD = 0.93
REVIEW_THRESHOLD = 0.70


@dataclass
class EventAttribution:
    """Attribution result for an event"""
    event_id: int
    event_type: str
    character_name: Optional[str]
    character_id: Optional[int]
    parsed_data: Dict[str, Any]
    confidence: float
    reasoning: str
    auto_accepted: bool
    needs_review: bool


class EventAttributor:
    """Attribute progression events to characters"""

    # Number of events to process per AI call
    BATCH_SIZE = 15

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        cost_tracker: Optional[CostTracker] = None
    ):
        """
        Initialize the event attributor.

        Args:
            ai_client: AIClient instance (created if not provided)
            cost_tracker: CostTracker instance (created if not provided)
        """
        self.ai_client = ai_client or AIClient()
        self.cost_tracker = cost_tracker or CostTracker()
        self.wiki_cache = get_wiki_cache()

    def attribute_events(
        self,
        chapter_id: int,
        chapter_number: str,
        events: List[Dict[str, Any]],
        chapter_characters: List[str]
    ) -> Tuple[List[EventAttribution], List[AIResponse]]:
        """
        Attribute events in a chapter to characters.

        Args:
            chapter_id: Database ID of the chapter
            chapter_number: Chapter number for display
            events: List of event dicts with id, raw_text, surrounding_text
            chapter_characters: List of character names in this chapter

        Returns:
            Tuple of (list of attributions, list of AI responses)
        """
        all_attributions = []
        all_responses = []

        # Process events in batches
        for i in range(0, len(events), self.BATCH_SIZE):
            batch = events[i:i + self.BATCH_SIZE]
            batch_num = (i // self.BATCH_SIZE) + 1
            total_batches = (len(events) + self.BATCH_SIZE - 1) // self.BATCH_SIZE

            logger.info(
                f"Chapter {chapter_number}: Processing event batch {batch_num}/{total_batches}"
            )

            try:
                attributions, response = self._attribute_batch(
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    events=batch,
                    chapter_characters=chapter_characters
                )
                all_attributions.extend(attributions)
                all_responses.append(response)

            except AIError as e:
                logger.error(f"Failed to process batch {batch_num}: {e}")
                # Create failed attributions for this batch
                for event in batch:
                    all_attributions.append(EventAttribution(
                        event_id=event['id'],
                        event_type='other',
                        character_name=None,
                        character_id=None,
                        parsed_data={},
                        confidence=0.0,
                        reasoning=f"AI processing failed: {e}",
                        auto_accepted=False,
                        needs_review=True
                    ))

        return all_attributions, all_responses

    def _attribute_batch(
        self,
        chapter_id: int,
        chapter_number: str,
        events: List[Dict[str, Any]],
        chapter_characters: List[str]
    ) -> Tuple[List[EventAttribution], AIResponse]:
        """Process a single batch of events"""

        # Build character context from wiki
        character_context = {}
        for char_name in chapter_characters[:30]:  # Limit to prevent huge prompts
            wiki_char = self.wiki_cache.find_character(char_name)
            if wiki_char:
                char_info = {
                    'species': wiki_char.species or 'Unknown',
                    'aliases': wiki_char.aliases[:5] if wiki_char.aliases else []
                }
                character_context[char_name] = char_info

        # Build wiki reference data for skills/spells/classes mentioned in events
        wiki_ref = self._build_wiki_reference_for_events(events, self.wiki_cache)

        # Format events for prompt
        events_for_prompt = [
            {
                'id': e['id'],
                'raw_text': e['raw_text'],
                'surrounding_text': e.get('surrounding_text', e.get('context', ''))[:500]
            }
            for e in events
        ]

        # Build user message with wiki reference data
        user_message = f"""Attribute these progression events to characters.

Chapter: {chapter_number}

=== CHARACTERS IN THIS CHAPTER ===
{json.dumps(chapter_characters[:30], indent=2)}

=== CHARACTER CONTEXT (known information) ===
{json.dumps(character_context, indent=2)}

=== WIKI REFERENCE DATA ===
Use this wiki data to validate skills/spells/classes. Items marked as FAKE are imaginary/joke abilities.
{json.dumps(wiki_ref, indent=2)}

=== EVENTS TO PROCESS ===
{json.dumps(events_for_prompt, indent=2)}

=== INSTRUCTIONS ===
For each event:
1. Determine the event_type (class_obtained, level_up, skill_obtained, etc.)
2. Identify which character the event belongs to (use wiki character names)
3. Extract structured data (class name, level, skill name, etc.)
4. Provide confidence score and reasoning
5. Check wiki validation status:
   - If skill/class is in "fake_skills" or "fake_classes" → classify as "false_positive" with confidence 0.95
   - If skill/class is in "unknown_skills", "unknown_spells", or "unknown_classes" → flag for review (confidence < 0.93)
   - If skill/class is found in wiki → can be auto-accepted if attribution is clear

IMPORTANT:
- FAKE items from wiki = auto-reject as "false_positive"
- UNKNOWN items (not in wiki) = needs manual review, use confidence 0.70-0.85
- KNOWN items in wiki = can be auto-accepted with confidence >= 0.93 if attribution is clear"""

        # Call AI
        response = self.ai_client.send_message(
            system_prompt=EVENT_ATTRIBUTION_SYSTEM,
            user_message=user_message,
            max_tokens=4096,
            expect_json=True
        )

        # Log the request
        self.cost_tracker.log_request(
            response=response,
            chapter_id=chapter_id,
            processing_type='event_attribution'
        )

        # Parse response
        attributions = self._parse_attribution_response(response, events)

        return attributions, response

    def _build_wiki_reference_for_events(
        self,
        events: List[Dict[str, Any]],
        wiki_cache
    ) -> Dict[str, Any]:
        """
        Build wiki reference data relevant to the events being processed.

        Extracts skill/spell/class names from events and looks them up in wiki.
        """
        import re

        wiki_ref = {
            'skills': {},
            'spells': {},
            'classes': {},
            'fake_skills': [],
            'fake_classes': [],
            'unknown_skills': [],
            'unknown_spells': [],
            'unknown_classes': []
        }

        for event in events:
            raw_text = event.get('raw_text', '')

            # Extract skill names: [Skill - X obtained!] or [Skill: X obtained!]
            skill_match = re.search(r'\[Skill\s*[-:]\s*([^\]!]+)', raw_text, re.IGNORECASE)
            if skill_match:
                skill_name = skill_match.group(1).strip()
                skill_info = wiki_cache.get_skill_info(skill_name)
                if skill_info:
                    wiki_ref['skills'][skill_name] = skill_info
                    if skill_info.get('is_fake'):
                        wiki_ref['fake_skills'].append(skill_name)
                else:
                    wiki_ref['unknown_skills'].append(skill_name)

            # Extract spell names: [Spell - X obtained!]
            spell_match = re.search(r'\[Spell\s*[-:]\s*([^\]!]+)', raw_text, re.IGNORECASE)
            if spell_match:
                spell_name = spell_match.group(1).strip()
                spell_info = wiki_cache.get_spell_info(spell_name)
                if spell_info:
                    wiki_ref['spells'][spell_name] = spell_info
                else:
                    wiki_ref['unknown_spells'].append(spell_name)

            # Extract class names: [X Level Y!] or [X class obtained!]
            class_match = re.search(r'\[([^\]]+?)\s+Level\s+\d+', raw_text, re.IGNORECASE)
            if not class_match:
                class_match = re.search(r'\[([^\]]+?)\s+class\s+obtained', raw_text, re.IGNORECASE)
            if class_match:
                class_name = class_match.group(1).strip()
                class_info = wiki_cache.get_class_info(class_name)
                if class_info:
                    wiki_ref['classes'][class_name] = class_info
                    if class_info.get('is_fake'):
                        wiki_ref['fake_classes'].append(class_name)
                else:
                    wiki_ref['unknown_classes'].append(class_name)

        # Add summary
        wiki_ref['summary'] = {
            'skills_found': len(wiki_ref['skills']),
            'spells_found': len(wiki_ref['spells']),
            'classes_found': len(wiki_ref['classes']),
            'fake_items_detected': len(wiki_ref['fake_skills']) + len(wiki_ref['fake_classes']),
            'unknown_items': len(wiki_ref['unknown_skills']) + len(wiki_ref['unknown_spells']) + len(wiki_ref['unknown_classes'])
        }

        return wiki_ref

    def _parse_attribution_response(
        self,
        response: AIResponse,
        original_events: List[Dict[str, Any]]
    ) -> List[EventAttribution]:
        """Parse the AI response into EventAttribution objects"""
        attributions = []
        event_id_map = {e['id']: e for e in original_events}

        if not response.parsed_json:
            logger.warning("No JSON in attribution response")
            # Return failed attributions for all events
            for event in original_events:
                attributions.append(EventAttribution(
                    event_id=event['id'],
                    event_type='other',
                    character_name=None,
                    character_id=None,
                    parsed_data={},
                    confidence=0.0,
                    reasoning="Failed to parse AI response",
                    auto_accepted=False,
                    needs_review=True
                ))
            return attributions

        data = response.parsed_json
        processed_ids = set()

        for attr in data.get('attributions', []):
            event_id = attr.get('event_id')
            if event_id not in event_id_map:
                continue

            processed_ids.add(event_id)

            confidence = attr.get('confidence', 0.5)
            character_name = attr.get('character_name')
            event_type = attr.get('event_type', 'other')

            # Look up character ID from wiki
            character_id = None
            if character_name:
                character_id = self.wiki_cache.get_character_id(character_name)

            # Determine acceptance/review status
            # False positives always need review - even if AI is confident,
            # a human should verify before discarding potential real events
            if event_type == 'false_positive':
                auto_accepted = False
                needs_review = True
            else:
                auto_accepted = confidence >= AUTO_ACCEPT_THRESHOLD
                needs_review = confidence < AUTO_ACCEPT_THRESHOLD

            attributions.append(EventAttribution(
                event_id=event_id,
                event_type=event_type,
                character_name=character_name,
                character_id=character_id,
                parsed_data=attr.get('parsed_data', {}),
                confidence=confidence,
                reasoning=attr.get('reasoning', ''),
                auto_accepted=auto_accepted,
                needs_review=needs_review
            ))

        # Handle any events that weren't in the response
        for event in original_events:
            if event['id'] not in processed_ids:
                attributions.append(EventAttribution(
                    event_id=event['id'],
                    event_type='other',
                    character_name=None,
                    character_id=None,
                    parsed_data={},
                    confidence=0.0,
                    reasoning="Event not processed by AI",
                    auto_accepted=False,
                    needs_review=True
                ))

        return attributions

    def save_attributions(
        self,
        attributions: List[EventAttribution]
    ) -> Dict[str, int]:
        """
        Save event attributions to the database.

        Args:
            attributions: List of EventAttribution objects

        Returns:
            Dict with counts: auto_accepted, flagged_review, failed
        """
        stats = {'auto_accepted': 0, 'flagged_review': 0, 'failed': 0}
        conn = None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            for attr in attributions:
                try:
                    # Update the raw_event with attribution data
                    cursor.execute(
                        """
                        UPDATE raw_events
                        SET
                            event_type = %s,
                            character_id = %s,
                            parsed_data = %s,
                            ai_confidence = %s,
                            ai_reasoning = %s,
                            is_assigned = %s,
                            needs_review = %s
                        WHERE id = %s
                        """,
                        (
                            attr.event_type,
                            attr.character_id,
                            json.dumps(attr.parsed_data) if attr.parsed_data else None,
                            attr.confidence,
                            attr.reasoning,
                            attr.auto_accepted,  # Only mark as assigned if auto-accepted
                            attr.needs_review,
                            attr.event_id
                        )
                    )

                    if attr.auto_accepted:
                        stats['auto_accepted'] += 1
                    elif attr.needs_review:
                        stats['flagged_review'] += 1
                    else:
                        stats['failed'] += 1

                except Exception as e:
                    logger.error(f"Failed to save attribution for event {attr.event_id}: {e}")
                    stats['failed'] += 1

            conn.commit()
            cursor.close()

            logger.info(
                f"Saved attributions: {stats['auto_accepted']} auto-accepted, "
                f"{stats['flagged_review']} flagged for review, "
                f"{stats['failed']} failed"
            )

            return stats

        except Exception as e:
            logger.error(f"Failed to save attributions: {e}")
            if conn:
                conn.rollback()
            return stats
        finally:
            if conn:
                return_connection(conn)

    def update_chapter_state(
        self,
        chapter_id: int,
        events_processed: int,
        auto_accepted: int,
        flagged_review: int
    ):
        """Update the AI processing state for a chapter"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO ai_chapter_state (
                    chapter_id, events_attributed, events_attributed_at,
                    events_processed, events_auto_accepted, events_flagged_review
                )
                VALUES (%s, TRUE, CURRENT_TIMESTAMP, %s, %s, %s)
                ON CONFLICT (chapter_id) DO UPDATE
                SET events_attributed = TRUE,
                    events_attributed_at = CURRENT_TIMESTAMP,
                    events_processed = EXCLUDED.events_processed,
                    events_auto_accepted = EXCLUDED.events_auto_accepted,
                    events_flagged_review = EXCLUDED.events_flagged_review
                """,
                (chapter_id, events_processed, auto_accepted, flagged_review)
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


def get_unprocessed_events(chapter_id: int) -> List[Dict[str, Any]]:
    """Get events that haven't been attributed yet"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, raw_text, surrounding_text, context, event_index
            FROM raw_events
            WHERE chapter_id = %s
              AND (ai_confidence IS NULL OR needs_review = TRUE)
              AND archived = FALSE
            ORDER BY event_index
            """,
            (chapter_id,)
        )

        events = [
            {
                'id': row[0],
                'raw_text': row[1],
                'surrounding_text': row[2] or row[3],  # Use surrounding_text or fall back to context
                'event_index': row[4]
            }
            for row in cursor.fetchall()
        ]

        cursor.close()
        return events

    except Exception as e:
        logger.error(f"Failed to get unprocessed events: {e}")
        return []
    finally:
        if conn:
            return_connection(conn)
