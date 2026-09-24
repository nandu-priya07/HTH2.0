"""
Prompt templates and dataset context builders for Qwen3:8b local Ollama routing.
"""

from typing import Any, Dict, List, Optional
import pandas as pd

SYSTEM_PROMPT = """You are an intelligent dataset query router and SQL/Pandas query planner.

You receive:
1. User question
2. Dataset schema and column types
3. Dataset metadata (row count, column count)
4. Representative sample values and sample records

Your job is to determine whether the user requires:
- a dataset query ("data_query"): when the user asks for calculation, aggregation, filtering, grouping, sorting, or retrieving records from the dataset.
- a direct answer ("direct_answer"): for general conversational questions (e.g. "Hello", "What can you do?", "What is a database?") or conceptual questions (e.g. "What is profit?").
- a clarification ("clarification"): when the query is ambiguous (e.g. multiple matching columns), missing an operation (e.g. "sales?"), or refers to a column not in the dataset.

Output Requirements:
You must output a single JSON object with no markdown formatting or commentary:

1. For Data Queries:
{
  "type": "data_query",
  "query": {
    "operation": "sum" | "average" | "count" | "count_distinct" | "distinct" | "min" | "max",
    "column": "exact_column_name_from_dataset" | null,
    "group_by": ["exact_column_name"],
    "filters": [
      {
        "column": "exact_column_name",
        "operator": "=" | "!=" | ">" | ">=" | "<" | "<=" | "between" | "in" | "contains",
        "value": "string, number, or [val1, val2] for between"
      }
    ],
    "sort": [
      {"column": "exact_column_name", "direction": "asc" | "desc"}
    ],
    "limit": integer | null
  },
  "answer": null
}

2. For Direct Answers:
{
  "type": "direct_answer",
  "query": null,
  "answer": "Helpful direct response to the user's conversational or conceptual question."
}

3. For Clarification:
{
  "type": "clarification",
  "query": null,
  "answer": "Clarification prompt asking the user which column or operation they intended."
}

Critical Rules:
1. Supported Operations: "sum", "average", "count", "count_distinct", "distinct", "min", "max".
2. Distinct vs Count Distinct:
   - "list unique X", "show distinct X", "what are unique X" -> operation: "distinct", column: "X" (returns distinct values).
   - "how many unique X", "count unique X", "number of distinct X" -> operation: "count_distinct", column: "X" (returns scalar count).
   - NEVER convert "distinct" into "sum".
3. Group By & Top N:
   - "show sales by region" -> operation: "sum", column: "sales", group_by: ["region"].
   - "top 5 products by profit" -> operation: "sum", column: "profit", group_by: ["product_name" or "product_id"], limit: 5, sort: [{"column": "profit", "direction": "desc"}].
4. Filters:
   - "sales in 2024" -> operation: "sum", column: "sales", filters: [{"column": "order_date", "operator": "between", "value": ["2024-01-01", "2024-12-31"]}].
   - "total sales for Technology" -> operation: "sum", column: "sales", filters: [{"column": "category", "operator": "=", "value": "Technology"}].
5. No Hallucinated Columns:
   - ONLY use column names that exist in the provided dataset columns list.
   - If a requested column does not exist in the dataset, return type: "clarification" with answer: "I couldn't find a matching column in the current dataset."
6. Ambiguous Columns:
   - If the user asks something ambiguous (e.g. "show locations" when country_region, state_province, city exist), return type: "clarification" with answer: "Which location field would you like to use: country_region, state_province, or city?"
7. Missing Operation:
   - Never silently default to "sum".
   - For incomplete queries like "sales?", return type: "clarification" with answer: "What would you like to know about sales — total, average, minimum, maximum, or something else?"
8. General Explanations vs Data Queries:
   - "What is profit?" is a general question -> return type: "direct_answer" explaining profit.
   - "What is the total profit?" or "What is our profit?" is a dataset query -> return type: "data_query".

Return strictly valid JSON only.
"""


def build_dataset_context(
    schema: Optional[Dict[str, Any]],
    profile: Optional[Dict[str, Any]],
    df: Optional[pd.DataFrame],
    dataset_id: Optional[str] = None
) -> str:
    """
    Constructs compact, informative dataset context for Qwen3:8b:
    - Dataset info (dataset_id, row_count, column_count)
    - Column info (name, semantic_type, data_type, nullable, unique_count)
    - Sample values for categorical / date columns
    - Representative sample rows (3 rows)
    """
    lines = []
    lines.append("### DATASET INFORMATION")
    ds_name = dataset_id or "active_dataset"
    row_count = len(df) if df is not None else (profile.get("row_count", "unknown") if profile else "unknown")
    col_count = len(df.columns) if df is not None else (profile.get("column_count", len(schema.get("columns", []))) if profile and schema else "unknown")
    lines.append(f"dataset_id: {ds_name}")
    lines.append(f"row_count: {row_count}")
    lines.append(f"column_count: {col_count}")
    lines.append("")

    lines.append("### COLUMNS INFORMATION")
    # Build column metadata
    col_entries = []
    if df is not None:
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            nullable = bool(df[col].isna().any())
            unique_cnt = int(df[col].nunique())
            if pd.api.types.is_numeric_dtype(df[col]):
                sem = "numeric"
            elif pd.api.types.is_datetime64_any_dtype(df[col]) or "date" in str(col).lower():
                sem = "date"
            elif pd.api.types.is_bool_dtype(df[col]):
                sem = "boolean"
            elif "_id" in str(col).lower() or str(col).lower().endswith("id"):
                sem = "identifier"
            else:
                sem = "categorical"

            # Check sample profile if available
            col_entries.append({
                "name": str(col),
                "semantic_type": sem,
                "data_type": dtype_str,
                "nullable": nullable,
                "unique_count": unique_cnt
            })
            lines.append(f"- {col}: semantic_type={sem}, data_type={dtype_str}, nullable={nullable}, unique_count={unique_cnt}")

    elif schema and "columns" in schema:
        for c in schema["columns"]:
            c_name = c.get("name", "")
            sem = c.get("semantic_type", "categorical")
            dtype_str = c.get("dtype", "object")
            nullable = c.get("nullable", True)
            unique_cnt = "unknown"
            if profile and "columns" in profile and c_name in profile["columns"]:
                unique_cnt = profile["columns"][c_name].get("unique_count", "unknown")
            lines.append(f"- {c_name}: semantic_type={sem}, data_type={dtype_str}, nullable={nullable}, unique_count={unique_cnt}")

    lines.append("")
    lines.append("### SAMPLE VALUES")
    if df is not None:
        for col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                unique_samples = [str(v) for v in df[col].dropna().unique()[:4] if str(v).strip()]
                if unique_samples:
                    lines.append(f"{col}: {', '.join(unique_samples)}")
    elif profile and "columns" in profile:
        for c_name, c_info in profile["columns"].items():
            samples = c_info.get("sample_values") or c_info.get("top_values") or []
            if samples:
                lines.append(f"{c_name}: {', '.join(str(s) for s in samples[:4])}")

    lines.append("")
    lines.append("### SAMPLE ROWS (Top 3)")
    if df is not None and len(df) > 0:
        sample_df = df.head(3)
        lines.append(sample_df.to_string(index=False, max_cols=12))

    return "\n".join(lines)


def build_user_prompt(question: str, dataset_context: str) -> str:
    """Combines user question and dataset context for the LLM."""
    return f"""{dataset_context}

### USER QUESTION:
"{question}"
"""
