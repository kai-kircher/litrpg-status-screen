"""Batch processor for cost-effective bulk AI processing using Anthropic Batch API"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .batch_client import BatchClient, BatchRequest, BatchResult, BatchJob, BatchStatus, BatchResultType, BATCH_PRICING
from .prompts import CHARACTER_EXTRACTION_SYSTEM, EVENT_ATTRIBUTION_SYSTEM
from .wiki_reference import get_wiki_cache
from .character_extractor import ExtractedCharacter
from .event_attributor import EventAttribution, AUTO_ACCEPT_THRESHOLD
from ..db import get_connection, return_connection

logger = logging.getLogger(__name__)


@dataclass
class BatchJobInfo:
    """Information about a submitted batch job"""
    db_id: int
    batch_id: str
    batch_type: str
    total_requests: int


class BatchProcessor:
    """
    Handles batch processing for character extraction and event attribution.

    Workflow:
    1. prepare_*_batch() - Build batch requests from chapters/events
    2. submit_batch() - Submit to Anthropic and store in database
    3. check_batch_status() - Poll for completion
    4. process_batch_results() - Download and process results
    """

    def __init__(self, batch_client: Optional[BatchClient] = None):
        """
        Initialize the batch processor.

        Args:
            batch_client: BatchClient instance (created if not provided)
        """
        self.batch_client = batch_client or BatchClient()
        self._wiki_cache = None

    @property
    def wiki_cache(self):
        """Lazy-load wiki cache"""
        if self._wiki_cache is None:
            self._wiki_cache = get_wiki_cache()
        return self._wiki_cache

    # =========================================================================
    # CHARACTER EXTRACTION BATCHING
    # =========================================================================

    def prepare_character_extraction_batch(
        self,
        chapters: List[Tuple[int, int, str, str]],  # (id, order_index, chapter_number, content)
        max_text_length: int = 100000
    ) -> Tuple[List[BatchRequest], Dict[str, Dict]]:
        """
        Prepare batch requests for character extraction.

        Args:
            chapters: List of (chapter_id, order_index, chapter_number, content) tuples
            max_text_length: Maximum text length per chapter

        Returns:
            Tuple of (list of BatchRequest, metadata dict keyed by custom_id)
        """
        requests = []
        metadata = {}

        # Get wiki characters for the prompt (wiki is now the canonical source)
        wiki_characters = self.wiki_cache.get_all_character_names()
        wiki_context = self.wiki_cache.get_character_context_for_prompt(wiki_characters[:100])

        # Wiki is the source of truth for characters
        all_known_characters = wiki_characters

        # Get aliases from wiki cache
        known_aliases = self._get_wiki_character_aliases()

        for chapter_id, order_index, chapter_number, content in chapters:
            custom_id = f"char_extract_{chapter_id}"

            # Truncate content if needed
            text_to_analyze = content
            if len(content) > max_text_length:
                logger.warning(f"Chapter {chapter_number} truncated for batch")
                text_to_analyze = content[:max_text_length]

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

            requests.append(BatchRequest(
                custom_id=custom_id,
                system_prompt=CHARACTER_EXTRACTION_SYSTEM,
                user_message=user_message,
                max_tokens=4096,
                chapter_id=chapter_id,
                processing_type='character_extraction'
            ))

            metadata[custom_id] = {
                'chapter_id': chapter_id,
                'order_index': order_index,
                'chapter_number': chapter_number
            }

        return requests, metadata

    def process_character_extraction_results(
        self,
        batch_id: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Process results from a character extraction batch.

        Args:
            batch_id: The batch ID to process results for
            dry_run: If True, don't save to database

        Returns:
            Dict with processing stats
        """
        stats = {
            'chapters_processed': 0,
            'characters_found': 0,
            'new_characters_created': 0,
            'errors': 0
        }

        # Get batch job info from database
        batch_info = self._get_batch_job_info(batch_id)
        if not batch_info:
            raise ValueError(f"Batch {batch_id} not found in database")

        # Get request metadata
        request_metadata = self._get_batch_request_metadata(batch_info['db_id'])

        # Process results
        for result in self.batch_client.get_batch_results(batch_id, expect_json=True):
            metadata = request_metadata.get(result.custom_id, {})
            chapter_id = metadata.get('chapter_id')

            if result.result_type == BatchResultType.SUCCEEDED:
                characters = self._parse_character_extraction_result(result)

                if not dry_run and chapter_id:
                    new_count = self._save_extracted_characters(characters, chapter_id)
                    self._update_chapter_extraction_state(
                        chapter_id, len(characters), new_count
                    )
                    stats['new_characters_created'] += new_count

                stats['characters_found'] += len(characters)
                stats['chapters_processed'] += 1

                # Update request record
                if not dry_run:
                    self._update_batch_request_result(
                        batch_info['db_id'], result.custom_id,
                        result.result_type.value, result.input_tokens, result.output_tokens
                    )
            else:
                logger.error(f"Request {result.custom_id} failed: {result.error_message}")
                stats['errors'] += 1

                if not dry_run:
                    self._update_batch_request_result(
                        batch_info['db_id'], result.custom_id,
                        result.result_type.value, error_message=result.error_message
                    )

        # Update batch job status
        if not dry_run:
            self._update_batch_job_processed(batch_info['db_id'], stats)

        return stats

    # =========================================================================
    # EVENT ATTRIBUTION BATCHING
    # =========================================================================

    def prepare_event_attribution_batch(
        self,
        chapter_events: List[Dict[str, Any]]  # [{chapter_id, chapter_number, events: [...], characters: [...]}]
    ) -> Tuple[List[BatchRequest], Dict[str, Dict]]:
        """
        Prepare batch requests for event attribution.

        Args:
            chapter_events: List of dicts with chapter_id, chapter_number, events, characters

        Returns:
            Tuple of (list of BatchRequest, metadata dict keyed by custom_id)
        """
        requests = []
        metadata = {}

        for chapter_data in chapter_events:
            chapter_id = chapter_data['chapter_id']
            chapter_number = chapter_data['chapter_number']
            events = chapter_data['events']
            chapter_characters = chapter_data['characters']

            if not events:
                continue

            custom_id = f"event_attr_{chapter_id}"

            # Build wiki reference for these events
            wiki_ref = self._build_wiki_reference_for_events(events)

            # Build character context
            character_context = self._build_character_context(chapter_characters[:30])

            # Format events for prompt
            events_for_prompt = [
                {
                    'id': e['id'],
                    'raw_text': e['raw_text'],
                    'surrounding_text': e.get('surrounding_text', e.get('context', ''))[:500]
                }
                for e in events
            ]

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
   - If skill/class is in "fake_skills" or "fake_classes" -> classify as "false_positive" with confidence 0.95
   - If skill/class is in "unknown_skills", "unknown_spells", or "unknown_classes" -> flag for review (confidence < 0.93)
   - If skill/class is found in wiki -> can be auto-accepted if attribution is clear

