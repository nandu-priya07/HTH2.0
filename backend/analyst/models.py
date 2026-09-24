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


class ResponseType(str, Enum):
    DATA_QUERY = "data_query"
    DIRECT_ANSWER = "direct_answer"
    CLARIFICATION = "clarification"
    DATA_RESULT = "data_result"
    ERROR = "error"


class ConditionSpec(BaseModel):
    operator: str = "equals"  # "equals", "=", "!=", ">", ">=", "<", "<=", "contains", "in"
    value: Any = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class FilterSpec(BaseModel):
    column: str
    operator: str = "="
    value: Any = None

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


class QuerySpec(BaseModel):
    """
    Structured query representation produced by Qwen3.
    Supports single column, multi-column (e.g. conditional_count), and grouping.
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
    Result returned by the Query Executor after Pandas calculation.
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

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
