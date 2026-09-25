"""
QueryPreprocessor module for low-latency semantic query processing.
Normalizes whitespace, repeated punctuation, casing, and common abbreviations
while preserving the exact original user query for context.
"""

import re
from typing import Dict, List, Any, Optional
from pydantic import BaseModel


class PreprocessedQuery(BaseModel):
    original_query: str
    normalized_query: str
    cleaned_text: str
    tokens: List[str]
    abbreviations_mapped: Dict[str, str] = {}


COMMON_ABBREVIATIONS = {
    "wht": "what",
    "wat": "what",
    "abt": "about",
    "profitt": "profit",
    "profiit": "profit",
    "proft": "profit",
    "revnue": "revenue",
    "rev": "revenue",
    "subj": "subject",
    "subjs": "subjects",
    "no of": "count of",
    "num of": "count of",
    "qty": "quantity",
    "avg": "average",
    "tot": "total",
    "sf": "san francisco",
    "la": "los angeles",
    "nyc": "new york",
    "max": "maximum",
    "min": "minimum"
}


class QueryPreprocessor:
    """
    Lightweight, deterministic query preprocessor.
    Prepares normalized query text and tokens for fuzzy candidate matching and LLM context.
    """

    def __init__(self, custom_abbreviations: Optional[Dict[str, str]] = None):
        self.abbrev_map = {**COMMON_ABBREVIATIONS, **(custom_abbreviations or {})}

    def preprocess(self, raw_query: str) -> PreprocessedQuery:
        if not raw_query or not raw_query.strip():
            return PreprocessedQuery(
                original_query="",
                normalized_query="",
                cleaned_text="",
                tokens=[]
            )

        original = raw_query.strip()

        # 1. Normalize repeated punctuation (e.g. "???" -> "?", "!!!" -> "!")
        cleaned = re.sub(r"\?{2,}", "?", original)
        cleaned = re.sub(r"!{2,}", "!", cleaned)

        # 2. Normalize whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # 3. Normalized lowercase representation for token matching
        normalized = cleaned.lower()

        # 4. Abbreviation & common typo mapping
        mapped_abbrevs: Dict[str, str] = {}
        words = normalized.split()
        normalized_words = []

        for word in words:
            clean_w = re.sub(r"[^\w]", "", word)
            if clean_w in self.abbrev_map:
                expanded = self.abbrev_map[clean_w]
                mapped_abbrevs[clean_w] = expanded
                # Replace whole word while preserving punctuation attached to it
                word = re.sub(rf"\b{re.escape(clean_w)}\b", expanded, word)
            normalized_words.append(word)

        normalized_query = " ".join(normalized_words)
        tokens = [re.sub(r"[^\w]", "", w) for w in normalized_words if re.sub(r"[^\w]", "", w)]

        return PreprocessedQuery(
            original_query=original,
            normalized_query=normalized_query,
            cleaned_text=cleaned,
            tokens=tokens,
            abbreviations_mapped=mapped_abbrevs
        )
