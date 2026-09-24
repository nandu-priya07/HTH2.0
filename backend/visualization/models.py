"""
Data models for the Visualization Layer.
Defines supported visualization types and configuration metadata.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class VisualizationType(str, Enum):
    KPI = "kpi"
    BAR = "bar"
    HORIZONTAL_BAR = "horizontal_bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    TABLE = "table"


class VisualizationConfig(BaseModel):
    """
    Standardized visualization configuration sent to the frontend.
    Supports explicit types, user-choice prompts, and automatic selection.
    """
    type: Optional[str] = None  # "kpi", "bar", "horizontal_bar", "line", "pie", "scatter", "table", or None
    visualization_type: Optional[str] = None  # mirror of type / explicit metadata
    visualization_required: bool = False
    visualization_source: Optional[str] = "default"  # "user_requested" | "user_not_specified" | "automatic" | "default"
    requires_user_choice: bool = False
    available_types: List[str] = Field(default_factory=list)
    message: Optional[str] = None
    title: str = "Visualization"
    x_key: Optional[str] = None
    y_key: Optional[str] = None
    value_key: Optional[str] = None
    value: Optional[Union[float, int, str]] = None
    label_key: Optional[str] = None
    orientation: Optional[str] = "vertical"  # "vertical" | "horizontal"
    data: List[Dict[str, Any]] = Field(default_factory=list)
    description: Optional[str] = None
    format: Optional[str] = "number"  # "currency", "number", "percentage", "string"
    data_source: Optional[str] = None
    headers: Optional[List[str]] = None
    rows: Optional[List[List[Any]]] = None
    options: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = self.model_dump()
        clean: Dict[str, Any] = {}
        for k, v in d.items():
            if v is not None:
                clean[k] = v
            elif k in ("visualization_type", "type") and self.requires_user_choice:
                clean[k] = None
        return clean

