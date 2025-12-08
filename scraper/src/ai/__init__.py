"""AI module for character extraction and event attribution"""

from .client import AIClient, AIError
from .cost_tracker import CostTracker
from .character_extractor import CharacterExtractor
from .event_attributor import EventAttributor
from .wiki_reference import WikiReferenceCache, get_wiki_cache
from .batch_client import BatchClient, BatchRequest, BatchJob, BatchStatus, BatchResultType
from .batch_processor import BatchProcessor, BatchJobInfo

__all__ = [
    'AIClient',
    'AIError',
    'CostTracker',
    'CharacterExtractor',
    'EventAttributor',
    'WikiReferenceCache',
    'get_wiki_cache',
    # Batch API support
    'BatchClient',
    'BatchRequest',
    'BatchJob',
    'BatchStatus',
    'BatchResultType',
    'BatchProcessor',
    'BatchJobInfo',
]
