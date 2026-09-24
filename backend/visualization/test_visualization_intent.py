"""
Unit tests for Visualization Intent Detection and Explicit/Automatic/User-Choice Routing.
Validates that the system NEVER automatically assumes a bar chart when the user has not specified a visualization type.
Tests all 7 required scenarios from the prompt:
1. "visualize the A grade count for each subject" -> requires_user_choice = True, visualization_type = None
2. "visualize the A grade count for each subject using pie chart" -> visualization_type = "pie", requires_user_choice = False
3. "show A grade count for each subject as a bar chart" -> visualization_type = "bar", requires_user_choice = False
4. "show A grade count for each subject as a line chart" -> visualization_type = "line", requires_user_choice = False
5. "show A grade count for each subject as a table" -> visualization_type = "table", requires_user_choice = False
6. "visualize sales by month and choose the best chart" -> visualization_source = "automatic", requires_user_choice = False
7. "what is the total profit?" -> requires_user_choice = False, visualization_required = False
"""

import pytest
import pandas as pd
from analyst.models import QuerySpec, QueryResult, ConditionSpec
from visualization.selector import select_visualizations, detect_visualization_intent


# ---------------------------------------------------------
# Intent Detection Helper Tests
# ---------------------------------------------------------

def test_intent_detection_explicit_types():
    assert detect_visualization_intent("visualize using pie chart") == (True, "pie", False)
    assert detect_visualization_intent("show as a bar chart") == (True, "bar", False)
    assert detect_visualization_intent("show as a line chart") == (True, "line", False)
    assert detect_visualization_intent("show results as a table") == (True, "table", False)
    assert detect_visualization_intent("show sales and profit using a scatter plot") == (True, "scatter", False)


def test_intent_detection_automatic():
    assert detect_visualization_intent("visualize sales by month and choose the best chart") == (True, None, True)
    assert detect_visualization_intent("pick a suitable chart for this data") == (True, None, True)
    assert detect_visualization_intent("visualize automatically") == (True, None, True)


def test_intent_detection_unspecified_visualization():
    assert detect_visualization_intent("visualize the A grade count for each subject") == (True, None, False)
    assert detect_visualization_intent("plot the data") == (True, None, False)
    assert detect_visualization_intent("show me a chart of sales by region") == (True, None, False)


def test_intent_detection_normal_analytical_query():
    assert detect_visualization_intent("what is the total profit?") == (False, None, False)
    assert detect_visualization_intent("how many orders were placed?") == (False, None, False)
    assert detect_visualization_intent("list the unique country_regions") == (False, None, False)


# ---------------------------------------------------------
# Required Test Cases 1 through 7
# ---------------------------------------------------------

def test_1_user_not_specified_chart_requires_choice():
    """
    Test 1:
    Query: "visualize the A grade count for each subject"
    Expected: requires_user_choice = True, visualization_type = None, visualization_source = "user_not_specified"
    """
    mock_result = [
        {"column": "CS23333", "condition": "A", "count": 96},
        {"column": "CS23331", "condition": "A", "count": 117},
        {"column": "CS23332", "condition": "A", "count": 143},
        {"column": "AI23331", "condition": "A", "count": 149},
        {"column": "MA23313", "condition": "A", "count": 102}
    ]
    query_res = QueryResult(
        success=True,
        query={"operation": "conditional_count", "columns": ["CS23333", "CS23331", "CS23332", "AI23331", "MA23313"]},
        result=mock_result,
        table={"headers": ["column", "condition", "count"], "rows": [["CS23333", "A", 96], ["CS23331", "A", 117]]}
    )
    spec = QuerySpec(
        operation="conditional_count",
        columns=["CS23333", "CS23331", "CS23332", "AI23331", "MA23313"],
        condition=ConditionSpec(operator="equals", value="A"),
        raw_question="visualize the A grade count for each subject"
    )

    visualizations = select_visualizations(spec, query_res, raw_question="visualize the A grade count for each subject")

    assert len(visualizations) == 1
    vis = visualizations[0]
    assert vis["requires_user_choice"] is True
    assert vis.get("visualization_type") is None
    assert vis.get("type") is None
    assert vis["visualization_source"] == "user_not_specified"
    assert vis["visualization_required"] is True
    assert "bar" in vis["available_types"]
    assert "pie" in vis["available_types"]
    assert "table" in vis["available_types"]