IMPORTANT:
- FAKE items from wiki = auto-reject as "false_positive"
- UNKNOWN items (not in wiki) = needs manual review, use confidence 0.70-0.85
- KNOWN items in wiki = can be auto-accepted with confidence >= 0.93 if attribution is clear"""

            requests.append(BatchRequest(
                custom_id=custom_id,
                system_prompt=EVENT_ATTRIBUTION_SYSTEM,
                user_message=user_message,
                max_tokens=4096,
                chapter_id=chapter_id,
                processing_type='event_attribution'
            ))

            metadata[custom_id] = {
                'chapter_id': chapter_id,
                'chapter_number': chapter_number,
                'event_ids': [e['id'] for e in events]
            }

        return requests, metadata

    def process_event_attribution_results(
        self,
        batch_id: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Process results from an event attribution batch.

        Args:
            batch_id: The batch ID to process results for
            dry_run: If True, don't save to database

        Returns:
            Dict with processing stats
        """
        stats = {
            'chapters_processed': 0,
            'events_processed': 0,
            'auto_accepted': 0,
            'flagged_review': 0,
            'errors': 0
        }

        # Get batch job info
        batch_info = self._get_batch_job_info(batch_id)
        if not batch_info:
            raise ValueError(f"Batch {batch_id} not found in database")

        # Get request metadata
        request_metadata = self._get_batch_request_metadata(batch_info['db_id'])

        # Process results
        for result in self.batch_client.get_batch_results(batch_id, expect_json=True):
            metadata = request_metadata.get(result.custom_id, {})
            chapter_id = metadata.get('chapter_id')
            event_ids = metadata.get('event_ids', [])

            if result.result_type == BatchResultType.SUCCEEDED:
                attributions = self._parse_event_attribution_result(result, event_ids)

                if not dry_run:
                    save_stats = self._save_event_attributions(attributions)
                    stats['auto_accepted'] += save_stats['auto_accepted']
                    stats['flagged_review'] += save_stats['flagged_review']

                    if chapter_id:
                        self._update_chapter_attribution_state(
                            chapter_id, len(event_ids),
                            save_stats['auto_accepted'], save_stats['flagged_review']
                        )

                    self._update_batch_request_result(
                        batch_info['db_id'], result.custom_id,
                        result.result_type.value, result.input_tokens, result.output_tokens
                    )

                stats['events_processed'] += len(event_ids)
                stats['chapters_processed'] += 1
            else:
                logger.error(f"Request {result.custom_id} failed: {result.error_message}")
                stats['errors'] += 1

                if not dry_run:
                    self._update_batch_request_result(
                        batch_info['db_id'], result.custom_id,
                        result.result_type.value, error_message=result.error_message
                    )

        # Update batch job status
        if not dry_run:
            self._update_batch_job_processed(batch_info['db_id'], stats)

        return stats

    # =========================================================================
    # BATCH SUBMISSION AND TRACKING
    # =========================================================================

    def submit_batch(
        self,
        requests: List[BatchRequest],
        metadata: Dict[str, Dict],
        batch_type: str,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None
    ) -> BatchJobInfo:
        """
        Submit a batch to Anthropic and record in database.

        Args:
            requests: List of BatchRequest objects
            metadata: Metadata dict keyed by custom_id
            batch_type: 'character_extraction' or 'event_attribution'
            start_chapter: Optional start chapter index
            end_chapter: Optional end chapter index

        Returns:
            BatchJobInfo with database ID and batch ID
        """
        # Submit to Anthropic
        batch_job = self.batch_client.create_batch(requests)

        # Extract chapter IDs from metadata
        chapter_ids = list(set(
            m.get('chapter_id') for m in metadata.values() if m.get('chapter_id')
        ))

        # Store in database
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Insert batch job record
            cursor.execute(
                """
                INSERT INTO ai_batch_jobs (
                    batch_id, batch_type, processing_status, total_requests,
                    start_chapter, end_chapter, chapter_ids,
                    submitted_at, expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
                RETURNING id
                """,
                (
                    batch_job.batch_id,
                    batch_type,
                    batch_job.processing_status.value,
                    len(requests),
                    start_chapter,
                    end_chapter,
                    chapter_ids,
                    batch_job.expires_at
                )
            )
            db_id = cursor.fetchone()[0]

            # Insert request records
            for req in requests:
                meta = metadata.get(req.custom_id, {})
                cursor.execute(
                    """
                    INSERT INTO ai_batch_requests (
                        batch_job_id, custom_id, chapter_id, event_ids, request_type
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        db_id,
                        req.custom_id,
                        meta.get('chapter_id'),
                        meta.get('event_ids'),
                        batch_type
                    )
                )

            conn.commit()
            cursor.close()

            logger.info(f"Batch {batch_job.batch_id} submitted with {len(requests)} requests")

            return BatchJobInfo(
                db_id=db_id,
                batch_id=batch_job.batch_id,
                batch_type=batch_type,
                total_requests=len(requests)
            )

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to save batch job: {e}")
            raise
        finally:
            if conn:
                return_connection(conn)

    def check_batch_status(self, batch_id: str) -> BatchJob:
        """
        Check the status of a batch and update database.

        Args:
            batch_id: The Anthropic batch ID

        Returns:
            BatchJob with current status
        """
        batch_job = self.batch_client.get_batch_status(batch_id)

        # Update database
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE ai_batch_jobs
                SET processing_status = %s,
                    requests_succeeded = %s,
                    requests_errored = %s,
                    requests_canceled = %s,
                    requests_expired = %s,
                    ended_at = %s,
                    results_url = %s
                WHERE batch_id = %s
                """,
                (
                    batch_job.processing_status.value,
                    batch_job.request_counts['succeeded'],
                    batch_job.request_counts['errored'],
                    batch_job.request_counts['canceled'],
                    batch_job.request_counts['expired'],
                    batch_job.ended_at,
                    batch_job.results_url,
                    batch_id
                )
            )

            conn.commit()
            cursor.close()

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to update batch status: {e}")
        finally:
            if conn:
                return_connection(conn)

        return batch_job

    def get_pending_batches(self) -> List[Dict[str, Any]]:
        """Get all batches that are still processing"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, batch_id, batch_type, processing_status,
                       total_requests, created_at, expires_at
                FROM ai_batch_jobs
                WHERE processing_status IN ('in_progress', 'canceling')
                ORDER BY created_at
                """
            )

            batches = []
            for row in cursor.fetchall():
                batches.append({
                    'db_id': row[0],
                    'batch_id': row[1],
                    'batch_type': row[2],
                    'processing_status': row[3],
                    'total_requests': row[4],
                    'created_at': row[5],
                    'expires_at': row[6]
                })

            cursor.close()
            return batches

        except Exception as e:
            logger.error(f"Failed to get pending batches: {e}")
            return []
        finally:
            if conn:
                return_connection(conn)

    def get_completed_batches_awaiting_processing(self) -> List[Dict[str, Any]]:
        """Get batches that completed but results haven't been processed"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, batch_id, batch_type, total_requests,
                       requests_succeeded, ended_at
                FROM ai_batch_jobs
                WHERE processing_status = 'ended'
                  AND results_processed_at IS NULL
                ORDER BY ended_at
                """
            )

            batches = []
            for row in cursor.fetchall():
                batches.append({
                    'db_id': row[0],
                    'batch_id': row[1],
                    'batch_type': row[2],
                    'total_requests': row[3],
                    'requests_succeeded': row[4],
                    'ended_at': row[5]
                })

            cursor.close()
            return batches

        except Exception as e:
            logger.error(f"Failed to get completed batches: {e}")
            return []
        finally:
            if conn:
                return_connection(conn)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_wiki_character_aliases(self) -> Dict[str, List[str]]:
        """Get character name to aliases mapping from wiki cache"""
        aliases = {}
        for name in self.wiki_cache.get_all_character_names():
            char = self.wiki_cache.find_character(name)
            if char and char.aliases:
                aliases[name] = char.aliases
        return aliases

    def _build_character_context(self, character_names: List[str]) -> Dict[str, Any]:
        """Build character context for event attribution from wiki"""
        context = {}
        for name in character_names:
            wiki_char = self.wiki_cache.find_character(name)
            if wiki_char:
                context[name] = {
                    'species': wiki_char.species or 'Unknown',
                    'aliases': wiki_char.aliases[:5] if wiki_char.aliases else []
                }
        return context

    def _build_wiki_reference_for_events(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build wiki reference data for events"""
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

            # Extract skill names
            skill_match = re.search(r'\[Skill\s*[-:]\s*([^\]!]+)', raw_text, re.IGNORECASE)
            if skill_match:
                skill_name = skill_match.group(1).strip()
                skill_info = self.wiki_cache.get_skill_info(skill_name)
                if skill_info:
                    wiki_ref['skills'][skill_name] = skill_info
                    if skill_info.get('is_fake'):
                        wiki_ref['fake_skills'].append(skill_name)
                else:
                    wiki_ref['unknown_skills'].append(skill_name)

            # Extract spell names
            spell_match = re.search(r'\[Spell\s*[-:]\s*([^\]!]+)', raw_text, re.IGNORECASE)
            if spell_match:
                spell_name = spell_match.group(1).strip()
                spell_info = self.wiki_cache.get_spell_info(spell_name)
                if spell_info:
                    wiki_ref['spells'][spell_name] = spell_info
                else:
                    wiki_ref['unknown_spells'].append(spell_name)

            # Extract class names
            class_match = re.search(r'\[([^\]]+?)\s+Level\s+\d+', raw_text, re.IGNORECASE)
            if not class_match:
                class_match = re.search(r'\[([^\]]+?)\s+class\s+obtained', raw_text, re.IGNORECASE)
            if class_match:
                class_name = class_match.group(1).strip()
                class_info = self.wiki_cache.get_class_info(class_name)
                if class_info:
                    wiki_ref['classes'][class_name] = class_info
                    if class_info.get('is_fake'):
                        wiki_ref['fake_classes'].append(class_name)
                else:
                    wiki_ref['unknown_classes'].append(class_name)

        wiki_ref['summary'] = {
            'skills_found': len(wiki_ref['skills']),
            'spells_found': len(wiki_ref['spells']),
            'classes_found': len(wiki_ref['classes']),
            'fake_items_detected': len(wiki_ref['fake_skills']) + len(wiki_ref['fake_classes']),
            'unknown_items': len(wiki_ref['unknown_skills']) + len(wiki_ref['unknown_spells']) + len(wiki_ref['unknown_classes'])
        }

        return wiki_ref

    def _parse_character_extraction_result(self, result: BatchResult) -> List[ExtractedCharacter]:
        """Parse character extraction result into ExtractedCharacter objects"""
        characters = []

        if not result.parsed_json:
            return characters

        data = result.parsed_json

        for char in data.get('characters_mentioned', []):
            characters.append(ExtractedCharacter(
                name=char.get('name', 'Unknown'),
                confidence=char.get('confidence', 0.5),
                alias_used=char.get('alias_used'),
                is_new=False
            ))

        for char in data.get('new_characters', []):
            characters.append(ExtractedCharacter(
                name=char.get('name', 'Unknown'),
                confidence=0.8,
                is_new=True,
                species=char.get('species'),
                description=char.get('description')
            ))

        return characters

    def _parse_event_attribution_result(
        self,
        result: BatchResult,
        event_ids: List[int]
    ) -> List[EventAttribution]:
        """Parse event attribution result into EventAttribution objects"""
        attributions = []
        event_id_set = set(event_ids)
        processed_ids = set()

        if result.parsed_json:
            data = result.parsed_json

            for attr in data.get('attributions', []):
                event_id = attr.get('event_id')
                if event_id not in event_id_set:
                    continue

                processed_ids.add(event_id)
                confidence = attr.get('confidence', 0.5)
                event_type = attr.get('event_type', 'other')

                # Look up character ID
                character_name = attr.get('character_name')
                character_id = self._get_character_id(character_name) if character_name else None

                # Determine acceptance
                # Only auto-accept if confidence is high AND we found a character
                # Events without a character_id need manual review to assign one
                if event_type == 'false_positive':
                    auto_accepted = False
                    needs_review = True
                else:
                    has_character = character_id is not None
                    auto_accepted = confidence >= AUTO_ACCEPT_THRESHOLD and has_character
                    needs_review = not auto_accepted

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

        # Handle unprocessed events
        for event_id in event_ids:
            if event_id not in processed_ids:
                attributions.append(EventAttribution(
                    event_id=event_id,
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

    def _get_character_id(self, name: str) -> Optional[int]:
        """Look up character ID by name from wiki_characters"""
        if not name:
            return None
        return self.wiki_cache.get_character_id(name)

    def _save_extracted_characters(
        self,
        characters: List[ExtractedCharacter],
        chapter_id: int
    ) -> int:
        """Update first_appearance_chapter_id for characters found in wiki"""
        updated_count = 0
        conn = None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            for char in characters:
                # Look up character in wiki
                wiki_char = self.wiki_cache.find_character(char.name)
                if wiki_char and wiki_char.first_appearance_chapter_id is None:
                    # Update first_appearance_chapter_id if not set
                    cursor.execute(
                        """
                        UPDATE wiki_characters
                        SET first_appearance_chapter_id = %s
                        WHERE id = %s AND first_appearance_chapter_id IS NULL
                        """,
                        (chapter_id, wiki_char.id)
                    )
                    if cursor.rowcount > 0:
                        updated_count += 1
                        logger.debug(f"Updated first appearance for {char.name}")

            conn.commit()
            cursor.close()
            return updated_count

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to update character first appearances: {e}")
            return 0
        finally:
            if conn:
                return_connection(conn)

    def _save_event_attributions(self, attributions: List[EventAttribution]) -> Dict[str, int]:
        """Save event attributions to database"""
        stats = {'auto_accepted': 0, 'flagged_review': 0, 'failed': 0}
        conn = None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            for attr in attributions:
                try:
                    cursor.execute(
                        """
                        UPDATE raw_events
                        SET event_type = %s, character_id = %s, parsed_data = %s,
                            ai_confidence = %s, ai_reasoning = %s,
                            is_assigned = %s, needs_review = %s
                        WHERE id = %s
                        """,
                        (
                            attr.event_type,
                            attr.character_id,
                            json.dumps(attr.parsed_data) if attr.parsed_data else None,
                            attr.confidence,
                            attr.reasoning,
                            attr.auto_accepted,
                            attr.needs_review,
                            attr.event_id
                        )
                    )

                    if attr.auto_accepted:
                        stats['auto_accepted'] += 1
                    elif attr.needs_review:
                        stats['flagged_review'] += 1

                except Exception as e:
                    logger.error(f"Failed to save attribution for event {attr.event_id}: {e}")
                    stats['failed'] += 1

            conn.commit()
            cursor.close()
            return stats

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to save attributions: {e}")
            return stats
        finally:
            if conn:
                return_connection(conn)

    def _update_chapter_extraction_state(
        self, chapter_id: int, characters_found: int, new_characters: int
    ):
        """Update AI processing state for character extraction"""
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
            if conn:
                conn.rollback()
            logger.error(f"Failed to update chapter state: {e}")
        finally:
            if conn:
                return_connection(conn)

    def _update_chapter_attribution_state(
        self, chapter_id: int, events_processed: int, auto_accepted: int, flagged_review: int
    ):
        """Update AI processing state for event attribution"""
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
            if conn:
                conn.rollback()
            logger.error(f"Failed to update chapter state: {e}")
        finally:
            if conn:
                return_connection(conn)

    def _get_batch_job_info(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get batch job info from database"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, batch_type FROM ai_batch_jobs WHERE batch_id = %s",
                (batch_id,)
            )
            row = cursor.fetchone()
            cursor.close()
            if row:
                return {'db_id': row[0], 'batch_type': row[1]}
            return None
        except Exception as e:
            logger.error(f"Failed to get batch job info: {e}")
            return None
        finally:
            if conn:
                return_connection(conn)

    def _get_batch_request_metadata(self, db_id: int) -> Dict[str, Dict]:
        """Get request metadata from database"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT custom_id, chapter_id, event_ids
                FROM ai_batch_requests
                WHERE batch_job_id = %s
                """,
                (db_id,)
            )
            metadata = {}
            for row in cursor.fetchall():
                metadata[row[0]] = {
                    'chapter_id': row[1],
                    'event_ids': row[2] or []
                }
            cursor.close()
            return metadata
        except Exception as e:
            logger.error(f"Failed to get batch request metadata: {e}")
            return {}
        finally:
            if conn:
                return_connection(conn)

    def _update_batch_request_result(
        self,
        batch_db_id: int,
        custom_id: str,
        result_type: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error_message: Optional[str] = None
    ):
        """Update individual request result in database"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE ai_batch_requests
                SET result_type = %s, result_processed = TRUE,
                    input_tokens = %s, output_tokens = %s, error_message = %s
                WHERE batch_job_id = %s AND custom_id = %s
                """,
                (result_type, input_tokens, output_tokens, error_message, batch_db_id, custom_id)
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to update batch request: {e}")
        finally:
            if conn:
                return_connection(conn)

    def _update_batch_job_processed(self, db_id: int, stats: Dict[str, Any]):
        """Mark batch job as fully processed"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Calculate total tokens from requests
            cursor.execute(
                """
                SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0)
                FROM ai_batch_requests
                WHERE batch_job_id = %s AND result_type = 'succeeded'
                """,
                (db_id,)
            )
            row = cursor.fetchone()
            total_input = row[0]
            total_output = row[1]

            # Calculate cost (batch pricing is 50% of standard)
            estimated_cost = self.batch_client.calculate_batch_cost(total_input, total_output)

            cursor.execute(
                """
                UPDATE ai_batch_jobs
                SET processing_status = 'results_processed',
                    results_processed_at = CURRENT_TIMESTAMP,
                    total_input_tokens = %s,
                    total_output_tokens = %s,
                    estimated_cost_usd = %s
                WHERE id = %s
                """,
                (total_input, total_output, estimated_cost, db_id)
            )
            conn.commit()
            cursor.close()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to update batch job processed: {e}")
        finally:
            if conn:
                return_connection(conn)
