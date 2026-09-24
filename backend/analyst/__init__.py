"""
Antigravity Analyst Package.
Provides dataset-agnostic query processing, schema mapping, validation, and analytics execution.
"""

from .query_types import (
    QuerySpec,
    QueryResult,
    QueryStatus,
    QueryOperation,
    AggregationType,
    FilterOperator,
    TimeGranularity,
    FilterSpec,
    SortSpec,
    QueryErrorDetails,
    ResultType
)

from .query_errors import (
    ErrorCode,
    AnalystError,
    AmbiguousColumnError
)

from .schema_mapper import (
    normalize_schema,
    resolve_column,
    resolve_group_by,
    resolve_metric,
    find_candidate_columns,
    ColumnMetadata,
    ColumnCandidate,
    ColumnResolutionResult
)

from .query_planner import (
    build_query_spec,
    create_query_plan
)

from .query_validator import (
    validate_query,
    validate_query_plan
)

from .question_parser import (
    parse_query,
    parse_question
)

from .query_executor import (
    execute_query,
    load_processed_dataset
)

# High-level pipeline entrypoint
process_query = parse_query

__all__ = [
    "process_query",
    "parse_query",
    "parse_question",
    "validate_query",
    "validate_query_plan",
    "execute_query",
    "load_processed_dataset",
    "build_query_spec",
    "create_query_plan",
    "normalize_schema",
    "resolve_column",
    "resolve_group_by",
    "resolve_metric",
    "QuerySpec",
    "QueryResult",
    "QueryStatus",
    "QueryOperation",
    "AggregationType",
    "FilterOperator",
    "TimeGranularity",
    "FilterSpec",
    "SortSpec",
    "QueryErrorDetails",
    "ResultType",
    "ErrorCode",
    "AnalystError",
    "AmbiguousColumnError",
    "ColumnMetadata",
    "ColumnCandidate",
    "ColumnResolutionResult"
]