def test_2_explicit_pie_chart_request():
    """
    Test 2:
    Query: "visualize the A grade count for each subject using pie chart"
    Expected: visualization_type = "pie", requires_user_choice = False, visualization_source = "user_requested"
    """
    mock_result = [
        {"column": "CS23333", "condition": "A", "count": 96},
        {"column": "CS23331", "condition": "A", "count": 117},
        {"column": "AI23331", "condition": "A", "count": 149}
    ]
    query_res = QueryResult(
        success=True,
        query={"operation": "conditional_count"},
        result=mock_result,
        table={"headers": ["column", "condition", "count"], "rows": [["CS23333", "A", 96], ["CS23331", "A", 117], ["AI23331", "A", 149]]}
    )
    spec = QuerySpec(
        operation="conditional_count",
        raw_question="visualize the A grade count for each subject using pie chart"
    )

    visualizations = select_visualizations(spec, query_res, raw_question="visualize the A grade count for each subject using pie chart")

    assert len(visualizations) >= 1
    vis = visualizations[0]
    assert vis["visualization_type"] == "pie"
    assert vis["type"] == "pie"
    assert vis["requires_user_choice"] is False
    assert vis["visualization_source"] == "user_requested"
    assert vis["visualization_required"] is True


def test_3_explicit_bar_chart_request():
    """
    Test 3:
    Query: "show A grade count for each subject as a bar chart"
    Expected: visualization_type = "bar", requires_user_choice = False, visualization_source = "user_requested"
    """
    mock_result = [
        {"column": "CS23333", "condition": "A", "count": 96},
        {"column": "CS23331", "condition": "A", "count": 117}
    ]
    query_res = QueryResult(
        success=True,
        query={"operation": "conditional_count"},
        result=mock_result,
        table={"headers": ["column", "condition", "count"], "rows": [["CS23333", "A", 96], ["CS23331", "A", 117]]}
    )
    spec = QuerySpec(
        operation="conditional_count",
        raw_question="show A grade count for each subject as a bar chart"
    )

    visualizations = select_visualizations(spec, query_res, raw_question="show A grade count for each subject as a bar chart")

    assert len(visualizations) >= 1
    vis = visualizations[0]
    assert vis["visualization_type"] == "bar"
    assert vis["type"] == "bar"
    assert vis["requires_user_choice"] is False
    assert vis["visualization_source"] == "user_requested"


def test_4_explicit_line_chart_request():
    """
    Test 4:
    Query: "show A grade count for each subject as a line chart"
    Expected: visualization_type = "line", requires_user_choice = False, visualization_source = "user_requested"
    """
    mock_result = [
        {"column": "CS23333", "condition": "A", "count": 96},
        {"column": "CS23331", "condition": "A", "count": 117}
    ]
    query_res = QueryResult(
        success=True,
        query={"operation": "conditional_count"},
        result=mock_result,
        table={"headers": ["column", "condition", "count"], "rows": [["CS23333", "A", 96], ["CS23331", "A", 117]]}
    )
    spec = QuerySpec(
        operation="conditional_count",
        raw_question="show A grade count for each subject as a line chart"
    )

    visualizations = select_visualizations(spec, query_res, raw_question="show A grade count for each subject as a line chart")

    assert len(visualizations) >= 1
    vis = visualizations[0]
    assert vis["visualization_type"] == "line"
    assert vis["type"] == "line"
    assert vis["requires_user_choice"] is False
    assert vis["visualization_source"] == "user_requested"


