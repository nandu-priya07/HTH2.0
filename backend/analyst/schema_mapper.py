"""
Dataset-Agnostic Schema Mapper for Column Resolution.

Resolves natural-language terms and user questions to dataset columns dynamically
using the active dataset schema, normalized matching, token overlap, and semantic types.
Does NOT rely on hardcoded retail or domain-specific assumptions.
"""

import re
import difflib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union


@dataclass
class ColumnMetadata:
    name: str
    original_name: str
    semantic_type: str = "unknown"  # "numeric", "categorical", "date", "identifier", "boolean", "text", "unknown"
    dtype: str = "object"
    normalized_name: str = ""
    tokens: Set[str] = field(default_factory=set)
    sample_values: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.normalized_name:
            self.normalized_name = _normalize_identifier(self.name)
        if not self.tokens:
            self.tokens = set(_tokenize(self.name))


@dataclass
class ColumnCandidate:
    column: ColumnMetadata
    score: float
    match_type: str  # "exact", "normalized", "token_match", "singular_plural", "substring", "fuzzy"


@dataclass
class ColumnResolutionResult:
    resolved: Optional[str] = None
    is_ambiguous: bool = False
    options: List[str] = field(default_factory=list)
    confidence: float = 0.0
    match_type: Optional[str] = None


