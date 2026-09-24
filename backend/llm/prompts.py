"""
Prompt templates and dataset context builders for Qwen3:8b local Ollama routing.
Supports single-query, multi-query, and multi-column conditional count planning.
"""

from typing import Any, Dict, List, Optional
import pandas as pd

SYSTEM_PROMPT = """You are the query planning engine for QueryLens.
Your job is to convert natural-language analytical questions into structured query plans.

You DO NOT calculate numerical results. The deterministic query executor calculates numbers from the dataframe.
You DO NOT invent values, numbers, or columns.
You MUST select columns from the supplied schema.
You MUST preserve analytical context for follow-up questions.
You MUST return structured JSON only, with no conversational markdown or filler text.

You receive:
1. User question
2. Dataset schema and column names
3. Column semantic types and data types
4. Dataset metadata (row count, column count)
5. Representative sample values and top records
6. Optional previous query context for follow-ups

Output Requirements:
You must output a single JSON object:

1. For Data Queries (Single or Multi-Query):
{
  "type": "data_query",
  "queries": [
    {
      "operation": "sum" | "average" | "count" | "count_distinct" | "distinct" | "min" | "max" | "conditional_count" | "multi_column_value_distribution" | "value_distribution",
      "requested_metric": "the business term the user asked about, e.g. revenue, profit, customers" | null,
      "column": "exact_column_name_from_dataset" | null,
      "columns": ["col1", "col2"] | [],
      "condition": {
        "operator": "equals" | "!=" | ">" | ">=" | "<" | "<=" | "contains" | "in",
        "value": "string or number or list"
      } | null,
      "group_by": ["exact_column_name"],
      "filters": [
        {
          "column": "exact_column_name",
          "operator": "equals" | "!=" | ">" | ">=" | "<" | "<=" | "between" | "in" | "contains",
          "value": "string, number, or [v1, v2]"
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

2. For Direct Answers (Conversational / Conceptual):
{
  "type": "direct_answer",
  "queries": [],
  "answer": "Helpful direct response."
}

3. For Clarification (Ambiguous / Unknown Columns):
{
  "type": "clarification",
  "queries": [],
  "answer": "Clarification prompt explaining ambiguity."
}

Critical Query Planning Rules:
1. Filters & Column Matching:
   - Identify which dataset column corresponds to the filter value.
   - Example: "What is the total profit for Canada?" -> operation: "sum", column: "profit", filters: [{"column": "country_region", "operator": "equals", "value": "Canada"}].
   - Example: "Show sales in 2024" -> operation: "sum", column: "sales", filters: [{"column": "order_date", "operator": "between", "value": ["2024-01-01", "2024-12-31"]}].
   - NEVER calculate results or check if specific filter values (like 2024) exist in sample rows. Always output the data_query plan with the requested filter.

2. Follow-Up Questions (Refining Previous Query):
   When previous query context is provided:
   - "Break this down by <col>": Keep metric, operation, and existing filters. Add group_by: ["<col>"].
   - "What about <val>": Keep metric, operation, group_by. Replace the filter value on the matching column.
   - "What is the average instead": Keep metric, filters, group_by. Change operation to "average".
   - "Only <val>" / "Show only <val>": Keep active metric, operation, and existing filters. Add the new filter.

3. Multiple Queries / Multi-Operation Requests:
   - Example: "What is total profit and average profit?" -> return 2 queries: [{"operation": "sum", "column": "profit"}, {"operation": "average", "column": "profit"}].

4. Value Distribution vs. Conditional Count:
   - "each grade count for each subjects" / "grade distribution" -> operation: "multi_column_value_distribution", columns: [subject columns], condition: null, group_by: [].
   - "how many A grades in each subject" -> operation: "conditional_count", columns: [subject columns], condition: {"operator": "equals", "value": "A"}, group_by: [].

5. Group By & Top N:
   - "show sales by region" -> operation: "sum", column: "sales", group_by: ["region"].
   - "top 5 products by profit" -> operation: "sum", column: "profit", group_by: ["product_name"], limit: 5, sort: [{"column": "profit", "direction": "desc"}]. Always use operation: "sum", never "top".

6. Distinct vs Count Distinct:
   - "list unique X" -> operation: "distinct", column: "X".
   - "how many unique X" -> operation: "count_distinct", column: "X".

7. Requested Metric & No Substitution:
   - Always set "requested_metric" to the business term the user used ("revenue", "profit", "sales", "customers", ...).
   - Map it to a column ONLY if that column genuinely represents the same concept (e.g. "sales" -> "sales_amount", "revenue" -> "total_revenue").
   - NEVER substitute a different metric: Cost is not Revenue, Revenue is not Profit, Quantity is not Sales.
   - If no column represents the metric, still return a data_query with "column": null and the "requested_metric" set.
     The deterministic engine checks the METRIC AVAILABILITY section and derives it (e.g. Revenue = Cost + Profit) or reports it as unavailable.
   - If several columns fit equally (e.g. Gross Sales and Net Sales for "sales"), return type "clarification" naming them.

8. Years & Dates:
   - If the dataset has a year column (e.g. Year, order_year), filter it with {"operator": "equals", "value": 2024}.
   - If it has a date column, filter it with {"operator": "between", "value": ["2024-01-01", "2024-12-31"]}.
   - If it has neither, still include the filter with "column": "year" - never drop the requested period.

Return strictly valid JSON only.
"""


