"""
SemanticQueryCache module for low-latency query interpretation caching.
Caches dataset schema context and deterministic QuerySpec interpretations by dataset_id,
normalized_query, and context hash.
"""

import hashlib
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel

from .models import LLMResponse, QuerySpec

logger = logging.getLogger(__name__)

_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}
_INTERPRETATION_CACHE: Dict[str, LLMResponse] = {}
_CACHE_MAX_SIZE = 500


class SemanticQueryCache:
    """
    In-memory LRU semantic cache for schema context and query interpretation QuerySpecs.
    Validates cache entries against dataset_id and version timestamp.
    """

    @staticmethod
    def _make_key(dataset_id: str, normalized_query: str, context_hash: str = "") -> str:
        raw_key = f"{dataset_id}:{normalized_query}:{context_hash}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def get_cached_interpretation(
        dataset_id: str,
        normalized_query: str,
        context_hash: str = ""
    ) -> Optional[LLMResponse]:
        if not dataset_id or not normalized_query:
            return None
        key = SemanticQueryCache._make_key(dataset_id, normalized_query, context_hash)
        cached = _INTERPRETATION_CACHE.get(key)
        if cached:
            logger.info(f"Semantic Cache HIT for dataset '{dataset_id}' query: '{normalized_query}'")
            return cached
        return None

    @staticmethod
    def cache_interpretation(
        dataset_id: str,
        normalized_query: str,
        response: LLMResponse,
        context_hash: str = ""
    ) -> None:
        if not dataset_id or not normalized_query or not response:
            return
        if response.type not in ("data_query", "direct_answer", "clarification"):
            return
        if len(_INTERPRETATION_CACHE) >= _CACHE_MAX_SIZE:
            # Evict oldest entry
            first_key = next(iter(_INTERPRETATION_CACHE))
            _INTERPRETATION_CACHE.pop(first_key, None)

        key = SemanticQueryCache._make_key(dataset_id, normalized_query, context_hash)
        _INTERPRETATION_CACHE[key] = response

    @staticmethod
    def get_cached_schema(dataset_id: str) -> Optional[Dict[str, Any]]:
        return _SCHEMA_CACHE.get(dataset_id)

    @staticmethod
    def cache_schema(dataset_id: str, schema_context: Dict[str, Any]) -> None:
        if dataset_id and schema_context:
            _SCHEMA_CACHE[dataset_id] = schema_context

    @staticmethod
    def clear() -> None:
        _SCHEMA_CACHE.clear()
        _INTERPRETATION_CACHE.clear()