def _normalize_identifier(name: str) -> str:
    """Normalize column names by converting snake_case, camelCase, kebab-case to space-separated lowercase."""
    s = str(name).strip()
    # Insert space before capital letters for camelCase
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    # Replace separators with spaces
    s = re.sub(r"[-_./]+", " ", s)
    # Remove non-alphanumeric except space
    s = re.sub(r"[^\w\s]", "", s)
    # Lowercase and single space
    return re.sub(r"\s+", " ", s).lower().strip()


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alpha words."""
    norm = _normalize_identifier(text)
    return [w for w in norm.split() if w]


def _singularize_word(word: str) -> str:
    """Safe singularization for common English words without over-stemming."""
    w = word.lower().strip()
    if len(w) <= 2:
        return w
    irregulars = {
        "categories": "category",
        "companies": "company",
        "countries": "country",
        "cities": "city",
        "quantities": "quantity",
        "properties": "property",
        "summaries": "summary",
        "deliveries": "delivery",
        "people": "person",
        "children": "child",
        "indices": "index",
        "matrices": "matrix",
        "statuses": "status",
        "addresses": "address",
        "classes": "class"
    }
    if w in irregulars:
        return irregulars[w]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if (w.endswith("shes") or w.endswith("ches") or w.endswith("sses") or w.endswith("xes")) and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and not w.endswith("us") and not w.endswith("is") and len(w) > 3:
        return w[:-1]
    return w


def _singularize(word: str) -> str:
    """Backward-compatible alias for _singularize_word."""
    return _singularize_word(word)


def _normalize_and_singularize(text: str) -> str:
    """Normalizes and singularizes all tokens in identifier/phrase."""
    tokens = _tokenize(text)
    return " ".join(_singularize_word(t) for t in tokens)


def normalize_schema(
    schema: Optional[Union[Dict[str, Any], List[Any]]],
    profile: Optional[Dict[str, Any]] = None
) -> Dict[str, ColumnMetadata]:
    """
    Normalizes diverse schema representations (file_processing schema, simple dicts, lists)
    into a standardized mapping of {column_name: ColumnMetadata}.
    """
    if schema is None:
        return {}
    if isinstance(schema, (dict, list)) and not schema:
        return {}
    if hasattr(schema, "empty") and schema.empty:
        return {}

    # Extract sample unique values from profile if available
    profile_values_map: Dict[str, List[str]] = {}
    if profile and isinstance(profile, dict):
        for col_p in profile.get("columns_profile", []):
            c_name = col_p.get("column_name") or col_p.get("name")
            if c_name:
                top_vals = [str(item.get("value")) for item in col_p.get("top_frequent_values", []) if item.get("value") is not None]
                profile_values_map[c_name] = top_vals

    # Check if schema is already a Dict[str, ColumnMetadata]
    if isinstance(schema, dict) and schema and all(isinstance(v, ColumnMetadata) for v in schema.values()):
        return schema

    col_meta_map: Dict[str, ColumnMetadata] = {}

    # Case 1: Pandas DataFrame passed directly (backward compatibility)
    if hasattr(schema, "columns") and hasattr(schema, "dtypes"):
        df = schema
        for col in df.columns:
            col_str = str(col)
            dtype_str = str(df[col].dtype)
            # Infer rudimentary semantic type from dtype
            if "int" in dtype_str or "float" in dtype_str:
                sem = "numeric"
            elif "datetime" in dtype_str:
                sem = "date"
            elif "bool" in dtype_str:
                sem = "boolean"
            else:
                sem = "categorical"

            col_meta_map[col_str] = ColumnMetadata(
                name=col_str,
                original_name=col_str,
                semantic_type=sem,
                dtype=dtype_str,
                sample_values=profile_values_map.get(col_str, [])
            )
        return col_meta_map

    # Case 2: Standard file_processing schema dict with "columns" list
    if isinstance(schema, dict) and "columns" in schema and isinstance(schema["columns"], list):
        for item in schema["columns"]:
            if isinstance(item, dict):
                col_name = str(item.get("name", ""))
                if not col_name:
                    continue
                orig_name = str(item.get("original_name", col_name))
                sem_type = str(item.get("semantic_type", "unknown"))
                dtype = str(item.get("dtype", "object"))
                col_meta_map[col_name] = ColumnMetadata(
                    name=col_name,
                    original_name=orig_name,
                    semantic_type=sem_type,
                    dtype=dtype,
                    sample_values=profile_values_map.get(col_name, [])
                )
            elif isinstance(item, str):
                col_meta_map[item] = ColumnMetadata(
                    name=item,
                    original_name=item,
                    semantic_type="unknown",
                    sample_values=profile_values_map.get(item, [])
                )
        return col_meta_map

    # Case 3: Dict of {col_name: semantic_type_or_dict}
    if isinstance(schema, dict):
        for col_key, val in schema.items():
            if col_key in ("row_count", "column_count", "numeric_columns", "categorical_columns", "date_columns", "identifier_columns", "boolean_columns", "text_columns"):
                continue
            col_str = str(col_key)
            if isinstance(val, dict):
                sem_type = str(val.get("semantic_type", "unknown"))
                dtype = str(val.get("dtype", "object"))
            elif isinstance(val, str):
                sem_type = val
                dtype = "object"
            else:
                sem_type = "unknown"
                dtype = "object"
            col_meta_map[col_str] = ColumnMetadata(
                name=col_str,
                original_name=col_str,
                semantic_type=sem_type,
                dtype=dtype,
                sample_values=profile_values_map.get(col_str, [])
            )
        return col_meta_map

    # Case 4: List of column names
    if isinstance(schema, list):
        for item in schema:
            if isinstance(item, str):
                col_meta_map[item] = ColumnMetadata(
                    name=item,
                    original_name=item,
                    semantic_type="unknown",
                    sample_values=profile_values_map.get(item, [])
                )
            elif isinstance(item, dict) and "name" in item:
                col_name = str(item["name"])
                col_meta_map[col_name] = ColumnMetadata(
                    name=col_name,
                    original_name=str(item.get("original_name", col_name)),
                    semantic_type=str(item.get("semantic_type", "unknown")),
                    dtype=str(item.get("dtype", "object")),
                    sample_values=profile_values_map.get(col_name, [])
                )
        return col_meta_map

    return {}


def score_column_match(
    term: str,
    col: ColumnMetadata,
    is_metric: bool = False,
    is_group_by: bool = False,
    is_date: bool = False
) -> Tuple[float, str]:
    """
    Computes a match score [0.0, 1.0] and match type for a term against a column
    following strict priority:
    1. Exact match (1.0)
    2. Normalized exact match (0.98)
    3. Singular/plural normalization match (0.95)
    4. Token subset match (0.85-0.90)
    5. Singularized token subset match (0.82-0.88)
    6. Token match (0.80)
    7. Substring match (0.68-0.80)
    8. Fuzzy similarity (0.65-0.75)
    """
    clean_term = term.strip().lower()
    norm_term = _normalize_identifier(clean_term)
    sing_norm_term = _normalize_and_singularize(clean_term)
    term_tokens = set(_tokenize(clean_term))
    sing_term_tokens = {_singularize_word(t) for t in term_tokens}

    col_name_lower = col.name.strip().lower()
    col_norm = col.normalized_name
    sing_col_norm = _normalize_and_singularize(col.name)
    col_tokens = col.tokens
    sing_col_tokens = {_singularize_word(t) for t in col_tokens}

    score = 0.0
    match_type = "none"

    # 1. Exact match (case-insensitive)
    if clean_term == col_name_lower or clean_term == col.original_name.lower():
        score = 1.0
        match_type = "exact"

    # 2. Normalized match (e.g. "sales amount" == "sales_amount")
    elif norm_term == col_norm:
        score = 0.98
        match_type = "normalized"

    # 3. Singular/Plural equality on whole string (e.g. "country_regions" == "country_region")
    elif sing_norm_term == sing_col_norm:
        score = 0.95
        match_type = "singular_plural"

    # 4. Multi-token full subset match (e.g. "order date" in "customer order date")
    elif term_tokens and term_tokens.issubset(col_tokens):
        coverage = len(term_tokens) / max(len(col_tokens), 1)
        score = 0.85 + (0.06 * coverage)
        match_type = "token_subset"

    # 5. Singularized token subset match
    elif sing_term_tokens and sing_term_tokens.issubset(sing_col_tokens):
        coverage = len(sing_term_tokens) / max(len(sing_col_tokens), 1)
        score = 0.82 + (0.06 * coverage)
        match_type = "token_subset_plural"

    # 6. Single term token match (e.g. "sales" matches "sales_tax")
    elif len(term_tokens) == 1 and list(term_tokens)[0] in col_tokens:
        coverage = 1.0 / max(len(col_tokens), 1)
        score = 0.80 + (0.06 * coverage)
        match_type = "token_match"

    # 7. Single term singular token match
    elif len(sing_term_tokens) == 1 and list(sing_term_tokens)[0] in sing_col_tokens:
        coverage = 1.0 / max(len(sing_col_tokens), 1)
        score = 0.78 + (0.06 * coverage)
        match_type = "token_match_plural"

    # 8. Substring match
    elif norm_term and (norm_term in col_norm or col_norm in norm_term):
        ratio = min(len(norm_term), len(col_norm)) / max(len(norm_term), len(col_norm), 1)
        score = 0.68 + (0.10 * ratio)
        match_type = "substring"

    # 9. Difflib fuzzy similarity
    else:
        ratio = difflib.SequenceMatcher(None, norm_term, col_norm).ratio()
        if ratio >= 0.75:
            score = ratio * 0.75
            match_type = "fuzzy"

    # Apply semantic context adjustments
    if score > 0.60:
        if is_metric:
            if col.semantic_type == "numeric":
                score += 0.03
            elif col.semantic_type in ("identifier", "date"):
                score -= 0.15
        elif is_group_by:
            if col.semantic_type in ("categorical", "text"):
                score += 0.06
                if "name" in col.name.lower() or "desc" in col.name.lower():
                    score += 0.04
            elif col.semantic_type == "identifier":
                score -= 0.04
            elif col.semantic_type == "numeric":
                score -= 0.10
        elif is_date:
            if col.semantic_type == "date":
                score += 0.20
            else:
                score -= 0.40

    return min(max(score, 0.0), 1.0), match_type


def find_candidate_columns(
    term: str,
    schema_map: Dict[str, ColumnMetadata],
    is_metric: bool = False,
    is_group_by: bool = False,
    is_date: bool = False,
    min_score: float = 0.70
) -> List[ColumnCandidate]:
    """Finds and ranks all candidate columns matching a term."""
    candidates: List[ColumnCandidate] = []
    for _, col_meta in schema_map.items():
        score, match_type = score_column_match(
            term=term,
            col=col_meta,
            is_metric=is_metric,
            is_group_by=is_group_by,
            is_date=is_date
        )
        if score >= min_score:
            candidates.append(ColumnCandidate(column=col_meta, score=round(score, 4), match_type=match_type))

    # Sort descending by score
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def resolve_column(
    term: str,
    schema: Optional[Union[Dict[str, Any], List[Any]]] = None,
    is_metric: bool = False,
    is_group_by: bool = False,
    is_date: bool = False,
    profile: Optional[Dict[str, Any]] = None,
    ambiguity_delta: float = 0.12,
    # Backward compatibility arguments
    df: Optional[Any] = None,
    semantic_model: Optional[Any] = None,
    semantic_embeddings: Optional[Any] = None
) -> ColumnResolutionResult:
    """
    Dataset-agnostic column resolver following strict resolution hierarchy:
    1. Exact match
    2. Normalized exact match
    3. Singular/plural normalization
    4. Token match
    5. Substring / Fuzzy
    """
    target_schema = schema if schema is not None else df
    schema_map = normalize_schema(target_schema, profile)

    if not schema_map:
        return ColumnResolutionResult(resolved=None, is_ambiguous=False, options=[])

    clean_term = term.strip().lower()

    # Exact dictionary key match shortcut
    for col_name, meta in schema_map.items():
        if col_name.lower() == clean_term or meta.original_name.lower() == clean_term:
            return ColumnResolutionResult(
                resolved=meta.name,
                is_ambiguous=False,
                confidence=1.0,
                match_type="exact"
            )

    candidates = find_candidate_columns(term, schema_map, is_metric, is_group_by, is_date, min_score=0.70)

    if not candidates:
        return ColumnResolutionResult(resolved=None, is_ambiguous=False, options=[])

    top_1 = candidates[0]

    # Priority Rule: If top candidate is exact, normalized, or singular/plural (Tier 1-3 match),
    # and second candidate is NOT an exact/normalized/singular_plural match (score < 0.94 or match_type not in ("exact", "normalized", "singular_plural")):
    # There is NO ambiguity! Candidate #1 directly wins.
    if top_1.match_type in ("exact", "normalized", "singular_plural") and top_1.score >= 0.94:
        if len(candidates) == 1:
            return ColumnResolutionResult(
                resolved=top_1.column.name,
                is_ambiguous=False,
                confidence=top_1.score,
                match_type=top_1.match_type
            )
        top_2 = candidates[1]
        if top_2.match_type not in ("exact", "normalized", "singular_plural") or top_2.score < 0.94:
            return ColumnResolutionResult(
                resolved=top_1.column.name,
                is_ambiguous=False,
                confidence=top_1.score,
                match_type=top_1.match_type
            )

    if len(candidates) == 1:
        if top_1.score >= 0.72:
            return ColumnResolutionResult(
                resolved=top_1.column.name,
                is_ambiguous=False,
                confidence=top_1.score,
                match_type=top_1.match_type
            )
        return ColumnResolutionResult(resolved=None, is_ambiguous=False, options=[])

    # Multiple candidates: check for ambiguity
    top_2 = candidates[1]

    # Condition 1: Scores are very close (difference < ambiguity_delta)
    score_diff = top_1.score - top_2.score
    is_score_close = score_diff < ambiguity_delta

    # Condition 2: Multiple columns share the query word token
    token_sharing = [c for c in candidates if any(t in c.column.tokens for t in _tokenize(clean_term)) and c.score >= 0.75]
    is_shared_root = len(token_sharing) >= 2 and len(_tokenize(clean_term)) <= 2

    if (is_score_close and top_1.score >= 0.75) or (is_shared_root and score_diff < 0.15):
        # Ambiguous! Return options
        options = [c.column.name for c in candidates if c.score >= (top_1.score - ambiguity_delta - 0.05)]
        return ColumnResolutionResult(
            resolved=None,
            is_ambiguous=True,
            options=options,
            confidence=top_1.score
        )

    # Decisive top candidate
    if top_1.score >= 0.75:
        return ColumnResolutionResult(
            resolved=top_1.column.name,
            is_ambiguous=False,
            confidence=top_1.score,
            match_type=top_1.match_type
        )

    return ColumnResolutionResult(resolved=None, is_ambiguous=False, options=[])


def resolve_group_by(
    group_by: str,
    schema: Optional[Union[Dict[str, Any], List[Any]]] = None,
    profile: Optional[Dict[str, Any]] = None,
    df: Optional[Any] = None,
    semantic_model: Optional[Any] = None,
    semantic_embeddings: Optional[Any] = None
) -> str:
    """
    Resolves group-by dimension against schema. Raises ValueError on ambiguity or missing column
    for backward compatibility with legacy tests.
    """
    res = resolve_column(
        term=group_by,
        schema=schema,
        is_group_by=True,
        profile=profile,
        df=df
    )
    if res.is_ambiguous:
        raise ValueError(f"Ambiguous group_by '{group_by}'. Possible columns: {res.options}")
    if res.resolved:
        return res.resolved
    raise ValueError(f"Could not resolve group_by: {group_by}")


def resolve_metric(
    metric: str,
    schema: Optional[Union[Dict[str, Any], List[Any]]] = None,
    profile: Optional[Dict[str, Any]] = None,
    df: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Resolves metric against schema. Returns dictionary for backward compatibility with query_executor.
    """
    res = resolve_column(
        term=metric,
        schema=schema,
        is_metric=True,
        profile=profile,
        df=df
    )
    if res.is_ambiguous:
        raise ValueError(f"Ambiguous metric '{metric}'. Possible columns: {res.options}")
    if res.resolved:
        return {
            "metric": metric,
            "type": "direct",
            "column": res.resolved,
            "expression": None
        }
    raise ValueError(f"Metric '{metric}' is not available for this dataset.")
