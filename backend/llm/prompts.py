"""
Prompt templates and dataset context builders for Qwen3:8b local Ollama routing.
Supports single-query, multi-query, and multi-column conditional count planning.
"""

from typing import Any, Dict, List, Optional
import pandas as pd

SYSTEM_PROMPT = """You are an intelligent dataset query router and analytical query planner.

You receive:
1. User question
2. Dataset schema and column names
3. Column semantic types and data types
4. Dataset metadata (row count, column count)
5. Representative sample values and top records

Your job is to determine whether the user requires:
- a dataset query ("data_query"): when the user asks for calculation, aggregation, conditional counting, filtering, grouping, sorting, or multi-query metrics from the dataset.
- a direct answer ("direct_answer"): for general conversational questions (e.g. "Hello", "What can you do?", "What is a database?") or conceptual explanations (e.g. "What is profit?").
- a clarification ("clarification"): when the query is ambiguous, missing an operation (e.g. "sales?"), or refers to non-existent columns.

Output Requirements:
You must output a single JSON object with no markdown formatting or conversational filler:

1. For Data Queries (Single or Multi-Query):
{
  "type": "data_query",
  "queries": [
    {
      "operation": "sum" | "average" | "count" | "count_distinct" | "distinct" | "min" | "max" | "conditional_count",
      "column": "exact_column_name_from_dataset" | null,
      "columns": ["col1", "col2", "col3"] | [],
      "condition": {
        "operator": "equals" | "!=" | ">" | ">=" | "<" | "<=" | "contains",
        "value": "string or number"
      } | null,
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
    }
  ],
  "answer": null
}

2. For Direct Answers:
{
  "type": "direct_answer",
  "queries": [],
  "answer": "Helpful direct response to conversational or conceptual question."
}

3. For Clarification:
{
  "type": "clarification",
  "queries": [],
  "answer": "Clarification prompt explaining ambiguity or asking for clarification."
}

Critical Query Planning Rules:
1. Multiple Queries / Multi-Operation Requests:
   - A user request may contain one or multiple analytical operations.
   - Never assume that a request produces only one result.
   - Example: "What is the total profit and average profit?" -> return 2 queries: [{"operation": "sum", "column": "profit"}, {"operation": "average", "column": "profit"}].
   - Example: "Give me total sales, average sales, and unique customers" -> return 3 queries: [{"operation": "sum", "column": "sales"}, {"operation": "average", "column": "sales"}, {"operation": "count_distinct", "column": "customer_id"}].

2. "Each / Every / All" & Multi-Column Conditional Counts:
   - When the user asks for a condition across "each subject", "every subject", "all subjects", "each column", or "each subject code" (e.g. "list the A grade count in each subject code"):
     -> Determine the COMPLETE SET of relevant columns from the supplied schema and sample values (e.g. all subject code columns containing grade values like A, B, C, etc.).
     -> Use operation: "conditional_count", columns: [list of all relevant columns], condition: {"operator": "equals", "value": "A"}.
     -> NEVER arbitrarily choose only one column. Include ALL relevant columns in "columns".

3. Distinct vs Count Distinct:
   - "list unique X", "show distinct X", "what are unique X" -> operation: "distinct", column: "X" (returns distinct values).
   - "how many unique X", "count unique X", "number of distinct X" -> operation: "count_distinct", column: "X" (returns scalar count).
   - NEVER convert "distinct" into "sum".

4. Group By & Top N:
   - "show sales by region" -> operation: "sum", column: "sales", group_by: ["region"].
   - "top 5 products by profit" -> operation: "sum", column: "profit", group_by: ["product_name"], limit: 5, sort: [{"column": "profit", "direction": "desc"}].

5. No Hallucinated Columns:
   - ONLY use column names that exist in the provided dataset columns list.
   - If a requested column does not exist in the dataset, return type: "clarification" with answer: "I couldn't find a matching column in the current dataset."

6. Ambiguity vs Clarification:
   - "count students who got A in every subject" refers to records satisfying A across all subjects simultaneously. If ambiguous or not a simple per-subject count, return type: "clarification" asking if the user wants per-subject counts or students passing all subjects.

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
    - Sample values for columns
    - Representative sample rows (top 3 rows)
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
            unique_samples = [str(v) for v in df[col].dropna().unique()[:6] if str(v).strip()]
            if unique_samples:
                lines.append(f"{col}: {', '.join(unique_samples)}")
    elif profile and "columns" in profile:
        for c_name, c_info in profile["columns"].items():
            samples = c_info.get("sample_values") or c_info.get("top_values") or []
            if samples:
                lines.append(f"{c_name}: {', '.join(str(s) for s in samples[:6])}")

    lines.append("")
    lines.append("### SAMPLE ROWS (Top 3)")
    if df is not None and len(df) > 0:
        sample_df = df.head(3)
        lines.append(sample_df.to_string(index=False, max_cols=14))

    return "\n".join(lines)


def build_user_prompt(question: str, dataset_context: str) -> str:
    """Combines user question and dataset context for the LLM."""
    return f"""{dataset_context}

### USER QUESTION:
"{question}"
"""
