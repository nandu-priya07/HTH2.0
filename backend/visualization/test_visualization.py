"""
Unit tests for the Dynamic Visualization Selector module.
Tests all required visualization cases:
1. KPI metric card for single scalar
2. Bar chart for categorical + numeric
3. Line chart for date/time + numeric
4. Horizontal bar chart for ranked / top-N
5. Distinct list to Table
6. Multi-dimensional to Table
7. Scatter chart for two numeric columns
8. Pie chart for small part-to-whole share
"""

import pytest
from analyst.models import QuerySpec, QueryResult
from visualization.selector import select_visualizations


def test_single_numeric_kpi():
    """Test 1: Single numeric result -> KPI metric card"""
    kpi_res = QueryResult(
        success=True,
        scalar={"metric": "sales", "aggregation": "sum", "value": 2297200.86}
    )
    spec = QuerySpec(operation="sum", column="sales")
    visualizations = select_visualizations(spec, kpi_res)

    assert len(visualizations) == 1
    vis = visualizations[0]
    assert vis["type"] == "kpi"
    assert "Sales" in vis["title"]
    assert vis["value"] == 2297200.86


def test_categorical_and_numeric_bar_chart():
    """Test 2: One categorical + one numeric -> Vertical Bar chart"""
    bar_res = QueryResult(
        success=True,
        query={"operation": "sum", "column": "sales", "group_by": ["region"]},
        result=[
            {"region": "West", "sales": 725457.82},
            {"region": "East", "sales": 678781.24},
            {"region": "Central", "sales": 501239.89},
            {"region": "South", "sales": 391721.90}
        ],
        table={
            "headers": ["region", "sales"],
            "rows": [["West", 725457.82], ["East", 678781.24], ["Central", 501239.89], ["South", 391721.90]]
        }
    )
    spec = QuerySpec(operation="sum", column="sales", group_by=["region"])
    schema = {"categorical_columns": ["region"], "numeric_columns": ["sales"]}
    visualizations = select_visualizations(spec, bar_res, schema=schema)

    assert len(visualizations) >= 1
    bar_vis = visualizations[0]
    assert bar_vis["type"] == "bar"
    assert bar_vis["x_key"] == "region"
    assert bar_vis["y_key"] == "sales"
    assert bar_vis.get("orientation") == "vertical"


def test_date_and_numeric_line_chart():
    """Test 3: Date/time + numeric -> Line chart"""
    line_res = QueryResult(
        success=True,
        query={"operation": "sum", "column": "sales", "group_by": ["order_date"]},
        result=[
            {"order_date": "2024-01", "sales": 10000},
            {"order_date": "2024-02", "sales": 12000},
            {"order_date": "2024-03", "sales": 15000}
        ],
        table={
            "headers": ["order_date", "sales"],
            "rows": [["2024-01", 10000], ["2024-02", 12000], ["2024-03", 15000]]
        }
    )
    spec = QuerySpec(operation="sum", column="sales", group_by=["order_date"])
    schema = {"date_columns": ["order_date"], "numeric_columns": ["sales"]}
    visualizations = select_visualizations(spec, line_res, schema=schema)

    assert len(visualizations) >= 1
    line_vis = visualizations[0]
    assert line_vis["type"] == "line"
    assert line_vis["x_key"] == "order_date"
    assert line_vis["y_key"] == "sales"