def test_5_explicit_table_request():
    """
    Test 5:
    Query: "show A grade count for each subject as a table"
    Expected: visualization_type = "table", requires_user_choice = False, visualization_source = "user_requested"
    """
    mock_result = [
        {"column": "CS23333", "condition": "A", "count": 96},
        {"column": "CS23331", "condition": "A", "count": 117}
    ]
    query_res = QueryResult(
        success=True,
        query={"operation": "conditional_count"},
        result=mock_result,
        table={"headers": ["column", "condition", "count"], "rows": [["CS23333", "A", 96], ["CS23331", "A", 117]]}
    )
    spec = QuerySpec(
        operation="conditional_count",
        raw_question="show A grade count for each subject as a table"
    )

    visualizations = select_visualizations(spec, query_res, raw_question="show A grade count for each subject as a table")

    assert len(visualizations) >= 1
    vis = visualizations[0]
    assert vis["visualization_type"] == "table"
    assert vis["type"] == "table"
    assert vis["requires_user_choice"] is False
    assert vis["visualization_source"] == "user_requested"


def test_6_automatic_chart_selection():
    """
    Test 6:
    Query: "visualize sales by month and choose the best chart"
    Expected: visualization_source = "automatic", requires_user_choice = False
    """
    mock_result = [
        {"order_date": "2024-01", "sales": 10000},
        {"order_date": "2024-02", "sales": 12000},
        {"order_date": "2024-03", "sales": 15000}
    ]
    query_res = QueryResult(
        success=True,
        query={"operation": "sum", "column": "sales", "group_by": ["order_date"]},
        result=mock_result,
        table={"headers": ["order_date", "sales"], "rows": [["2024-01", 10000], ["2024-02", 12000], ["2024-03", 15000]]}
    )
    spec = QuerySpec(
        operation="sum",
        column="sales",
        group_by=["order_date"],
        raw_question="visualize sales by month and choose the best chart"
    )
    schema = {"date_columns": ["order_date"], "numeric_columns": ["sales"]}

    visualizations = select_visualizations(
        spec,
        query_res,
        schema=schema,
        raw_question="visualize sales by month and choose the best chart"
    )

    assert len(visualizations) >= 1
    vis = visualizations[0]
    assert vis["visualization_source"] == "automatic"
    assert vis["requires_user_choice"] is False
    assert vis["visualization_required"] is True
    assert vis["type"] == "line"  # Line chart is best for date trend


def test_7_no_visualization_requested():
    """
    Test 7:
    Query: "what is the total profit?"
    Expected: requires_user_choice = False, visualization_required = False
    """
    kpi_res = QueryResult(
        success=True,
        scalar={"metric": "profit", "aggregation": "sum", "value": 2297200.86}
    )
    spec = QuerySpec(
        operation="sum",
        column="profit",
        raw_question="what is the total profit?"
    )

    visualizations = select_visualizations(spec, kpi_res, raw_question="what is the total profit?")

    assert len(visualizations) == 1
    vis = visualizations[0]
    assert vis["requires_user_choice"] is False
    assert vis["visualization_required"] is False
    assert vis["visualization_source"] == "default"
    assert vis["type"] == "kpi"
    assert vis["value"] == 2297200.86


def test_incompatible_pie_chart_falls_back_to_user_choice():
    """
    If user requests pie chart but data has negative numbers,
    do NOT silently convert to bar chart; return user choice with explanation.
    """
    mock_result = [
        {"category": "A", "profit": 500},
        {"category": "B", "profit": -200},
        {"category": "C", "profit": 300}
    ]
    query_res = QueryResult(
        success=True,
        query={"operation": "sum", "column": "profit", "group_by": ["category"]},
        result=mock_result,
        table={"headers": ["category", "profit"], "rows": [["A", 500], ["B", -200], ["C", 300]]}
    )
    spec = QuerySpec(
        operation="sum",
        column="profit",
        group_by=["category"],
        raw_question="visualize profit by category using pie chart"
    )
    schema = {"categorical_columns": ["category"], "numeric_columns": ["profit"]}

    visualizations = select_visualizations(
        spec,
        query_res,
        schema=schema,
        raw_question="visualize profit by category using pie chart"
    )

    assert len(visualizations) == 1
    vis = visualizations[0]
    assert vis["requires_user_choice"] is True
    assert "Pie chart is not suitable" in vis["message"]
    assert "bar" in vis["available_types"]
    assert "table" in vis["available_types"]
