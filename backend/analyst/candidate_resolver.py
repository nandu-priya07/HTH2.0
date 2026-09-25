"""
CandidateResolver module using RapidFuzz for fast, schema-aware fuzzy matching.
Identifies potential column, categorical value, and metric candidate matches with confidence scores
to enrich LLM context without blindly modifying user input.
"""

import logging
from typing import Dict, List, Any, Optional
import pandas as pd
from pydantic import BaseModel
from rapidfuzz import process, fuzz

from .preprocessor import PreprocessedQuery
from .value_indexer import ValueIndexer

logger = logging.getLogger(__name__)


class CandidateMatch(BaseModel):
    match_type: str  # "column", "value", "metric", "geographic"
    query_token: str
    matched_value: str
    confidence: float  # 0.0 to 1.0
    column_name: Optional[str] = None


class CandidateResolutionResult(BaseModel):
    column_candidates: List[CandidateMatch] = []
    value_candidates: List[CandidateMatch] = []
    metric_candidates: List[CandidateMatch] = []
    geo_candidates: List[CandidateMatch] = []

    def to_compact_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {}
        if self.column_candidates:
            res["columns"] = [
                {"query": c.query_token, "candidate": c.matched_value, "confidence": c.confidence}
                for c in self.column_candidates
            ]
        if self.value_candidates:
            res["values"] = [
                {"query": c.query_token, "candidate": c.matched_value, "column": c.column_name, "confidence": c.confidence}
                for c in self.value_candidates
            ]
        if self.metric_candidates:
            res["metrics"] = [
                {"query": c.query_token, "candidate": c.matched_value, "confidence": c.confidence}
                for c in self.metric_candidates
            ]
        if self.geo_candidates:
            res["geographic_locations"] = [
                {"query": c.query_token, "candidate": c.matched_value, "column": c.column_name, "confidence": c.confidence}
                for c in self.geo_candidates
            ]
        return res


KNOWN_METRICS = ["profit", "sales", "revenue", "amount", "price", "quantity", "score", "grade", "discount", "margin", "cost"]


class CandidateResolver:
    """
    Schema-aware fuzzy candidate resolver using RapidFuzz.
    Matches queries against column names, value index entries, and metric names.
    """

    def resolve(
        self,
        prep_query: PreprocessedQuery,
        df: Optional[pd.DataFrame] = None,
        schema: Optional[Dict[str, Any]] = None,
        dataset_id: Optional[str] = None,
        threshold: float = 75.0
    ) -> CandidateResolutionResult:
        result = CandidateResolutionResult()
        norm_q = prep_query.normalized_query
        tokens = prep_query.tokens

        # 1. Match Column Candidates
        col_names = []
        if df is not None and not df.empty:
            col_names = list(df.columns)
        elif schema and isinstance(schema, dict):
            num_cols = schema.get("numeric_columns", [])
            cat_cols = schema.get("categorical_columns", [])
            col_names = list(set(num_cols + cat_cols))

        if col_names:
            col_map = {c.lower(): c for c in col_names}
            # Search multi-word n-grams and single tokens
            ngrams = self._extract_ngrams(tokens, max_n=3)
            for ngram in ngrams:
                matches = process.extract(ngram, list(col_map.keys()), scorer=fuzz.QRatio, limit=1)
                for match_val, score, _ in matches:
                    if score >= threshold:
                        actual_col = col_map[match_val]
                        result.column_candidates.append(
                            CandidateMatch(
                                match_type="column",
                                query_token=ngram,
                                matched_value=actual_col,
                                confidence=round(score / 100.0, 2)
                            )
                        )

        # 2. Match Value Candidates (from ValueIndexer)
        if dataset_id and df is not None:
            idx = ValueIndexer.build_index(dataset_id, df)
            if idx and idx.indexed_values:
                val_map = {iv.normalized: iv for iv in idx.indexed_values}
                val_choices = list(val_map.keys())
                ngrams = self._extract_ngrams(tokens, max_n=3)

                seen_values = set()
                for ngram in ngrams:
                    if len(ngram) < 3:
                        continue
                    matches = process.extract(ngram, val_choices, scorer=fuzz.WRatio, limit=2)
                    for match_norm, score, _ in matches:
                        if score >= threshold:
                            matched_entry = val_map[match_norm]
                            v_key = (matched_entry.column, matched_entry.display)
                            if v_key not in seen_values:
                                seen_values.add(v_key)
                                match_obj = CandidateMatch(
                                    match_type="value",
                                    query_token=ngram,
                                    matched_value=matched_entry.display,
                                    column_name=matched_entry.column,
                                    confidence=round(score / 100.0, 2)
                                )
                                # Separate geo values if column is geographic
                                col_lower = matched_entry.column.lower()
                                if any(g in col_lower for g in ("country", "state", "city", "region", "location")):
                                    match_obj.match_type = "geographic"
                                    result.geo_candidates.append(match_obj)
                                else:
                                    result.value_candidates.append(match_obj)

        # 3. Match Metric Candidates
        for token in tokens:
            if len(token) >= 3:
                matches = process.extract(token, KNOWN_METRICS, scorer=fuzz.QRatio, limit=1)
                for m_val, score, _ in matches:
                    if score >= threshold and score < 100:
                        result.metric_candidates.append(
                            CandidateMatch(
                                match_type="metric",
                                query_token=token,
                                matched_value=m_val,
                                confidence=round(score / 100.0, 2)
                            )
                        )

        # Deduplicate candidates
        result.column_candidates = self._dedupe_candidates(result.column_candidates)
        result.value_candidates = self._dedupe_candidates(result.value_candidates)
        result.geo_candidates = self._dedupe_candidates(result.geo_candidates)
        result.metric_candidates = self._dedupe_candidates(result.metric_candidates)

        return result

    def _extract_ngrams(self, tokens: List[str], max_n: int = 3) -> List[str]:
        ngrams = list(tokens)
        n_tokens = len(tokens)
        for n in range(2, max_n + 1):
            for i in range(n_tokens - n + 1):
                ngram = " ".join(tokens[i : i + n])
                ngrams.append(ngram)
        return list(dict.fromkeys(ngrams))

    def _dedupe_candidates(self, candidates: List[CandidateMatch]) -> List[CandidateMatch]:
        seen = set()
        deduped = []
        for c in sorted(candidates, key=lambda x: x.confidence, reverse=True):
            key = (c.query_token, c.matched_value, c.column_name)
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        return deduped
