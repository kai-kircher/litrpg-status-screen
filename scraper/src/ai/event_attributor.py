"""Attribute progression events to characters using AI"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .client import AIClient, AIResponse, AIError
from .cost_tracker import CostTracker
from .prompts import EVENT_ATTRIBUTION_SYSTEM
from .character_extractor import CharacterExtractor
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
        cost_tracker: Optional[CostTracker] = None,
        character_extractor: Optional[CharacterExtractor] = None
    ):
        """
        Initialize the event attributor.

        Args:
            ai_client: AIClient instance (created if not provided)
            cost_tracker: CostTracker instance (created if not provided)
            character_extractor: CharacterExtractor for character lookup
        """
        self.ai_client = ai_client or AIClient()
        self.cost_tracker = cost_tracker or CostTracker()
        self.character_extractor = character_extractor or CharacterExtractor(
            ai_client=self.ai_client,
            cost_tracker=self.cost_tracker
        )

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

        # Build character context
        character_context = {}
        for char_name in chapter_characters[:30]:  # Limit to prevent huge prompts
            context = self.character_extractor.get_character_context(char_name)
            if context:
                knowledge = context.get('knowledge', {})
                character_context[char_name] = {
                    'species': knowledge.get('species', 'Unknown'),
                    'classes': knowledge.get('classes', []),
                    'current_levels': knowledge.get('current_levels', {})
                }

        # Format events for prompt
        events_for_prompt = [
            {
                'id': e['id'],
                'raw_text': e['raw_text'],
                'surrounding_text': e.get('surrounding_text', e.get('context', ''))[:500]
            }
            for e in events
        ]

        # Build user message
        user_message = f"""Attribute these progression events to characters.

Chapter: {chapter_number}

Characters in this chapter:
{json.dumps(chapter_characters[:30], indent=2)}

Character Context (known information):
{json.dumps(character_context, indent=2)}

Events to process:
{json.dumps(events_for_prompt, indent=2)}

For each event:
1. Determine the event_type (class_obtained, level_up, skill_obtained, etc.)
2. Identify which character the event belongs to
3. Extract structured data (class name, level, skill name, etc.)
4. Provide confidence score and reasoning"""

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

            # Look up character ID
            character_id = None
            if character_name:
                character_id = self.character_extractor.get_character_id(character_name)

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
