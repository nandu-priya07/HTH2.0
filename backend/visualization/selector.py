"""
Dynamic Visualization Selector module.
Inspects QuerySpec, QueryResult, Dataset Schema, and User Intent to determine visualization(s).
Strictly differentiates:
1. Explicit user visualization request (e.g. "using pie chart", "as a bar chart") -> user_requested
2. No visualization type specified (e.g. "visualize the A grade count for each subject") -> user_not_specified (requires_user_choice = True)
3. Explicit "choose automatically" request (e.g. "choose the best chart") -> automatic
4. Standard analytical queries without visualization requests -> default presentation
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import re
import pandas as pd

from analyst.models import QuerySpec, QueryResult
from .models import VisualizationConfig, VisualizationType


DATE_KEYWORDS = {
    "date", "time", "year", "month", "day", "week", "quarter",
    "timestamp", "period", "order_date", "ship_date", "created_at", "updated_at"
}

CURRENCY_KEYWORDS = {
    "sales", "revenue", "profit", "price", "cost", "amount", "income",
    "salary", "fee", "budget", "spend", "balance", "total_sales", "total_profit"
}

PERCENT_KEYWORDS = {
    "rate", "percent", "percentage", "pct", "ratio", "margin", "share", "discount"
}


# ---------------------------------------------------------
# INTENT DETECTION
# ---------------------------------------------------------

VIS_INTENT_PATTERNS = {
    "pie": [
        r"\bpie\s+charts?\b",
        r"\bpie\s+graphs?\b",
        r"\bpie\s+plots?\b",
        r"\bpie\b",
        r"\bas\s+(?:a\s+)?pie\b",
        r"\busing\s+(?:a\s+)?pie\b",
        r"\bin\s+(?:a\s+)?pie\b",
        r"\bshow\s+(?:as\s+)?(?:a\s+)?pie\b",
    ],
    "bar": [
        r"\bbar\s+charts?\b",
        r"\bbar\s+graphs?\b",
        r"\bbar\s+plots?\b",
        r"\bbars\b",
        r"\bcolumn\s+charts?\b",
        r"\bcolumn\s+graphs?\b",
        r"\bcolumn\s+plots?\b",
        r"\bas\s+(?:a\s+)?bar\b",
        r"\busing\s+(?:a\s+)?bar\b",
        r"\bin\s+(?:a\s+)?bar\b",
        r"\bas\s+(?:a\s+)?column\b",
        r"\bshow\s+(?:as\s+)?(?:a\s+)?bar\b",
    ],
    "line": [
        r"\bline\s+charts?\b",
        r"\bline\s+graphs?\b",
        r"\bline\s+plots?\b",
        r"\btrend\s+charts?\b",
        r"\btrend\s+graphs?\b",
        r"\btrend\s+plots?\b",
        r"\bas\s+(?:a\s+)?line\b",
        r"\busing\s+(?:a\s+)?line\b",
        r"\bin\s+(?:a\s+)?line\b",
        r"\bshow\s+(?:as\s+)?(?:a\s+)?line\b",
    ],
    "scatter": [
        r"\bscatter\s+plots?\b",
        r"\bscatter\s+charts?\b",
        r"\bscatter\s+graphs?\b",
        r"\bscatter\b",
        r"\bas\s+(?:a\s+)?scatter\b",
        r"\busing\s+(?:a\s+)?scatter\b",
        r"\bshow\s+(?:as\s+)?(?:a\s+)?scatter\b",
    ],
    "table": [
        r"\bshow\s+(?:as\s+)?(?:a\s+)?table\b",
        r"\bas\s+(?:a\s+)?table\b",
        r"\bin\s+(?:a\s+)?table\b",
        r"\busing\s+(?:a\s+)?table\b",
        r"\btabular\b",
        r"\btable\s+view\b",
        r"\btable\s+format\b",
        r"\bdata\s+table\b",
    ],
    "kpi": [
        r"\bkpi\s+cards?\b",
        r"\bkpi\b",
        r"\bmetric\s+cards?\b",
        r"\bscorecard\b",
        r"\bsingle\s+value\b",
    ]
}

AUTO_PATTERNS = [
    r"\bchoose\s+(?:the\s+)?best\s+chart\b",
    r"\bpick\s+(?:a\s+)?suitable\s+chart\b",
    r"\buse\s+(?:an\s+)?appropriate\s+chart\b",
    r"\bvisualize\s+automatically\b",
    r"\bchoose\s+automatically\b",
    r"\bpick\s+(?:the\s+)?best\s+chart\b",
    r"\bselect\s+(?:the\s+)?best\s+chart\b",
    r"\bbest\s+chart\b",
    r"\bbest\s+visualization\b",
    r"\bautomatic\s+chart\b",
    r"\bauto\s+chart\b",
    r"\bautomatically\s+choose\b",
    r"\bpick\s+(?:the\s+)?best\s+visualization\b",
    r"\bchoose\s+the\s+chart\b",
    r"\bpick\s+a\s+chart\b",
]

GENERIC_VIS_PATTERNS = [
    r"\bvisualize\b",
    r"\bvisualise\b",
    r"\bvisualization\b",
    r"\bvisualisation\b",
    r"\bplot\b",
    r"\bplotting\b",
    r"\bcharts?\b",
    r"\bgraphs?\b",
    r"\bshow\s+(?:me\s+)?(?:a\s+)?chart\b",
    r"\bshow\s+(?:me\s+)?(?:a\s+)?graph\b",
    r"\bdisplay\s+(?:as\s+)?(?:a\s+)?chart\b",
]


def detect_visualization_intent(raw_question: Optional[str]) -> Tuple[bool, Optional[str], bool]:
    """
    Analyzes raw question to detect:
    1. is_vis_requested: True if user asked to visualize/plot/chart or specified a chart type.
    2. explicit_type: Detected chart type ("bar", "pie", "line", "scatter", "table", "kpi") or None.
    3. is_automatic: True if user explicitly asked for automatic chart selection.
    """
    if not raw_question:
        return False, None, False

    q = raw_question.strip().lower()

    # Check automatic intent first
    for pat in AUTO_PATTERNS:
        if re.search(pat, q):
            return True, None, True

    # Check explicit chart type
    for c_type, patterns in VIS_INTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q):
                return True, c_type, False

    # Check generic visualization intent (without specific type)
    for pat in GENERIC_VIS_PATTERNS:
        if re.search(pat, q):
            return True, None, False

    return False, None, False


# ---------------------------------------------------------
# MAIN SELECTOR
# ---------------------------------------------------------

def select_visualizations(
    spec: Optional[Union[QuerySpec, Dict[str, Any]]],
    query_result: QueryResult,
    schema: Optional[Dict[str, Any]] = None,
    df: Optional[pd.DataFrame] = None,
    raw_question: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Selects one or more visualization configurations based on query results, schema, and intent.
    Never automatically defaults to a bar chart when visualization was requested without a type.
    """
    if not query_result or not query_result.success:
        return []

    # Standardize spec to dict
    spec_dict: Dict[str, Any] = {}
    if spec is not None:
        if isinstance(spec, dict):
            spec_dict = spec
        elif hasattr(spec, "model_dump"):
            spec_dict = spec.model_dump()
        elif hasattr(spec, "to_dict"):
            spec_dict = spec.to_dict()

    query_dict = query_result.query or {}
    operation = str(spec_dict.get("operation") or query_dict.get("operation") or "count").lower().strip()
    target_col = spec_dict.get("column") or query_dict.get("column")
    group_by = list(spec_dict.get("group_by") or query_dict.get("group_by") or [])
    limit = spec_dict.get("limit") or query_dict.get("limit")
    sort = spec_dict.get("sort") or query_dict.get("sort") or []

    # Question for intent detection
    raw_q = (
        raw_question or
        spec_dict.get("raw_question") or
        (query_result.query.get("raw_question") if query_result.query else None) or
        ""
    )
    is_vis_requested, explicit_type, is_automatic = detect_visualization_intent(raw_q)

    schema_dict = schema or {}
    date_cols = set(schema_dict.get("date_columns", []))
    num_cols = set(schema_dict.get("numeric_columns", []))
    cat_cols = set(schema_dict.get("categorical_columns", []))

    visualizations: List[VisualizationConfig] = []

    # ---------------------------------------------------------
    # CASE 0: MULTI-QUERY MULTIPLE SCALARS
    # ---------------------------------------------------------
    if query_result.scalars and len(query_result.scalars) > 1:
        for s in query_result.scalars:
            metric_name = s.get("metric") or "Metric"
            val = s.get("value")
            agg = s.get("aggregation") or "total"
            title = _format_kpi_title(metric_name, agg)
            fmt = _infer_format(metric_name)

            visualizations.append(VisualizationConfig(
                type=VisualizationType.KPI.value,
                visualization_type=VisualizationType.KPI.value,
                visualization_required=is_vis_requested,
                visualization_source="user_requested" if explicit_type else ("automatic" if is_automatic else "default"),
                requires_user_choice=False,
                title=title,
                value=val,
                value_key=metric_name,
                format=fmt,
                description=f"{agg.capitalize()} of {metric_name}"
            ))

        if query_result.table:
            visualizations.append(VisualizationConfig(
                type=VisualizationType.TABLE.value,
                visualization_type=VisualizationType.TABLE.value,
                visualization_required=is_vis_requested,
                visualization_source="default",
                requires_user_choice=False,
                title="Summary Analysis",
                headers=query_result.table.get("headers", []),
                rows=query_result.table.get("rows", [])
            ))

        return [v.to_dict() for v in visualizations]

    # ---------------------------------------------------------
    # CASE 1: CONDITIONAL COUNT ACROSS COLUMNS (e.g. 24 subject codes)
    # ---------------------------------------------------------
    if operation == "conditional_count":
        cond_dict = query_dict.get("condition") or spec_dict.get("condition") or {}
        cond_val = cond_dict.get("value") if isinstance(cond_dict, dict) else getattr(cond_dict, "value", "Target")
        title = f"'{cond_val}' Counts across Subjects/Columns"

        records = query_result.result if isinstance(query_result.result, list) else []
        table_payload = query_result.table or {}
        headers = table_payload.get("headers", ["column", "condition", "count"])
        rows = table_payload.get("rows", [])

        dim_col = "column"
        val_col = "count"
        available_types = ["bar", "pie", "line", "table"]

        # 1A. Explicit User Request
        if explicit_type:
            vis_config = _build_typed_chart(
                c_type=explicit_type,
                records=records,
                headers=headers,
                rows=rows,
                dim_col=dim_col,
                val_col=val_col,
                title=title,
                fmt="number",
                orientation="horizontal" if len(records) > 8 else "vertical"
            )
            vis_config.visualization_required = True
            vis_config.visualization_source = "user_requested"
            vis_config.requires_user_choice = False
            visualizations.append(vis_config)

            # Attach companion table
            if explicit_type != "table" and rows and headers:
                visualizations.append(VisualizationConfig(
                    type=VisualizationType.TABLE.value,
                    visualization_type=VisualizationType.TABLE.value,
                    visualization_required=False,
                    visualization_source="default",
                    title=f"{title} Data",
                    headers=headers,
                    rows=rows,
                    data=records
                ))
            return [v.to_dict() for v in visualizations]

        # 1B. User explicitly requested automatic selection
        if is_automatic:
            bar_vis = VisualizationConfig(
                type=VisualizationType.BAR.value,
                visualization_type=VisualizationType.BAR.value,
                visualization_required=True,
                visualization_source="automatic",
                requires_user_choice=False,
                title=title,
                x_key=dim_col,
                y_key=val_col,
                orientation="horizontal" if len(records) > 8 else "vertical",
                format="number",
                data=records,
                headers=headers,
                rows=rows,
                description=f"Count of '{cond_val}' per column"
            )
            visualizations.append(bar_vis)
            return [v.to_dict() for v in visualizations]

        # 1C. User requested visualization WITHOUT specifying type -> ASK USER!
        if is_vis_requested:
            choice_vis = VisualizationConfig(
                type=None,
                visualization_type=None,
                visualization_required=True,
                visualization_source="user_not_specified",
                requires_user_choice=True,
                available_types=available_types,
                message=f"How would you like to visualize the '{cond_val}' counts?",
                title=title,
                x_key=dim_col,
                y_key=val_col,
                label_key=dim_col,
                value_key=val_col,
                format="number",
                data=records,
                headers=headers,
                rows=rows,
                description=f"Select preferred chart format for '{cond_val}' counts"
            )
            visualizations.append(choice_vis)
            return [v.to_dict() for v in visualizations]

        # 1D. Standard Analytical Query (no visualization directive) -> Bar & Table
        bar_vis = VisualizationConfig(
            type=VisualizationType.BAR.value,
            visualization_type=VisualizationType.BAR.value,
            visualization_required=False,
            visualization_source="default",
            title=title,
            x_key=dim_col,
            y_key=val_col,
            orientation="horizontal" if len(records) > 8 else "vertical",
            format="number",
            data=records,
            headers=headers,
            rows=rows,
            description=f"Count of '{cond_val}' per column"
        )
        visualizations.append(bar_vis)

        table_vis = VisualizationConfig(
            type=VisualizationType.TABLE.value,
            visualization_type=VisualizationType.TABLE.value,
            visualization_required=False,
            visualization_source="default",
            title=f"{title} Data",
            headers=headers,
            rows=rows,
            data=records
        )
        visualizations.append(table_vis)
        return [v.to_dict() for v in visualizations]

    # ---------------------------------------------------------
    # CASE 1B: MULTI-COLUMN VALUE DISTRIBUTION & VALUE DISTRIBUTION
    # ---------------------------------------------------------
    if operation in ("multi_column_value_distribution", "value_distribution"):
        title = "Grade Distribution across Subjects" if operation == "multi_column_value_distribution" else f"Grade Distribution for {target_col or 'Column'}"
        records = query_result.result if isinstance(query_result.result, list) else []
        table_payload = query_result.table or {}
        headers = table_payload.get("headers", ["Subject", "Grade", "Count"])
        rows = table_payload.get("rows", [])

        dim_col = "subject" if records and "subject" in records[0] else ("column" if records and "column" in records[0] else "Subject")
        val_col = "count"
        series_col = "grade" if records and "grade" in records[0] else ("value" if records and "value" in records[0] else None)

        if explicit_type == "table":
            table_vis = VisualizationConfig(
                type=VisualizationType.TABLE.value,
                visualization_type=VisualizationType.TABLE.value,
                visualization_required=True,
                visualization_source="user_requested",
                title=title,
                headers=headers,
                rows=rows,
                data=records
            )
            visualizations.append(table_vis)
            return [v.to_dict() for v in visualizations]

        # Horizontal Bar Chart (Grouped / Stacked)
        bar_vis = VisualizationConfig(
            type=VisualizationType.BAR.value,
            visualization_type=VisualizationType.BAR.value,
            visualization_required=is_vis_requested,
            visualization_source="user_requested" if explicit_type else ("automatic" if is_automatic else "default"),
            requires_user_choice=False,
            title=title,
            x_key="count",
            y_key=dim_col,
            series_key=series_col,
            orientation="horizontal",
            format="number",
            data=records,
            headers=headers,
            rows=rows,
            description="Grade distribution across subjects"
        )
        visualizations.append(bar_vis)

        # Companion Data Table (Pivot Table with all grades)
        table_vis = VisualizationConfig(
            type=VisualizationType.TABLE.value,
            visualization_type=VisualizationType.TABLE.value,
            visualization_required=False,
            visualization_source="default",
            title=f"{title} Table",
            headers=headers,
            rows=rows,
            data=records
        )
        visualizations.append(table_vis)
        return [v.to_dict() for v in visualizations]

    # ---------------------------------------------------------
    # CASE 2: SINGLE SCALAR RESULT -> KPI Metric Card
    # ---------------------------------------------------------
    if query_result.scalar is not None:
        scalar = query_result.scalar
        metric_name = scalar.get("metric") or target_col or "Metric"
        val = scalar.get("value")
        agg = scalar.get("aggregation") or operation

        title = _format_kpi_title(metric_name, agg)
        fmt = _infer_format(metric_name)

        if explicit_type == "table":
            table_vis = VisualizationConfig(
                type=VisualizationType.TABLE.value,
                visualization_type=VisualizationType.TABLE.value,
                visualization_required=True,
                visualization_source="user_requested",
                requires_user_choice=False,
                title=title,
                headers=[metric_name],
                rows=[[val]],
                data=[{metric_name: val}]
            )
            visualizations.append(table_vis)
            return [v.to_dict() for v in visualizations]

        kpi_vis = VisualizationConfig(
            type=VisualizationType.KPI.value,
            visualization_type=VisualizationType.KPI.value,
            visualization_required=is_vis_requested,
            visualization_source="user_requested" if explicit_type else ("automatic" if is_automatic else "default"),
            requires_user_choice=False,
            title=title,
            value=val,
            value_key=metric_name,
            format=fmt,
            description=f"{agg.capitalize()} of {metric_name}"
        )
        visualizations.append(kpi_vis)
        return [v.to_dict() for v in visualizations]

    # ---------------------------------------------------------
    # CASE 3: DISTINCT LIST -> Table
    # ---------------------------------------------------------
    if operation == "distinct" or (query_result.list is not None and not group_by):
        col_name = target_col or (query_result.list.get("column") if query_result.list else "Values")
        vals = query_result.list.get("values", []) if query_result.list else (query_result.result or [])
        clean_title = f"Unique {_format_col_name(col_name)}"

        table_vis = VisualizationConfig(
            type=VisualizationType.TABLE.value,
            visualization_type=VisualizationType.TABLE.value,
            visualization_required=is_vis_requested,
            visualization_source="user_requested" if explicit_type == "table" else ("automatic" if is_automatic else "default"),
            requires_user_choice=False,
            title=clean_title,
            headers=[col_name],
            rows=[[v] for v in vals],
            data=[{col_name: v} for v in vals],
            description=f"Distinct values list ({len(vals)} items)"
        )
        visualizations.append(table_vis)
        return [v.to_dict() for v in visualizations]

    # ---------------------------------------------------------
    # CASE 4: GROUPED QUERY RESULT OR DATASET RECORDS
    # ---------------------------------------------------------
    records = query_result.result if isinstance(query_result.result, list) else []
    table_payload = query_result.table or {}
    headers = table_payload.get("headers", [])
    rows = table_payload.get("rows", [])

    if not records and rows and headers:
        records = [{headers[i]: row[i] for i in range(len(headers))} for row in rows]

    if not records:
        if table_payload and headers and rows:
            return [VisualizationConfig(
                type=VisualizationType.TABLE.value,
                visualization_type=VisualizationType.TABLE.value,
                visualization_required=is_vis_requested,
                visualization_source="default",
                title="Data Results",
                headers=headers,
                rows=rows,
                data=[]
            ).to_dict()]
        return []

    # ---------------------------------------------------------
    # CASE 5: TWO NUMERIC COLUMNS (NO GROUP BY) -> Scatter Chart
    # ---------------------------------------------------------
    if not group_by and len(headers) == 2:
        col1, col2 = headers[0], headers[1]
        if (col1 in num_cols or _is_numeric_header(records, col1)) and (col2 in num_cols or _is_numeric_header(records, col2)):
            if is_vis_requested and not explicit_type and not is_automatic:
                choice_vis = VisualizationConfig(
                    type=None,
                    visualization_type=None,
                    visualization_required=True,
                    visualization_source="user_not_specified",
                    requires_user_choice=True,
                    available_types=["scatter", "table", "bar", "line"],
                    message=f"How would you like to visualize {_format_col_name(col1)} vs {_format_col_name(col2)}?",
                    title=f"{_format_col_name(col1)} vs {_format_col_name(col2)}",
                    x_key=col1,
                    y_key=col2,
                    data=records,
                    headers=headers,
                    rows=rows
                )
                return [choice_vis.to_dict()]

            scatter_vis = VisualizationConfig(
                type=VisualizationType.SCATTER.value if explicit_type != "table" else VisualizationType.TABLE.value,
                visualization_type=VisualizationType.SCATTER.value if explicit_type != "table" else VisualizationType.TABLE.value,
                visualization_required=is_vis_requested,
                visualization_source="user_requested" if explicit_type else ("automatic" if is_automatic else "default"),
                requires_user_choice=False,
                title=f"{_format_col_name(col1)} vs {_format_col_name(col2)}",
                x_key=col1,
                y_key=col2,
                data=records,
                headers=headers,
                rows=rows,
                description=f"Scatter distribution of {col1} and {col2}"
            )
            visualizations.append(scatter_vis)
            return [v.to_dict() for v in visualizations]

    # ---------------------------------------------------------
    # Sub-case 4A: Single Grouping Dimension (e.g. subject + count, region + sales)
    # ---------------------------------------------------------
    if len(group_by) == 1 or (records and len(records[0]) == 2 and not group_by):
        dim_col = group_by[0] if group_by else headers[0]
        val_col = _get_metric_column(records[0], dim_col, target_col)
        fmt = _infer_format(val_col)
        is_date = _is_date_dimension(dim_col, date_cols)
        row_count = len(records)
        clean_title = f"{_format_col_name(val_col)} by {_format_col_name(dim_col)}"

        # Compute valid available types for this data shape
        available_types = ["bar", "pie", "line", "table"]
        # If values have negatives, pie is not suitable
        has_negative = any((r.get(val_col) or 0) < 0 for r in records if isinstance(r.get(val_col), (int, float)))
        if has_negative:
            available_types = ["bar", "line", "table"]

        # 4A-1. Explicit User Request
        if explicit_type:
            # Check compatibility
            if explicit_type == "pie" and has_negative:
                # Explain incompatibility and offer choices
                choice_vis = VisualizationConfig(
                    type=None,
                    visualization_type=None,
                    visualization_required=True,
                    visualization_source="user_not_specified",
                    requires_user_choice=True,
                    available_types=["bar", "line", "table"],
                    message="Pie chart is not suitable for these values (contains negative numbers). Would you like a bar chart or table instead?",
                    title=clean_title,
                    x_key=dim_col,
                    y_key=val_col,
                    format=fmt,
                    data=records,
                    headers=headers,
                    rows=rows
                )
                return [choice_vis.to_dict()]

            vis_config = _build_typed_chart(
                c_type=explicit_type,
                records=records,
                headers=headers,
                rows=rows,
                dim_col=dim_col,
                val_col=val_col,
                title=clean_title,
                fmt=fmt,
                orientation="vertical"
            )
            vis_config.visualization_required = True
            vis_config.visualization_source = "user_requested"
            vis_config.requires_user_choice = False
            visualizations.append(vis_config)

            if explicit_type != "table" and rows and headers:
                visualizations.append(VisualizationConfig(
                    type=VisualizationType.TABLE.value,
                    visualization_type=VisualizationType.TABLE.value,
                    visualization_required=False,
                    visualization_source="default",
                    title=f"{clean_title} Data",
                    headers=headers or [dim_col, val_col],
                    rows=rows,
                    data=records
                ))
            return [v.to_dict() for v in visualizations]

        # 4A-2. Explicit Automatic Selection Request ("choose the best chart")
        if is_automatic:
            if is_date:
                auto_type = "line"
            elif (limit and limit <= 15) or _is_ranked_query(sort, limit):
                auto_type = "bar"
            elif 2 <= row_count <= 6 and _is_share_oriented(spec_dict, val_col):
                auto_type = "pie"
            else:
                auto_type = "bar"

            auto_vis = _build_typed_chart(
                c_type=auto_type,
                records=records,
                headers=headers,
                rows=rows,
                dim_col=dim_col,
                val_col=val_col,
                title=f"Top {len(records)} {_format_col_name(dim_col)} by {_format_col_name(val_col)}" if ((limit and limit <= 15) or _is_ranked_query(sort, limit)) else clean_title,
                fmt=fmt,
                orientation="horizontal" if ((limit and limit <= 15) or _is_ranked_query(sort, limit)) else "vertical"
            )
            auto_vis.visualization_required = True
            auto_vis.visualization_source = "automatic"
            auto_vis.requires_user_choice = False
            visualizations.append(auto_vis)
            return [v.to_dict() for v in visualizations]

        # 4A-3. User requested visualization WITHOUT specifying chart type -> ASK USER!
        if is_vis_requested:
            choice_vis = VisualizationConfig(
                type=None,
                visualization_type=None,
                visualization_required=True,
                visualization_source="user_not_specified",
                requires_user_choice=True,
                available_types=available_types,
                message=f"How would you like to visualize {clean_title}?",
                title=clean_title,
                x_key=dim_col,
                y_key=val_col,
                label_key=dim_col,
                value_key=val_col,
                format=fmt,
                data=records,
                headers=headers or [dim_col, val_col],
                rows=rows,
                description=f"Select preferred chart format for {clean_title}"
            )
            visualizations.append(choice_vis)
            return [v.to_dict() for v in visualizations]

        # 4A-4. Standard Analytical Query (no visualization request) -> Standard default
        if is_date:
            chart_vis = VisualizationConfig(
                type=VisualizationType.LINE.value,
                visualization_type=VisualizationType.LINE.value,
                visualization_required=False,
                visualization_source="default",
                title=clean_title,
                x_key=dim_col,
                y_key=val_col,
                format=fmt,
                data=records,
                headers=headers,
                rows=rows,
                description=f"Trend of {val_col} across {dim_col}"
            )
            visualizations.append(chart_vis)
        elif (limit and limit <= 15) or _is_ranked_query(sort, limit):
            hbar_vis = VisualizationConfig(
                type=VisualizationType.BAR.value,
                visualization_type=VisualizationType.BAR.value,
                visualization_required=False,
                visualization_source="default",
                title=f"Top {len(records)} {_format_col_name(dim_col)} by {_format_col_name(val_col)}",
                x_key=dim_col,
                y_key=val_col,
                orientation="horizontal",
                format=fmt,
                data=records,
                headers=headers,
                rows=rows,
                description=f"Ranked breakdown of {val_col} by {dim_col}"
            )
            visualizations.append(hbar_vis)
        elif 2 <= row_count <= 6 and _is_share_oriented(spec_dict, val_col):
            pie_vis = VisualizationConfig(
                type=VisualizationType.PIE.value,
                visualization_type=VisualizationType.PIE.value,
                visualization_required=False,
                visualization_source="default",
                title=f"{_format_col_name(val_col)} Share by {_format_col_name(dim_col)}",
                label_key=dim_col,
                value_key=val_col,
                x_key=dim_col,
                y_key=val_col,
                format=fmt,
                data=records,
                headers=headers,
                rows=rows,
                description=f"Proportional breakdown of {val_col} across {dim_col}"
            )
            visualizations.append(pie_vis)
        else:
            bar_vis = VisualizationConfig(
                type=VisualizationType.BAR.value,
                visualization_type=VisualizationType.BAR.value,
                visualization_required=False,
                visualization_source="default",
                title=clean_title,
                x_key=dim_col,
                y_key=val_col,
                orientation="vertical",
                format=fmt,
                data=records,
                headers=headers,
                rows=rows,
                description=f"Breakdown of {val_col} by {dim_col}"
            )
            visualizations.append(bar_vis)

        table_vis = VisualizationConfig(
            type=VisualizationType.TABLE.value,
            visualization_type=VisualizationType.TABLE.value,
            visualization_required=False,
            visualization_source="default",
            title=f"{clean_title} Data",
            headers=headers or [dim_col, val_col],
            rows=rows,
            data=records
        )
        visualizations.append(table_vis)
        return [v.to_dict() for v in visualizations]


    # ---------------------------------------------------------
    # Sub-case 4B: Multiple Grouping Dimensions (>= 2 dimensions)
    # ---------------------------------------------------------
    if len(group_by) >= 2:
        val_col = target_col or headers[-1]
        dims_str = " and ".join([_format_col_name(g) for g in group_by])
        table_title = f"{_format_col_name(val_col)} by {dims_str}"

        table_vis = VisualizationConfig(
            type=VisualizationType.TABLE.value,
            visualization_type=VisualizationType.TABLE.value,
            visualization_required=is_vis_requested,
            visualization_source="user_requested" if explicit_type == "table" else ("automatic" if is_automatic else "default"),
            requires_user_choice=False,
            title=table_title,
            headers=headers,
            rows=rows,
            data=records,
            description=f"Multi-dimensional breakdown ({len(records)} rows)"
        )
        visualizations.append(table_vis)

        # If secondary aggregated breakdown can be computed per primary dimension
        if df is not None and target_col and group_by[0] in df.columns:
            try:
                primary_dim = group_by[0]
                sec_grouped = df.groupby(primary_dim, as_index=False)[target_col].sum()
                sec_records = sec_grouped.head(10).to_dict(orient="records")
                if sec_records:
                    bar_summary = VisualizationConfig(
                        type=VisualizationType.BAR.value,
                        visualization_type=VisualizationType.BAR.value,
                        visualization_required=False,
                        visualization_source="default",
                        title=f"Total {_format_col_name(target_col)} by {_format_col_name(primary_dim)}",
                        x_key=primary_dim,
                        y_key=target_col,
                        orientation="vertical",
                        format=_infer_format(target_col),
                        data=sec_records,
                        description=f"Aggregated summary by {primary_dim}"
                    )
                    visualizations.insert(0, bar_summary)
            except Exception:
                pass

        return [v.to_dict() for v in visualizations]

    # ---------------------------------------------------------
    # CASE 5: TWO NUMERIC COLUMNS (NO GROUP BY) -> Scatter Chart
    # ---------------------------------------------------------
    if not group_by and len(headers) == 2:
        col1, col2 = headers[0], headers[1]
        if (col1 in num_cols or _is_numeric_header(records, col1)) and (col2 in num_cols or _is_numeric_header(records, col2)):
            if is_vis_requested and not explicit_type and not is_automatic:
                choice_vis = VisualizationConfig(
                    type=None,
                    visualization_type=None,
                    visualization_required=True,
                    visualization_source="user_not_specified",
                    requires_user_choice=True,
                    available_types=["scatter", "table", "bar", "line"],
                    message=f"How would you like to visualize {_format_col_name(col1)} vs {_format_col_name(col2)}?",
                    title=f"{_format_col_name(col1)} vs {_format_col_name(col2)}",
                    x_key=col1,
                    y_key=col2,
                    data=records,
                    headers=headers,
                    rows=rows
                )
                return [choice_vis.to_dict()]

            scatter_vis = VisualizationConfig(
                type=VisualizationType.SCATTER.value if explicit_type != "table" else VisualizationType.TABLE.value,
                visualization_type=VisualizationType.SCATTER.value if explicit_type != "table" else VisualizationType.TABLE.value,
                visualization_required=is_vis_requested,
                visualization_source="user_requested" if explicit_type else ("automatic" if is_automatic else "default"),
                requires_user_choice=False,
                title=f"{_format_col_name(col1)} vs {_format_col_name(col2)}",
                x_key=col1,
                y_key=col2,
                data=records,
                headers=headers,
                rows=rows,
                description=f"Scatter distribution of {col1} and {col2}"
            )
            visualizations.append(scatter_vis)
            return [v.to_dict() for v in visualizations]

    # ---------------------------------------------------------
    # FALLBACK: Data Table
    # ---------------------------------------------------------
    fallback_table = VisualizationConfig(
        type=VisualizationType.TABLE.value,
        visualization_type=VisualizationType.TABLE.value,
        visualization_required=is_vis_requested,
        visualization_source="default",
        requires_user_choice=False,
        title="Query Results",
        headers=headers,
        rows=rows,
        data=records
    )
    visualizations.append(fallback_table)
    return [v.to_dict() for v in visualizations]