def test_ranked_top_n_horizontal_bar_chart():
    """Test 4: Ranked / Top-N -> Horizontal Bar chart"""
    top_res = QueryResult(
        success=True,
        query={"operation": "sum", "column": "profit", "group_by": ["product_name"]},
        result=[
            {"product_name": "Canon Copier", "profit": 25199},
            {"product_name": "Fellowes Binder", "profit": 7743},
            {"product_name": "Hewlett Packard Laser", "profit": 6140}
        ],
        table={
            "headers": ["product_name", "profit"],
            "rows": [
                ["Canon Copier", 25199],
                ["Fellowes Binder", 7743],
                ["Hewlett Packard Laser", 6140]
            ]
        }
    )
    spec = QuerySpec(
        operation="sum",
        column="profit",
        group_by=["product_name"],
        limit=5,
        sort=[{"column": "profit", "direction": "desc"}]
    )
    schema = {"categorical_columns": ["product_name"], "numeric_columns": ["profit"]}
    visualizations = select_visualizations(spec, top_res, schema=schema)

    assert len(visualizations) >= 1
    hbar_vis = visualizations[0]
    assert hbar_vis["type"] == "bar"
    assert hbar_vis.get("orientation") == "horizontal"
    assert "Top" in hbar_vis["title"]


def test_distinct_list_to_table():
    """Test 5: Distinct values list -> Table"""
    dist_res = QueryResult(
        success=True,
        query={"operation": "distinct", "column": "country_region"},
        result=["United States", "Canada", "Mexico"],
        list={"column": "country_region", "values": ["United States", "Canada", "Mexico"], "count": 3}
    )
    spec = QuerySpec(operation="distinct", column="country_region")
    visualizations = select_visualizations(spec, dist_res)

    assert len(visualizations) == 1
    table_vis = visualizations[0]
    assert table_vis["type"] == "table"
    assert "Country Region" in table_vis["title"]


def test_multi_dimensional_grouping_to_table():
    """Test 6: Multi-dimensional grouping -> Table"""
    multi_res = QueryResult(
        success=True,
        query={"operation": "sum", "column": "profit", "group_by": ["country_region", "region"]},
        result=[
            {"country_region": "United States", "region": "West", "profit": 108418},
            {"country_region": "United States", "region": "East", "profit": 91522}
        ],
        table={
            "headers": ["country_region", "region", "profit"],
            "rows": [
                ["United States", "West", 108418],
                ["United States", "East", 91522]
            ]
        }
    )
    spec = QuerySpec(operation="sum", column="profit", group_by=["country_region", "region"])
    schema = {"categorical_columns": ["country_region", "region"], "numeric_columns": ["profit"]}
    visualizations = select_visualizations(spec, multi_res, schema=schema)

    assert any(v["type"] == "table" for v in visualizations)


def test_scatter_chart_two_numeric():
    """Test 7: Two numeric columns -> Scatter chart"""
    scatter_res = QueryResult(
        success=True,
        result=[
            {"sales": 100, "profit": 20},
            {"sales": 200, "profit": 45}
        ],
        table={
            "headers": ["sales", "profit"],
            "rows": [[100, 20], [200, 45]]
        }
    )
    schema = {"numeric_columns": ["sales", "profit"]}
    visualizations = select_visualizations(None, scatter_res, schema=schema)

    assert len(visualizations) >= 1
    assert visualizations[0]["type"] == "scatter"


def test_pie_chart_share_query():
    """Test 8: Part-to-whole / share query with small category count -> Pie chart"""
    pie_res = QueryResult(
        success=True,
        query={"operation": "sum", "column": "sales", "group_by": ["category"]},
        result=[
            {"category": "Technology", "sales": 839893.28},
            {"category": "Furniture", "sales": 754747.76},
            {"category": "Office Supplies", "sales": 731893.31}
        ],
        table={
            "headers": ["category", "sales"],
            "rows": [
                ["Technology", 839893.28],
                ["Furniture", 754747.76],
                ["Office Supplies", 731893.31]
            ]
        }
    )
    spec = QuerySpec(operation="sum", column="sales", group_by=["category"])
    spec_dict = spec.model_dump()
    spec_dict["raw_question"] = "What is the sales share by category?"

    schema = {"categorical_columns": ["category"], "numeric_columns": ["sales"]}
    visualizations = select_visualizations(spec_dict, pie_res, schema=schema)

    assert len(visualizations) >= 1
    assert visualizations[0]["type"] == "pie"
