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
0. Geographic questions are still data queries. If the user asks to rank, compare, aggregate, or detect anomalies by a geographic field, include a "geo_query" object in the same response: {"analysis_type":"geographic_analysis","intent":"ranking|group_comparison|anomaly","geographic_dimension":"exact dataset column","metric":{"type":"existing_column|derived","column":"exact numeric column or concept","aggregation":"sum|average|count_distinct"},"comparison":{"direction":"highest|lowest"},"filters":[{"column":"exact dataset column","operator":"=|in|continent","value":"value or list"}],"limit":integer|null}. Use prior conversation analysis to retain metric, geography, and filters in follow-ups. If asked why a location matters, return its value as "selected_location" and use calculated evidence only. Use schema and sample values to pick geography; do not invent columns. For derived metrics, propose only a metric name; backend validates registry formulas. For anomaly requests set intent="anomaly". Add geo_query only for geographic analytical requests. Still provide a valid ordinary queries plan where possible.
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


SUMMARY_SYSTEM_PROMPT = """You rewrite a deterministic analytical answer for clarity using only the supplied verified facts and draft.
Do not calculate, infer causality, add recommendations, or introduce facts. Preserve the headline figure from the draft.
Return exactly one JSON object with this shape: {\"answer\": \"concise answer\"}.
"""


def build_summary_prompt(question: str, facts: Dict[str, Any], draft: str) -> str:
    """Build a bounded, explicit prompt for fact-checked answer polishing."""
    import json

    return (
        "USER QUESTION:\n" + str(question) +
        "\n\nVERIFIED FACTS (JSON):\n" + json.dumps(facts, ensure_ascii=False, default=str) +
        "\n\nDETERMINISTIC DRAFT:\n" + str(draft) +
        "\n\nRewrite the draft concisely. Output JSON only."
    )


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


def build_user_prompt(question: str, dataset_context: str, conversation_context: Optional[Dict[str, Any]] = None) -> str:
    """Combines user question and dataset context for the LLM."""
    prior = f"\n### PRIOR CONVERSATION ANALYSIS (use for follow-ups; preserve metric/geography unless user changes them):\n{conversation_context}\n" if conversation_context else ""
    return f"""{dataset_context}
{prior}

### USER QUESTION:
"{question}"
"""
