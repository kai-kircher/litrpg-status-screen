"""Wiki reference data for AI processing"""

import logging
import re
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass

from ..db import get_connection, return_connection

logger = logging.getLogger(__name__)


@dataclass
class WikiCharacter:
    """Wiki character data"""
    id: int
    name: str
    aliases: List[str]
    species: Optional[str]
    status: Optional[str]
    wiki_url: str


@dataclass
class WikiAbility:
    """Wiki skill or spell data"""
    id: int
    name: str
    normalized_name: str
    is_fake: bool
    effect: Optional[str] = None
    tier: Optional[int] = None  # For spells only


@dataclass
class WikiClass:
    """Wiki class data"""
    id: int
    name: str
    normalized_name: str
    is_fake: bool
    description: Optional[str] = None


class WikiReferenceCache:
    """Cache for wiki reference data used by AI processing"""

    def __init__(self):
        self._characters: Dict[str, WikiCharacter] = {}
        self._character_aliases: Dict[str, str] = {}  # alias -> canonical name
        self._skills: Dict[str, WikiAbility] = {}
        self._spells: Dict[str, WikiAbility] = {}
        self._classes: Dict[str, WikiClass] = {}
        self._fake_skills: Set[str] = set()
        self._fake_classes: Set[str] = set()
        self._loaded = False

    def load(self):
        """Load all wiki reference data into memory"""
        if self._loaded:
            return

        self._load_characters()
        self._load_skills()
        self._load_spells()
        self._load_classes()
        self._loaded = True

        logger.info(
            f"Wiki cache loaded: {len(self._characters)} characters, "
            f"{len(self._skills)} skills, {len(self._spells)} spells, "
            f"{len(self._classes)} classes"
        )

    def _load_characters(self):
        """Load wiki characters"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, name, aliases, species, status, wiki_url
                FROM wiki_characters
                """
            )

            for row in cursor.fetchall():
                char_id, name, aliases, species, status, wiki_url = row
                char = WikiCharacter(
                    id=char_id,
                    name=name,
                    aliases=aliases or [],
                    species=species,
                    status=status,
                    wiki_url=wiki_url
                )

                # Index by lowercase name
                self._characters[name.lower()] = char

                # Index by aliases
                if aliases:
                    for alias in aliases:
                        self._character_aliases[alias.lower()] = name

            cursor.close()

        except Exception as e:
            logger.error(f"Failed to load wiki characters: {e}")
        finally:
            if conn:
                return_connection(conn)

    def _load_skills(self):
        """Load wiki skills"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, name, normalized_name, is_fake, effect
                FROM wiki_skills
                """
            )

            for row in cursor.fetchall():
                skill_id, name, normalized_name, is_fake, effect = row
                skill = WikiAbility(
                    id=skill_id,
                    name=name,
                    normalized_name=normalized_name,
                    is_fake=is_fake,
                    effect=effect
                )

                self._skills[normalized_name] = skill

                if is_fake:
                    self._fake_skills.add(normalized_name)

            cursor.close()

        except Exception as e:
            logger.error(f"Failed to load wiki skills: {e}")
        finally:
            if conn:
                return_connection(conn)

    def _load_spells(self):
        """Load wiki spells"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, name, normalized_name, tier, effect
                FROM wiki_spells
                """
            )

            for row in cursor.fetchall():
                spell_id, name, normalized_name, tier, effect = row
                spell = WikiAbility(
                    id=spell_id,
                    name=name,
                    normalized_name=normalized_name,
                    is_fake=False,  # No fake spells in wiki
                    effect=effect,
                    tier=tier
                )

                self._spells[normalized_name] = spell

            cursor.close()

        except Exception as e:
            logger.error(f"Failed to load wiki spells: {e}")
        finally:
            if conn:
                return_connection(conn)

    def _load_classes(self):
        """Load wiki classes"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, name, normalized_name, is_fake, description
                FROM wiki_classes
                """
            )

            for row in cursor.fetchall():
                class_id, name, normalized_name, is_fake, description = row
                cls = WikiClass(
                    id=class_id,
                    name=name,
                    normalized_name=normalized_name,
                    is_fake=is_fake,
                    description=description
                )

                self._classes[normalized_name] = cls

                if is_fake:
                    self._fake_classes.add(normalized_name)

            cursor.close()

        except Exception as e:
            logger.error(f"Failed to load wiki classes: {e}")
        finally:
            if conn:
                return_connection(conn)

    # =========================================================================
    # Character Matching
    # =========================================================================

    def get_all_character_names(self) -> List[str]:
        """Get list of all wiki character names"""
        self.load()
        return [c.name for c in self._characters.values()]

    def find_character(self, name: str) -> Optional[WikiCharacter]:
        """Find a character by name or alias"""
        self.load()

        name_lower = name.lower()

        # Direct match
        if name_lower in self._characters:
            return self._characters[name_lower]

        # Alias match
        if name_lower in self._character_aliases:
            canonical_name = self._character_aliases[name_lower]
            return self._characters.get(canonical_name.lower())

        return None

    def get_character_context_for_prompt(self, names: List[str]) -> str:
        """Build character context string for AI prompts"""
        self.load()

        lines = []
        for name in names:
            char = self.find_character(name)
            if char:
                info_parts = [f"- {char.name}"]
                if char.species:
                    info_parts.append(f"({char.species})")
                if char.aliases:
                    info_parts.append(f"[aliases: {', '.join(char.aliases[:3])}]")
                lines.append(' '.join(info_parts))

        return '\n'.join(lines) if lines else "(no wiki data available)"

    # =========================================================================
    # Skill Matching
    # =========================================================================

    def normalize_ability_name(self, name: str) -> str:
        """Normalize a skill/spell name for matching"""
        # Remove brackets
        normalized = re.sub(r'[\[\]]', '', name)
        # Lowercase
        normalized = normalized.lower()
        # Remove common prefixes
        normalized = re.sub(r'^(skill|spell)\s*[-:]\s*', '', normalized)
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        return normalized

    def find_skill(self, name: str) -> Optional[WikiAbility]:
        """Find a skill by name"""
        self.load()
        normalized = self.normalize_ability_name(name)
        return self._skills.get(normalized)

    def is_known_skill(self, name: str) -> bool:
        """Check if skill exists in wiki"""
        return self.find_skill(name) is not None

    def is_fake_skill(self, name: str) -> bool:
        """Check if skill is marked as fake/imaginary in wiki"""
        self.load()
        normalized = self.normalize_ability_name(name)
        return normalized in self._fake_skills

    def get_skill_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detailed skill info"""
        skill = self.find_skill(name)
        if skill:
            return {
                'name': skill.name,
                'effect': skill.effect,
                'is_fake': skill.is_fake
            }
        return None

    # =========================================================================
    # Spell Matching
    # =========================================================================

    def find_spell(self, name: str) -> Optional[WikiAbility]:
        """Find a spell by name"""
        self.load()
        normalized = self.normalize_ability_name(name)
        return self._spells.get(normalized)

    def is_known_spell(self, name: str) -> bool:
        """Check if spell exists in wiki"""
        return self.find_spell(name) is not None

    def get_spell_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detailed spell info"""
        spell = self.find_spell(name)
        if spell:
            return {
                'name': spell.name,
                'tier': spell.tier,
                'effect': spell.effect
            }
        return None

    # =========================================================================
    # Class Matching
    # =========================================================================

    def normalize_class_name(self, name: str) -> str:
        """Normalize a class name for matching"""
        # Remove brackets
        normalized = re.sub(r'[\[\]]', '', name)
        # Lowercase
        normalized = normalized.lower()
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        return normalized

    def find_class(self, name: str) -> Optional[WikiClass]:
        """Find a class by name"""
        self.load()
        normalized = self.normalize_class_name(name)
        return self._classes.get(normalized)

    def is_known_class(self, name: str) -> bool:
        """Check if class exists in wiki"""
        return self.find_class(name) is not None

    def is_fake_class(self, name: str) -> bool:
        """Check if class is marked as fake/hypothetical in wiki"""
        self.load()
        normalized = self.normalize_class_name(name)
        return normalized in self._fake_classes

    def get_class_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detailed class info"""
        cls = self.find_class(name)
        if cls:
            return {
                'name': cls.name,
                'description': cls.description,
                'is_fake': cls.is_fake
            }
        return None

    # =========================================================================
    # Validation
    # =========================================================================

    def validate_event(self, event_type: str, event_text: str) -> Dict[str, Any]:
        """
        Validate an event against wiki data.

        Returns dict with:
        - is_valid: bool
        - is_fake: bool (if known to be fake/imaginary)
        - is_unknown: bool (not found in wiki - needs review)
        - wiki_match: matching wiki entry if found
        - validation_note: explanation
        """
        self.load()

        result = {
            'is_valid': True,
            'is_fake': False,
            'is_unknown': False,
            'wiki_match': None,
            'validation_note': None
        }

        # Extract ability/class name from event text
        # Pattern: [Something - Name obtained!] or [Class Level X!]
        name_match = re.search(r'\[(?:Skill|Spell)\s*[-:]\s*([^\]!]+)', event_text, re.IGNORECASE)
        class_match = re.search(r'\[([^\]]+?)\s+Level\s+\d+', event_text, re.IGNORECASE)
        class_obtained_match = re.search(r'\[([^\]]+?)\s+class\s+obtained', event_text, re.IGNORECASE)

        if event_type in ['skill_obtained', 'skill_change', 'skill_consolidation']:
            if name_match:
                skill_name = name_match.group(1).strip()
                skill = self.find_skill(skill_name)
                if skill:
                    result['wiki_match'] = skill.name
                    if skill.is_fake:
                        result['is_fake'] = True
                        result['is_valid'] = False
                        result['validation_note'] = f"Wiki lists '{skill.name}' as a fake/imaginary skill - auto-reject"
                else:
                    # Skill not in wiki - flag for review
                    result['is_unknown'] = True
                    result['validation_note'] = f"Skill '{skill_name}' not found in wiki - needs review"

        elif event_type in ['spell_obtained']:
            if name_match:
                spell_name = name_match.group(1).strip()
                spell = self.find_spell(spell_name)
                if spell:
                    result['wiki_match'] = spell.name
                else:
                    # Spell not in wiki - flag for review
                    result['is_unknown'] = True
                    result['validation_note'] = f"Spell '{spell_name}' not found in wiki - needs review"

        elif event_type in ['class_obtained', 'level_up', 'class_evolution']:
            class_name = None
            if class_match:
                class_name = class_match.group(1).strip()
            elif class_obtained_match:
                class_name = class_obtained_match.group(1).strip()

            if class_name:
                cls = self.find_class(class_name)
                if cls:
                    result['wiki_match'] = cls.name
                    if cls.is_fake:
                        result['is_fake'] = True
                        result['is_valid'] = False
                        result['validation_note'] = f"Wiki lists '{cls.name}' as a fake/hypothetical class - auto-reject"
                else:
                    # Class not in wiki - flag for review
                    result['is_unknown'] = True
                    result['validation_note'] = f"Class '{class_name}' not found in wiki - needs review"

        return result


# Global singleton instance
_wiki_cache: Optional[WikiReferenceCache] = None


def get_wiki_cache() -> WikiReferenceCache:
    """Get or create the global wiki cache"""
    global _wiki_cache
    if _wiki_cache is None:
        _wiki_cache = WikiReferenceCache()
    return _wiki_cache
