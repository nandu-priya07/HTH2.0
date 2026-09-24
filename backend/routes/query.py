"""
API Route for Natural Language Query Processing and Analytics Execution.
Integrates the Analyst module with FastAPI and active datasets.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
import pandas as pd

from analyst import process_query, execute_query, QueryStatus, ResultType
from file_processing.schema_inference import infer_schema
from file_processing.data_profiler import profile_dataset
from routes.upload import DATASET_REGISTRY, BASE_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])

PROCESSED_DIR = BASE_DIR / "uploads" / "processed"


class QueryRequest(BaseModel):
    question: str
    dataset_id: Optional[str] = None


def _get_or_load_dataset(dataset_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves the dataset from memory or loads existing processed dataset from disk.
    """
    # 1. Check if specific dataset_id is in registry
    if dataset_id and dataset_id in DATASET_REGISTRY:
        return DATASET_REGISTRY[dataset_id]

    # 2. If no dataset_id specified, use most recently registered dataset
    if not dataset_id and DATASET_REGISTRY:
        return list(DATASET_REGISTRY.values())[-1]

    # 3. Check disk for processed CSV files if registry is empty
    if PROCESSED_DIR.exists():
        if dataset_id:
            target_csv = PROCESSED_DIR / f"{dataset_id}.csv"
            candidates = [target_csv] if target_csv.exists() else []
        else:
            candidates = sorted(list(PROCESSED_DIR.glob("*.csv")), key=lambda p: p.stat().st_mtime, reverse=True)

        if candidates:
            csv_path = candidates[0]
            ds_id = csv_path.stem
            try:
                df = pd.read_csv(csv_path)
                schema = infer_schema(df)
                profile = profile_dataset(df, schema)
                ds_entry = {
                    "dataset_id": ds_id,
                    "filename": f"{ds_id}.csv",
                    "file_path": str(csv_path),
                    "status": "processed",
                    "data": df,
                    "result": {
                        "dataset_id": ds_id,
                        "schema": schema,
                        "profile": profile,
                        "metadata": {
                            "rows": len(df),
                            "columns": len(df.columns)
                        }
                    }
                }
                DATASET_REGISTRY[ds_id] = ds_entry
                return ds_entry
            except Exception as e:
                logger.error(f"Failed to auto-load processed dataset {csv_path}: {e}")

    return None


def _format_summary_text(spec: Any, result: Any) -> str:
    """Formats human-friendly summary text from QueryResult."""
    if result.result_type == "list":
        col_name = result.column or spec.column or "column"
        count = result.count if result.count is not None else len(result.values or [])
        filter_desc = ""
        if spec.filters:
            f_parts = [f"{f['column'] if isinstance(f, dict) else f.column} {f['operator'] if isinstance(f, dict) else f.operator} {f['value'] if isinstance(f, dict) else f.value}" for f in spec.filters]
            filter_desc = f" (filtered by {', '.join(f_parts)})"
        return f"Found **{count}** unique values for **{col_name}**{filter_desc}:"

    if result.result_type == "scalar":
        val = result.value
        agg = spec.aggregation or "total"
        metric_name = spec.metric or spec.column or "metric"
        if isinstance(val, float):
            formatted_val = f"{val:,.2f}"
        elif isinstance(val, int):
            formatted_val = f"{val:,}"
        else:
            formatted_val = str(val)

        filter_desc = ""
        if spec.filters:
            f_parts = [f"{f['column'] if isinstance(f, dict) else f.column} {f['operator'] if isinstance(f, dict) else f.operator} {f['value'] if isinstance(f, dict) else f.value}" for f in spec.filters]
            filter_desc = f" (filtered by {', '.join(f_parts)})"

        return f"The **{agg}** of **{metric_name}** is **{formatted_val}**{filter_desc}."

    if result.result_type in ("table", "detail"):
        row_count = len(result.rows) if result.rows else 0
        if spec.operation == "trend":
            gran = spec.time_granularity or "period"
            return f"Here is the **{spec.metric}** trend broken down by **{gran}** ({row_count} periods analyzed):"
        if spec.group_by:
            group_str = ", ".join(spec.group_by)
            metric_desc = f"**{spec.metric}**" if spec.metric else "records"
            return f"Breakdown of {metric_desc} grouped by **{group_str}** ({row_count} groups found):"
        return f"Here are the {row_count} matching records based on your question:"

    return "Analysis completed successfully."