# ---------------------------------------------------------
# CHART BUILDER HELPER
# ---------------------------------------------------------

def _build_typed_chart(
    c_type: str,
    records: List[Dict[str, Any]],
    headers: List[str],
    rows: List[List[Any]],
    dim_col: str,
    val_col: str,
    title: str,
    fmt: str = "number",
    orientation: str = "vertical"
) -> VisualizationConfig:
    """Constructs a VisualizationConfig for a specific requested chart type."""
    t_clean = c_type.lower().strip()

    if t_clean in ("pie", "pie chart", "pie graph"):
        return VisualizationConfig(
            type=VisualizationType.PIE.value,
            visualization_type=VisualizationType.PIE.value,
            title=f"{title} (Pie Chart)",
            label_key=dim_col,
            value_key=val_col,
            x_key=dim_col,
            y_key=val_col,
            format=fmt,
            data=records,
            headers=headers,
            rows=rows,
            description=f"Proportional breakdown of {val_col} across {dim_col}"
        )
    elif t_clean in ("line", "line chart", "line graph", "trend chart"):
        return VisualizationConfig(
            type=VisualizationType.LINE.value,
            visualization_type=VisualizationType.LINE.value,
            title=f"{title} (Line Chart)",
            x_key=dim_col,
            y_key=val_col,
            format=fmt,
            data=records,
            headers=headers,
            rows=rows,
            description=f"Trend line of {val_col} across {dim_col}"
        )
    elif t_clean in ("scatter", "scatter plot", "scatter chart"):
        return VisualizationConfig(
            type=VisualizationType.SCATTER.value,
            visualization_type=VisualizationType.SCATTER.value,
            title=f"{title} (Scatter Plot)",
            x_key=dim_col,
            y_key=val_col,
            data=records,
            headers=headers,
            rows=rows,
            description=f"Scatter distribution of {val_col} and {dim_col}"
        )
    elif t_clean in ("table", "tabular", "data table"):
        return VisualizationConfig(
            type=VisualizationType.TABLE.value,
            visualization_type=VisualizationType.TABLE.value,
            title=f"{title} Table",
            headers=headers or [dim_col, val_col],
            rows=rows,
            data=records,
            description=f"Data table for {title}"
        )
    else:  # Default to bar
        return VisualizationConfig(
            type=VisualizationType.BAR.value,
            visualization_type=VisualizationType.BAR.value,
            title=f"{title} (Bar Chart)",
            x_key=dim_col,
            y_key=val_col,
            orientation=orientation,
            format=fmt,
            data=records,
            headers=headers,
            rows=rows,
            description=f"Bar chart of {val_col} by {dim_col}"
        )


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def _format_col_name(col: Optional[str]) -> str:
    """Formats column names for display (e.g. 'country_region' -> 'Country Region')."""
    if not col:
        return ""
    words = str(col).replace("_", " ").replace("-", " ").split()
    return " ".join(w.capitalize() for w in words)