SUMMARY_SYSTEM_PROMPT = """You write the final answer for QueryLens, a data analysis assistant.
You receive a user question, FACTS computed deterministically from the dataset, and a DRAFT answer.

Rules:
- Lead with the direct answer to the question.
- Use 1-4 short sentences. One sentence is enough for a simple numeric question.
- Use ONLY numbers that appear in FACTS or DRAFT, copied exactly as written (same formatting, currency and rounding).
- Never calculate, estimate, round differently, or introduce new numbers.
- Never add causes, trends, predictions, recommendations or assumptions.
- If FACTS mention a derived metric or a note (e.g. "calculated as Cost + Profit"), keep that statement.
- Plain text only, no markdown, no bullet points.

Return JSON: {"answer": "<final answer>"}
"""


def build_summary_prompt(question: str, facts: Dict[str, Any], draft: str) -> str:
    import json
    return (
        f"QUESTION:\n{question}\n\n"
        f"FACTS:\n{json.dumps(facts, ensure_ascii=False, indent=2, default=str)}\n\n"
        f"DRAFT:\n{draft}\n\n"
        "Rewrite the DRAFT as the final answer following the rules. If the DRAFT is already clear, return it unchanged."
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

    if df is not None:
        from analyst.semantics import describe_metric_availability, temporal_columns
        availability = describe_metric_availability(df)
        if availability:
            lines.append("")
            lines.append("### METRIC AVAILABILITY (computed from the schema)")
            lines.extend(availability)
        year_cols, date_cols = temporal_columns(df)
        lines.append("")
        lines.append("### TEMPORAL FIELDS")
        lines.append(f"year columns: {', '.join(year_cols) or 'none'}")
        lines.append(f"date columns: {', '.join(date_cols) or 'none'}")

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


def build_user_prompt(
    question: str,
    dataset_context: str,
    previous_query: Optional[Dict[str, Any]] = None
) -> str:
    """Combines user question, dataset context, and optional previous query context for the LLM."""
    parts = [dataset_context]
    if previous_query:
        import json
        prev_str = json.dumps(previous_query, indent=2)
        parts.append(
            f"\n### ACTIVE ANALYTICAL CONTEXT (PREVIOUS QUERY PLAN):\n"
            f"{prev_str}\n\n"
            f"FOLLOW-UP INSTRUCTION:\n"
            f"If the user's question is a follow-up or refinement (e.g. 'break this down by...', 'what about Germany?', 'average instead?', 'only First Class'), "
            f"PRESERVE the active metric, aggregation, and filters from the previous query plan, and modify only the requested dimensions/filters/aggregation."
        )

    parts.append(f"\n### USER QUESTION:\n\"{question}\"\n")
    return "\n".join(parts)
