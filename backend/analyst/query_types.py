"""
Structured query representation and data models for query processing and analytics execution.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class QueryStatus(str, Enum):
    VALID = "VALID"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    IRRELEVANT = "IRRELEVANT"
    CONVERSATIONAL = "CONVERSATIONAL"
    NO_DATASET = "NO_DATASET"
    INVALID = "INVALID"


class QueryOperation(str, Enum):
    AGGREGATION = "aggregation"
    GROUP_BY = "group_by"
    FILTER = "filter"
    COMPARISON = "comparison"
    TREND = "trend"
    COUNT = "count"
    DISTINCT = "distinct"
    COUNT_DISTINCT = "count_distinct"
    DETAIL = "detail"


class AggregationType(str, Enum):
    SUM = "sum"
    MEAN = "mean"
    AVERAGE = "average"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    MEDIAN = "median"


class FilterOperator(str, Enum):
    EQUALS = "="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"


class TimeGranularity(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class FilterSpec(BaseModel):
    column: str
    operator: str
    value: Any

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class SortSpec(BaseModel):
    column: str
    direction: str = "desc"

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class QueryErrorDetails(BaseModel):
    code: str
    message: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class QuerySpec(BaseModel):
    status: Union[QueryStatus, str] = QueryStatus.VALID
    operation: Optional[str] = None
    column: Optional[str] = None
    metric: Optional[str] = None
    aggregation: Optional[str] = None
    group_by: List[str] = Field(default_factory=list)
    filters: List[Union[FilterSpec, Dict[str, Any]]] = Field(default_factory=list)
    sort: List[Union[SortSpec, Dict[str, Any]]] = Field(default_factory=list)
    limit: Optional[int] = None
    time_dimension: Optional[str] = None
    time_granularity: Optional[str] = None
    time_range: Optional[Dict[str, Any]] = None

    # Clarification / conversational / irrelevant / error metadata
    reason: Optional[str] = None
    detected_column: Optional[str] = None
    options: Optional[List[str]] = None
    message: Optional[str] = None
    error: Optional[Union[QueryErrorDetails, Dict[str, Any]]] = None

    # Extra metadata
    confidence: Optional[float] = None
    raw_question: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class ResultType(str, Enum):
    SCALAR = "scalar"
    TABLE = "table"
    LIST = "list"
    SERIES = "series"
    DETAIL = "detail"
    ERROR = "error"


class QueryResult(BaseModel):
    success: bool
    result_type: str
    column: Optional[str] = None
    value: Optional[Any] = None
    values: Optional[List[Any]] = None
    count: Optional[int] = None
    columns: Optional[List[str]] = None
    rows: Optional[List[List[Any]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)

    def to_dataframe(self) -> Any:
        import pandas as pd
        if self.result_type == "scalar":
            return pd.DataFrame({"value": [self.value]})
        if self.result_type == "list":
            col_name = self.column or "value"
            return pd.DataFrame({col_name: self.values or []})
        if self.rows is not None and self.columns is not None:
            return pd.DataFrame(self.rows, columns=self.columns)
        return pd.DataFrame()

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)