def _format_kpi_title(metric: str, agg: str) -> str:
    """Generates clean title for KPI metric cards."""
    clean_metric = _format_col_name(metric)
    agg_lower = (agg or "total").lower()

    if agg_lower in ("sum", "total"):
        return f"Total {clean_metric}"
    elif agg_lower in ("average", "mean", "avg"):
        return f"Average {clean_metric}"
    elif agg_lower in ("min", "minimum"):
        return f"Minimum {clean_metric}"
    elif agg_lower in ("max", "maximum"):
        return f"Maximum {clean_metric}"
    elif agg_lower == "count_distinct":
        return f"Unique {clean_metric} Count"
    elif agg_lower == "count":
        return f"Total {clean_metric} Count"
    return f"{clean_metric} ({agg.capitalize()})"


def _infer_format(col_name: Optional[str]) -> str:
    """Infers number display format (currency, percentage, number) from column name."""
    if not col_name:
        return "number"
    c_lower = str(col_name).lower()
    if any(k in c_lower for k in CURRENCY_KEYWORDS):
        return "currency"
    if any(k in c_lower for k in PERCENT_KEYWORDS):
        return "percentage"
    return "number"


def _is_date_dimension(col_name: str, date_cols: set) -> bool:
    """Checks if a dimension column represents date / time series."""
    if col_name in date_cols:
        return True
    c_lower = col_name.lower()
    return any(kw in c_lower for kw in DATE_KEYWORDS)


