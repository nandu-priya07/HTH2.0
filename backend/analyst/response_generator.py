"""
ResponseGenerator module for deterministic answer generation and intent classification.
Formats scalar, aggregate, grouped, ranking, and complex analytical results into structured,
natural language responses matching QueryLens QA requirements without calling a second LLM.
"""

import logging
from typing import Dict, Any, Optional, List
from .models import QueryResult, QuerySpec

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """
    Deterministic response generator and intent classifier for analytical results.
    Bypasses second LLM call for simple, filtered, grouped, ranking, and standard queries.
    """

    @staticmethod
    def generate_response(result: QueryResult, question: str, spec: Optional[QuerySpec] = None) -> str:
        if not result.success:
            err = result.error or "Analysis could not be completed."
            return f"I couldn't complete the request: {err}"

        # 1. GEO_ANALYSIS Result
        if result.metadata and result.metadata.get("analysis_type") == "geographic_analysis":
            return result.text or result.answer or "Geographic analysis completed."

        filters = result.filters_applied or []
        query_plan = (result.metadata or {}).get("query_plan") or {}
        op = ((result.aggregation or query_plan.get("operation") or "SUM").upper())

        # 2. RANKING / TOP_N Query (e.g. "Which state has highest sales?", "Show top 5 states by profit")
        is_ranking_question = any(kw in question.lower() for kw in ("highest", "lowest", "top", "bottom", "best", "worst", "most", "least", "rank"))
        if result.table and is_ranking_question:
            headers = result.table.get("headers", [])
            rows = result.table.get("rows", [])
            if headers and rows:
                dim_name = headers[0]
                val_name = headers[-1]
                top_row = rows[0]
                winner_name = str(top_row[0])
                winner_val = top_row[-1]
                formatted_winner_val = ResponseGenerator._format_val(winner_val, val_name)
                total_groups = (result.metadata or {}).get("groups_total") or len(rows)

                lines = [f"**{winner_name}** has the highest **{val_name}** at **{formatted_winner_val}**."]
                lines.append(f"\n**{total_groups:,}** locations/groups were analyzed.\n")
                lines.append("Top 5:")

                for rank_idx, row in enumerate(rows[:5], 1):
                    g_name = str(row[0])
                    g_val = ResponseGenerator._format_val(row[-1], val_name)
                    lines.append(f"{rank_idx}. {g_name} — {g_val}")

                return "\n".join(lines)

        # 3. GROUPED_RESULT (e.g. "Show the number of orders for each category.")
        if result.table and not result.scalar:
            headers = result.table.get("headers", [])
            rows = result.table.get("rows", [])
            if headers and rows:
                dim_name = headers[0]
                val_name = headers[-1]
                total_groups = len(rows)

                lines = [f"There are **{total_groups:,}** **{dim_name}**s in the dataset.\n"]
                lines.append("Top-level result:")

                for row in rows[:5]:
                    g_name = str(row[0])
                    g_val = ResponseGenerator._format_val(row[-1], val_name)
                    lines.append(f"- {g_name} — {g_val}")

                return "\n".join(lines)

        # 4. FILTERED_AGGREGATION (e.g. "What is the total profit for Technology products in California?")
        if result.scalar and len(filters) > 1:
            metric = result.scalar.get("metric", "value")
            val = result.scalar.get("value", 0)
            formatted_val = ResponseGenerator._format_val(val, metric)

            filter_scope = " and ".join(f"{f.get('column')} = {f.get('value')}" for f in filters if isinstance(f, dict))
            scope_desc = f"from **{filter_scope}**" if filter_scope else ""

            lines = [f"Generated **{formatted_val}** in total **{metric}** {scope_desc}.\n"]
            lines.append("Filters applied:")
            for f in filters:
                if isinstance(f, dict):
                    lines.append(f"- {f.get('column')}: {f.get('value')}")
            lines.append(f"\nRecords analyzed: {result.rows_after_filter or result.rows_before_filter or 0:,}")
            lines.append(f"Metric: {metric.title()}")
            lines.append(f"Aggregation: {op}")
            return "\n".join(lines)

        # 5. SIMPLE_VALUE (e.g. "What is the total profit for California?" or "What is total sales?")
        if result.scalar:
            metric = result.scalar.get("metric", "value")
            val = result.scalar.get("value", 0)
            formatted_val = ResponseGenerator._format_val(val, metric)

            if filters and isinstance(filters[0], dict):
                f0 = filters[0]
                scope_title = f"**{f0.get('value')}** generated **{formatted_val}** in total **{metric}**."
            else:
                scope_title = f"The total **{metric}** is **{formatted_val}**."

            lines = [scope_title, "\nDetails:"]
            if filters and isinstance(filters[0], dict):
                lines.append(f"- {filters[0].get('column', 'Scope').title()}: {filters[0].get('value')}")
            lines.append(f"- Metric: {metric.title()}")
            lines.append(f"- Aggregation: {op}")
            lines.append(f"- Records analyzed: {result.rows_after_filter or result.rows_before_filter or 0:,}")
            return "\n".join(lines)

        return result.text or result.answer or "Analysis complete."

    @staticmethod
    def _format_val(val: Any, metric: str = "") -> str:
        if val is None:
            return "N/A"
        is_currency = any(kw in metric.lower() for kw in ("sales", "profit", "revenue", "amount", "price", "cost", "income", "salary"))
        if isinstance(val, (int, float)):
            if is_currency:
                return f"${val:,.2f}"
            return f"{val:,.2f}" if isinstance(val, float) and not val.is_integer() else f"{int(val):,}"
        return str(val)
