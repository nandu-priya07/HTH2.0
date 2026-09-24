"""
Structured query error definitions and exception classes.
"""

from typing import Any, Dict, Optional


class ErrorCode:
    QUERY_PARSE_ERROR = "QUERY_PARSE_ERROR"
    QUERY_VALIDATION_ERROR = "QUERY_VALIDATION_ERROR"
    COLUMN_NOT_FOUND = "COLUMN_NOT_FOUND"
    AMBIGUOUS_COLUMN = "AMBIGUOUS_COLUMN"
    INVALID_AGGREGATION = "INVALID_AGGREGATION"
    INVALID_FILTER = "INVALID_FILTER"
    INVALID_TIME_OPERATION = "INVALID_TIME_OPERATION"
    INVALID_LIMIT = "INVALID_LIMIT"
    INCOMPATIBLE_METRIC_TYPE = "INCOMPATIBLE_METRIC_TYPE"
    NO_DATASET = "NO_DATASET"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class AnalystError(Exception):
    """Base application exception for Analyst module with structured details."""
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": False,
            "error": {
                "code": self.code,
                "message": self.message
            }
        }
        if self.details:
            result["error"]["details"] = self.details
        return result


class AmbiguousColumnError(AnalystError):
    def __init__(self, term: str, candidates: list[str]):
        super().__init__(
            code=ErrorCode.AMBIGUOUS_COLUMN,
            message=f"I found multiple columns related to '{term}'. Which one do you mean?",
            details={"term": term, "options": candidates}
        )
        self.term = term
        self.candidates = candidates
