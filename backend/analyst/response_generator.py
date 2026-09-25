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

        # 0. Analytical Reasoning & Special Analytical Intents Response Formatting
        reasoning = result.reasoning
        canonical = result.canonical_data or {}
        intent = canonical.get("intent") or (result.query.get("intent") if isinstance(result.query, dict) else None)

        if intent == "forecast" or result.forecast_data:
            fc_data = result.forecast_data or canonical
            metric = fc_data.get("metric", "metric")
            fc_list = fc_data.get("forecast", [])
            model = fc_data.get("model", "Statistical Model")
            conf = fc_data.get("confidence", "Moderate")

            lines = [f"### Forecast for {metric.title()}\n"]
            lines.append(f"Model: **{model}** (Confidence: **{conf}**)\n")
            for item in fc_list:
                lines.append(f"- **{item['period']}**: **${item['predicted']:,.2f}** (Range: ${item['lower']:,.2f} – ${item['upper']:,.2f})")

            if reasoning:
                lines.append("\n### Interpretation")
                lines.append(reasoning.get("summary") or reasoning.get("forecast_interpretation") or "")
                if reasoning.get("trend"):
                    lines.append(f"\n**Trend Pattern:** {reasoning.get('trend')}")
                if reasoning.get("uncertainty"):
                    lines.append(f"\n**Uncertainty & Bounds:** {reasoning.get('uncertainty')}")
                if reasoning.get("limitations"):
                    lines.append(f"\n**Limitations:** {reasoning.get('limitations')}")

            lines.append(f"\n### Evidence\n- Method: {model}\n- Horizon: {len(fc_list)} period(s)\n- Historical records analyzed: {result.rows_before_filter or 0:,}")
            return "\n".join(lines)

        if intent == "anomaly_detection" or result.anomaly_data:
            anom_data = result.anomaly_data or canonical
            metric = anom_data.get("metric", "metric")
            anom_list = anom_data.get("anomalies", [])

            lines = [f"### Anomaly Detection Results for {metric.title()}\n"]
            if anom_list:
                lines.append(f"Found **{len(anom_list)}** statistical anomalies (|Z-Score| ≥ 2.0):\n")
                for a in anom_list[:5]:
                    lines.append(f"- **{a['period']}**: Actual = **{a['value']:,.2f}** vs Expected = **{a['expected']:,.2f}** (Z-Score: {a['z_score']:+.2f}, Severity: **{a['severity']}**)")
            else:
                lines.append(f"No statistical anomalies detected in **{metric.title()}** (all values within standard 2.0 deviation threshold).\n")

            if reasoning:
                lines.append("\n### Interpretation")
                lines.append(reasoning.get("summary") or "")
                if reasoning.get("key_findings"):
                    lines.append("\n**Key Findings:**")
                    for kf in reasoning["key_findings"]:
                        lines.append(f"- {kf}")

            lines.append(f"\n### Evidence\n- Criteria: {anom_data.get('threshold', 'Z-Score >= 2.0')}\n- Mean Baseline: {anom_data.get('baseline_mean', 0.0):,.2f}")
            return "\n".join(lines)

        if reasoning and isinstance(reasoning, dict):
            lines = []
            if reasoning.get("summary"):
                lines.append(f"### Answer\n{reasoning['summary']}\n")
            if reasoning.get("key_findings"):
                lines.append("### Key Findings")
                for kf in reasoning["key_findings"]:
                    lines.append(f"- {kf}")
                lines.append("")
            if reasoning.get("reasoning"):
                lines.append("### Reasoning & Analysis")
                for r in reasoning["reasoning"]:
                    lines.append(f"- {r}")
                lines.append("")
            if reasoning.get("limitations"):
                lines.append("### Limitations")
                for lim in reasoning["limitations"]:
                    lines.append(f"- {lim}")
                lines.append("")
            if lines:
                return "\n".join(lines)

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

            lines = [scope_title, "\n### How we got this answer\n"]
            lines.append(f"1. Selected the `{metric}` field.")
            lines.append(f"2. Analyzed {result.rows_after_filter or result.rows_before_filter or 0:,} records.")
            if filters:
                filter_strs = [f"{f.get('column')} = {f.get('value')}" for f in filters if isinstance(f, dict)]
                lines.append(f"3. Applied filter: {', '.join(filter_strs)}.")
            else:
                lines.append("3. Applied no filters.")
            lines.append(f"4. Calculated {op}({metric}).")
            lines.append(f"5. Result = **{formatted_val}**.")
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
