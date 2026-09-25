"""
Data models for the Qwen3 Ollama Query Processor and Analytics Executor.
Supports single-query, multi-query, and multi-column conditional counts.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class QueryOperation(str, Enum):
    SUM = "sum"
    AVERAGE = "average"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    DISTINCT = "distinct"
    MIN = "min"
    MAX = "max"
    CONDITIONAL_COUNT = "conditional_count"
    COLUMN_VALUE_COUNT = "column_value_count"
    COLUMN_VALUE_DISTRIBUTION = "column_value_distribution"
    RECORD_LOOKUP = "record_lookup"
    # New Analytical Intents:
    DATASET_SUMMARY = "dataset_summary"
    AGGREGATION = "aggregation"
    RANKING = "ranking"
    COMPARISON = "comparison"
    TREND = "trend"
    FORECAST = "forecast"
    ANOMALY_DETECTION = "anomaly_detection"
    COMPLEX_INSIGHT = "complex_insight"
    DECISION_ANALYSIS = "decision_analysis"
    GEO_ANALYSIS = "geo_analysis"


class ResponseType(str, Enum):
    DATA_QUERY = "data_query"
    DIRECT_ANSWER = "direct_answer"
    CLARIFICATION = "clarification"
    DATA_RESULT = "data_result"
    ERROR = "error"
    NO_DATA = "no_data"


OPERATOR_MAP: Dict[str, str] = {
    "=": "eq",
    "==": "eq",
    "equals": "eq",
    "equal": "eq",
    "eq": "eq",
    "is": "eq",
    "geographic_equals": "eq",

    "!=": "neq",
    "<>": "neq",
    "not_equals": "neq",
    "not_equal": "neq",
    "neq": "neq",
    "is_not": "neq",

    ">": "gt",
    "gt": "gt",
    "greater_than": "gt",

    ">=": "gte",
    "gte": "gte",
    "greater_than_or_equal": "gte",
    "greater_or_equal": "gte",

    "<": "lt",
    "lt": "lt",
    "less_than": "lt",

    "<=": "lte",
    "lte": "lte",
    "less_than_or_equal": "lte",
    "less_or_equal": "lte",

    "in": "in",
    "is_in": "in",

    "not_in": "not_in",
    "not in": "not_in",

    "contains": "contains",
    "like": "contains",
    "includes": "contains",

    "starts_with": "starts_with",
    "startswith": "starts_with",

    "ends_with": "ends_with",
    "endswith": "ends_with",

    "between": "between",
    "range": "between"
}


def normalize_operator(op: Any) -> str:
    if not op:
        return "eq"
    op_str = str(op).strip().lower()
    return OPERATOR_MAP.get(op_str, op_str)


class ConditionSpec(BaseModel):
    operator: str = "eq"
    value: Any = None

    def model_post_init(self, __context: Any) -> None:
        if self.operator:
            self.operator = normalize_operator(self.operator)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class FilterSpec(BaseModel):
    column: str
    operator: str = "eq"
    value: Any = None

    def model_post_init(self, __context: Any) -> None:
        if self.operator:
            self.operator = normalize_operator(self.operator)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class SortSpec(BaseModel):
    column: str
    direction: str = "desc"

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class DerivedMetricSpec(BaseModel):
    name: str
    formula: Optional[str] = None
    kind: str = "expression"
    operator: Optional[str] = None
    operands: List[str] = Field(default_factory=list)
    source_column: Optional[str] = None
    required_columns: List[str] = Field(default_factory=list)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class QuerySpec(BaseModel):
    """
    Structured query representation produced by fast-path router or Qwen3.
    Supports single column, multi-column, grouping, analytical intents, and forecasting.
    """
    operation: str = "count"
    column: Optional[str] = None
    columns: List[str] = Field(default_factory=list)
    condition: Optional[ConditionSpec] = None
    group_by: List[str] = Field(default_factory=list)
    filters: List[FilterSpec] = Field(default_factory=list)
    sort: List[SortSpec] = Field(default_factory=list)
    limit: Optional[int] = None
    raw_question: Optional[str] = None
    derived_metric: Optional[Any] = None
    requested_metric: Optional[Any] = None
    metric_mapping: Optional[Any] = None

    # Analytical and Forecasting fields:
    intent: Optional[str] = None
    time_column: Optional[str] = None
    frequency: Optional[str] = None
    horizon: Optional[int] = None
    target_column: Optional[str] = None
    comparison_columns: List[str] = Field(default_factory=list)
    options: List[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if self.columns:
            seen = set()
            dedup = []
            for c in self.columns:
                if c and c not in seen:
                    seen.add(c)
                    dedup.append(c)
            self.columns = dedup
        if self.group_by:
            seen_g = set()
            dedup_g = []
            for g in self.group_by:
                if g and g not in seen_g:
                    seen_g.add(g)
                    dedup_g.append(g)
            self.group_by = dedup_g

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class LLMResponse(BaseModel):
    """
    Structured JSON returned by Qwen3 local Ollama model.
    Supports both single query (query) and multiple queries (queries).
    """
    type: str = "direct_answer"  # 'data_query', 'direct_answer', 'clarification'
    query: Optional[QuerySpec] = None
    queries: List[QuerySpec] = Field(default_factory=list)
    answer: Optional[str] = None
    geo_query: Optional[Dict[str, Any]] = None
    timing: Optional[Dict[str, Any]] = None

    @property
    def primary_query(self) -> Optional[QuerySpec]:
        """Returns the primary query or first query in queries list."""
        return self.query or (self.queries[0] if self.queries else None)

    @property
    def all_queries(self) -> List[QuerySpec]:
        """Returns normalized list of all QuerySpecs in this response."""
        if self.queries:
            return self.queries
        if self.query:
            return [self.query]
        return []

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class QueryResult(BaseModel):
    """
    Result returned by the Query Executor after pandas/analytical execution.
    """
    success: bool = True
    type: str = "data_result"
    query: Optional[Dict[str, Any]] = None
    queries: Optional[List[Dict[str, Any]]] = None
    result: Any = None
    results: Optional[List[Any]] = None
    table: Optional[Dict[str, Any]] = None
    tables: Optional[List[Dict[str, Any]]] = None
    scalar: Optional[Dict[str, Any]] = None
    scalars: Optional[List[Dict[str, Any]]] = None
    list: Optional[Dict[str, Any]] = None
    answer: Optional[str] = None
    text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status: Optional[str] = None
    fields_used: Optional[List[str]] = None
    derived_metric: Optional[Any] = None
    filters_applied: Optional[List[Any]] = None
    rows_before_filter: Optional[int] = None
    rows_after_filter: Optional[int] = None
    aggregation: Optional[str] = None
    group_by: Optional[List[str]] = None
    calculation_steps: Optional[List[str]] = None

    # Analytical Reasoning & Engines attributes:
    canonical_data: Optional[Dict[str, Any]] = None
    reasoning: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None
    forecast_data: Optional[Dict[str, Any]] = None
    anomaly_data: Optional[Dict[str, Any]] = None
    summary_data: Optional[Dict[str, Any]] = None
    trend_data: Optional[Dict[str, Any]] = None
    decision_data: Optional[Dict[str, Any]] = None
    comparison_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