@router.post("/query")
async def execute_user_query(payload: QueryRequest):
    """
    Main endpoint for taking natural language questions, executing them against active dataset,
    and returning structured AI analyst results with charts/tables.
    """
    question = payload.question.strip()
    if not question:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "Question cannot be empty"}
        )

    # 1. Retrieve Dataset
    dataset_info = _get_or_load_dataset(payload.dataset_id)
    if not dataset_info:
        spec = process_query(question=question, schema=None)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "status": QueryStatus.NO_DATASET.value,
                "text": "Please upload a CSV or Excel dataset first before asking data-analysis questions. Click the **+** button below to attach a file.",
                "query_spec": spec.to_dict()
            }
        )

    schema = dataset_info["result"]["schema"]
    profile = dataset_info["result"].get("profile")
    df = dataset_info["data"]

    # 2. Process Natural Language Query into QuerySpec
    spec = process_query(question=question, schema=schema, profile=profile)

    # 3. Handle Non-Valid Query Statuses
    if spec.status == QueryStatus.CONVERSATIONAL:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "status": spec.status,
                "text": spec.message or "Hello! I am your AI Data Analyst. Ask me anything about your uploaded dataset.",
                "query_spec": spec.to_dict()
            }
        )

    if spec.status == QueryStatus.IRRELEVANT:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "status": spec.status,
                "text": spec.message or "This question does not appear to be related to the uploaded dataset. Please ask a question related to your data columns.",
                "query_spec": spec.to_dict()
            }
        )

    if spec.status == QueryStatus.NEEDS_CLARIFICATION:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "status": spec.status,
                "reason": spec.reason,
                "text": spec.message,
                "options": spec.options,
                "detected_column": spec.detected_column,
                "time_range": spec.time_range,
                "query_spec": spec.to_dict()
            }
        )

    if spec.status == QueryStatus.INVALID:
        err_msg = spec.error.get("message") if isinstance(spec.error, dict) else (spec.error.message if spec.error else "Invalid query specification.")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": False,
                "status": spec.status,
                "text": f"I couldn't process this query: {err_msg}",
                "error": err_msg,
                "query_spec": spec.to_dict()
            }
        )

    # 4. Execute Valid QuerySpec
    res = execute_query(spec, df)
    if not res.success:
        err_msg = res.error.get("message") if isinstance(res.error, dict) else "Query execution failed."
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": False,
                "status": "EXECUTION_ERROR",
                "text": f"An error occurred while analyzing the dataset: {err_msg}",
                "error": err_msg,
                "query_spec": spec.to_dict()
            }
        )

    # 5. Build Formatted Response
    summary_text = _format_summary_text(spec, res)

    list_data = None
    if res.result_type == ResultType.LIST.value or res.values is not None:
        list_data = {
            "column": res.column or spec.column,
            "values": res.values or [],
            "count": res.count if res.count is not None else len(res.values or [])
        }

    table_data = None
    if res.result_type in (ResultType.TABLE.value, ResultType.DETAIL.value, ResultType.LIST.value):
        table_data = {
            "headers": res.columns or ([res.column] if res.column else ["value"]),
            "rows": res.rows or ([[v] for v in (res.values or [])])
        }

    scalar_data = None
    if res.result_type == ResultType.SCALAR.value:
        scalar_data = {
            "metric": spec.metric or spec.column,
            "aggregation": spec.aggregation or spec.operation,
            "value": res.value
        }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "status": QueryStatus.VALID.value,
            "text": summary_text,
            "result_type": res.result_type,
            "list": list_data,
            "table": table_data,
            "scalar": scalar_data,
            "metadata": res.metadata,
            "query_spec": spec.to_dict(),
            "dataset_id": dataset_info.get("dataset_id")
        }
    )


@router.get("/datasets")
async def list_available_datasets():
    """Lists loaded or available datasets with column metadata."""
    _get_or_load_dataset()  # Auto-load if available
    datasets = []
    for ds_id, info in DATASET_REGISTRY.items():
        res_info = info.get("result", {})
        schema = res_info.get("schema", {})
        cols = [c["name"] for c in schema.get("columns", [])] if "columns" in schema else []
        datasets.append({
            "dataset_id": ds_id,
            "filename": info.get("filename", f"{ds_id}.csv"),
            "rows": res_info.get("metadata", {}).get("rows", len(info.get("data", []))),
            "columns_count": len(cols),
            "columns": cols[:8]
        })
    return {"success": True, "datasets": datasets}


@router.get("/dataset/{dataset_id}/suggestions")
async def get_dynamic_suggestions(dataset_id: str):
    """Generates context-aware recommended questions based on dataset columns."""
    dataset_info = _get_or_load_dataset(dataset_id)
    if not dataset_info:
        return {"success": False, "suggestions": []}

    schema = dataset_info["result"]["schema"]
    num_cols = schema.get("numeric_columns", [])
    cat_cols = schema.get("categorical_columns", [])
    date_cols = schema.get("date_columns", [])

    suggestions = []
    if num_cols and cat_cols:
        suggestions.append(f"What is the total {num_cols[0]} by {cat_cols[0]}?")
        suggestions.append(f"Show the top 5 {cat_cols[0]} by {num_cols[0]}")
    if len(num_cols) > 1 and cat_cols:
        suggestions.append(f"Average {num_cols[1]} by {cat_cols[0]}")
    elif num_cols:
        suggestions.append(f"What is the total {num_cols[0]}?")
        suggestions.append(f"What is the average {num_cols[0]}?")

    if num_cols and date_cols:
        suggestions.append(f"Show {num_cols[0]} trend by month")

    if cat_cols:
        suggestions.append(f"How many records by {cat_cols[0]}?")

    suggestions.append("Give me a summary of the dataset")
    return {"success": True, "suggestions": suggestions[:5]}