def _is_ranked_query(sort: List[Any], limit: Optional[int]) -> bool:
    """Checks if query is a ranked or top-N query."""
    if limit and limit <= 15:
        return True
    if sort:
        for s in sort:
            s_dir = s.get("direction") if isinstance(s, dict) else getattr(s, "direction", "desc")
            if str(s_dir).lower() == "desc":
                return True
    return False


def _is_share_oriented(spec_dict: Dict[str, Any], val_col: str) -> bool:
    """Checks if query or metric implies proportional share (e.g. pie chart)."""
    raw_q = str(spec_dict.get("raw_question") or "").lower()
    if any(w in raw_q for w in ["share", "proportion", "percentage", "distribution", "ratio"]):
        return True
    return False


def _get_metric_column(first_record: Dict[str, Any], dim_col: str, target_col: Optional[str]) -> str:
    """Identifies the metric/value column from record keys."""
    if target_col and target_col in first_record:
        return target_col
    for k, v in first_record.items():
        if k != dim_col:
            return k
    return "value"


def _is_numeric_header(records: List[Dict[str, Any]], col_name: str) -> bool:
    """Checks if values for a column are numeric across records."""
    if not records:
        return False
    sample = [r.get(col_name) for r in records[:5] if r.get(col_name) is not None]
    return len(sample) > 0 and all(isinstance(v, (int, float)) for v in sample)
