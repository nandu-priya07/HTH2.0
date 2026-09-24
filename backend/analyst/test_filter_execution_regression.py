"""
Regression test suite for Filter Execution, Single Source of Truth,
Zero Match Protection, Column Validation, and Conversational Follow-Up.
"""

import pytest
import pandas as pd
from analyst.models import QuerySpec, FilterSpec, QueryResult, ResponseType
from analyst.query_executor import execute_query, execute_queries, ZeroMatchError, ColumnNotFoundError
from analyst.query_processor import process_query_with_llm, _fallback_router
from chat.context_resolver import ContextResolver


@pytest.fixture
def sample_sales_df():
    data = {
        "order_id": ["CA-1", "CA-2", "DE-1", "DE-2", "DE-3", "FR-1"],
        "sales": [1000.0, 2000.0, 1500.0, 2500.0, 3000.0, 4000.0],
        "profit": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0],
        "country_region": ["Canada", "Canada", "Germany", "Germany", "Germany", "France"],
        "ship_mode": ["Regular Air", "First Class", "Regular Air", "First Class", "First Class", "Delivery Truck"],
        "category": ["Technology", "Technology", "Office Supplies", "Furniture", "Technology", "Furniture"]
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_schema(sample_sales_df):
    return {
        "columns": [
            {"name": col, "dtype": str(sample_sales_df[col].dtype), "semantic_type": "numeric" if pd.api.types.is_numeric_dtype(sample_sales_df[col]) else "categorical"}
            for col in sample_sales_df.columns
        ]
    }


# ==============================================================================
# TEST 1: Global aggregation vs Filtered aggregation (The Original Bug)
# ==============================================================================

def test_total_profit_global(sample_sales_df):
    """Total profit should sum all 6 rows: 2,100."""
    spec = QuerySpec(
        operation="sum",
        column="profit",
        filters=[]
    )
    res = execute_query(spec, sample_sales_df)
    assert res.success is True
    assert res.result == 2100.0
    assert res.metadata["rows_analyzed"] == 6
    assert res.metadata["filtered_rows"] == 6


def test_total_profit_for_canada(sample_sales_df):
    """
    CRITICAL BUG TEST: Total profit for Canada must ONLY sum Canadian rows (300.0),
    NEVER the global total (2,100.0).
    """
    spec = QuerySpec(
        operation="sum",
        column="profit",
        filters=[
            FilterSpec(column="country_region", operator="equals", value="Canada")
        ]
    )
    res = execute_query(spec, sample_sales_df)
    assert res.success is True
    # Must NOT equal global sum
    assert res.result != 2100.0
    # Must equal exact Canadian sum
    assert res.result == 300.0
    assert res.metadata["rows_before_filter"] == 6
    assert res.metadata["rows_after_filter"] == 2
    assert res.metadata["filtered_rows"] == 2
    assert "country_region" in res.metadata["fields_used"]
    assert "profit" in res.metadata["fields_used"]
    assert "Canada" in res.text


def test_total_profit_for_germany(sample_sales_df):
    """Total profit for Germany must sum 300 + 400 + 500 = 1200.0."""
    spec = QuerySpec(
        operation="sum",
        column="profit",
        filters=[
            FilterSpec(column="country_region", operator="equals", value="Germany")
        ]
    )
    res = execute_query(spec, sample_sales_df)
    assert res.success is True
    assert res.result == 1200.0
    assert res.metadata["filtered_rows"] == 3


def test_string_normalization_and_whitespace(sample_sales_df):
    """Filter must match despite whitespace or casing differences (canada, CANADA, 'Canada ')."""
    for val in ["canada", "CANADA", " Canada ", "Canada"]:
        spec = QuerySpec(
            operation="sum",
            column="profit",
            filters=[
                FilterSpec(column="country_region", operator="equals", value=val)
            ]
        )
        res = execute_query(spec, sample_sales_df)
        assert res.success is True
        assert res.result == 300.0


# ==============================================================================
# TEST 2: Filter + Group By (Follow-Up Test)
# ==============================================================================

def test_canada_profit_grouped_by_ship_mode(sample_sales_df):
    """
    Follow-up query: Break this down by ship_mode.
    Must maintain country_region = Canada filter AND group by ship_mode.
    """
    spec = QuerySpec(
        operation="sum",
        column="profit",
        group_by=["ship_mode"],
        filters=[
            FilterSpec(column="country_region", operator="equals", value="Canada")
        ]
    )
    res = execute_query(spec, sample_sales_df)
    assert res.success is True
    assert res.metadata["filtered_rows"] == 2
    assert len(res.result) == 2
    # Check groups
    group_dict = {r["ship_mode"]: r["profit"] for r in res.result}
    assert group_dict["Regular Air"] == 100.0
    assert group_dict["First Class"] == 200.0
    assert "country_region" in res.metadata["fields_used"]
    assert "ship_mode" in res.metadata["fields_used"]


def test_germany_profit_grouped_by_ship_mode(sample_sales_df):
    """
    Follow-up: What about Germany?
    Filter country_region = Germany, group_by ship_mode.
    """
    spec = QuerySpec(
        operation="sum",
        column="profit",
        group_by=["ship_mode"],
        filters=[
            FilterSpec(column="country_region", operator="equals", value="Germany")
        ]
    )
    res = execute_query(spec, sample_sales_df)
    assert res.success is True
    assert res.metadata["filtered_rows"] == 3
    group_dict = {r["ship_mode"]: r["profit"] for r in res.result}
    assert group_dict["Regular Air"] == 300.0
    assert group_dict["First Class"] == 900.0


def test_multi_filter_germany_and_first_class(sample_sales_df):
    """
    Follow-up: Only First Class.
    country_region = Germany AND ship_mode = First Class -> 400 + 500 = 900.0.
    """
    spec = QuerySpec(
        operation="sum",
        column="profit",
        filters=[
            FilterSpec(column="country_region", operator="equals", value="Germany"),
            FilterSpec(column="ship_mode", operator="equals", value="First Class")
        ]
    )
    res = execute_query(spec, sample_sales_df)
    assert res.success is True
    assert res.result == 900.0
    assert res.metadata["filtered_rows"] == 2


# ==============================================================================
# TEST 3: Zero Match Protection (STEP 11)
# ==============================================================================

def test_zero_match_protection(sample_sales_df):
    """
    STEP 11: If a filter matches 0 rows:
    DO NOT fallback to unfiltered DataFrame.
    Return 'No rows matched <col> = <val>'.
    """
    spec = QuerySpec(
        operation="sum",
        column="profit",
        filters=[
            FilterSpec(column="country_region", operator="equals", value="Antarctica")
        ]
    )
    res = execute_query(spec, sample_sales_df)
    assert res.success is False
    assert "No rows matched" in res.error
    assert "Antarctica" in res.error
    # Must NOT have calculated global profit!
    assert res.result != 2100.0


# ==============================================================================
# TEST 4: Invalid Column Protection (STEP 12)
# ==============================================================================

def test_invalid_column_protection(sample_sales_df):
    """
    STEP 12: If requested column does not exist in dataset:
    Return clear explanation without silent fallback.
    """
    spec = QuerySpec(
        operation="sum",
        column="non_existent_column",
        filters=[]
    )
    res = execute_query(spec, sample_sales_df)
    assert res.success is False
    assert "The dataset does not contain a field corresponding to" in res.error


def test_invalid_filter_column_protection(sample_sales_df):
    """If filter column does not exist, return clear error."""
    spec = QuerySpec(
        operation="sum",
        column="profit",
        filters=[
            FilterSpec(column="invalid_filter_col", operator="equals", value="xyz")
        ]
    )
    res = execute_query(spec, sample_sales_df)
    assert res.success is False
    assert "The dataset does not contain a field corresponding to" in res.error


# ==============================================================================
# TEST 5: Schema-Agnostic Query Routing & Context Inheritance
# ==============================================================================

def test_fallback_router_canada_filter(sample_sales_df, sample_schema):
    """Test schema-agnostic extraction of Canada filter for profit."""
    resp = process_query_with_llm(
        "What is the total profit for Canada?",
        schema=sample_schema,
        profile={},
        df=sample_sales_df
    )
    assert resp.type == "data_query"
    query = resp.primary_query
    assert query.column == "profit"
    assert len(query.filters) == 1
    assert query.filters[0].column == "country_region"
    assert query.filters[0].value.lower() == "canada"

    # Execution verification
    exec_res = execute_query(query, sample_sales_df)
    assert exec_res.success is True
    assert exec_res.result == 300.0


# ==============================================================================
# TEST 6: Multi-Turn Analytical Follow-Up Sequence (TESTS 1 to 6 in Prompt)
# ==============================================================================

def test_full_follow_up_pipeline_sequence(sample_sales_df, sample_schema):
    """
    Tests the complete sequence from USER_REQUEST STEP 16:
    Turn 1: "What is the total profit?"
    Turn 2: "What is the total profit for Canada?"
    Turn 3: "Break this down by ship_mode."
    Turn 4: "What about Germany?"
    Turn 5: "Only First Class."
    """
    # TURN 1: "What is the total profit?"
    resp1 = process_query_with_llm(
        "What is the total profit?",
        schema=sample_schema,
        profile={},
        df=sample_sales_df
    )
    assert resp1.type == "data_query"
    q1 = resp1.primary_query
    res1 = execute_query(q1, sample_sales_df)
    assert res1.success is True
    assert res1.result == 2100.0
    assert res1.metadata["filtered_rows"] == 6

    # TURN 2: "What is the total profit for Canada?"
    resp2 = process_query_with_llm(
        "What is the total profit for Canada?",
        schema=sample_schema,
        profile={},
        df=sample_sales_df,
        previous_query=res1.metadata["query_plan"]
    )
    assert resp2.type == "data_query"
    q2 = resp2.primary_query
    res2 = execute_query(q2, sample_sales_df)
    assert res2.success is True
    # The result MUST be independently calculated from the filtered dataframe:
    assert res2.result == 300.0
    assert res2.metadata["filtered_rows"] == 2
    assert res2.metadata["rows_before_filter"] == 6
    assert res2.metadata["rows_after_filter"] == 2

    # TURN 3: Follow-up: "Break this down by ship_mode."
    # Preserves metric=profit, filter=country_region=Canada, adds group_by=[ship_mode]
    resp3 = process_query_with_llm(
        "Break this down by ship_mode.",
        schema=sample_schema,
        profile={},
        df=sample_sales_df,
        previous_query=res2.metadata["query_plan"]
    )
    assert resp3.type == "data_query"
    q3 = resp3.primary_query
    assert "ship_mode" in q3.group_by
    res3 = execute_query(q3, sample_sales_df)
    assert res3.success is True
    assert res3.metadata["filtered_rows"] == 2
    group_map = {r["ship_mode"]: r["profit"] for r in res3.result}
    assert group_map["Regular Air"] == 100.0
    assert group_map["First Class"] == 200.0

    # TURN 4: Follow-up: "What about Germany?"
    # Replaces Canada with Germany, preserves metric=profit, preserves group_by=[ship_mode]
    resp4 = process_query_with_llm(
        "What about Germany?",
        schema=sample_schema,
        profile={},
        df=sample_sales_df,
        previous_query=res3.metadata["query_plan"]
    )
    assert resp4.type == "data_query"
    q4 = resp4.primary_query
    res4 = execute_query(q4, sample_sales_df)
    assert res4.success is True
    assert res4.metadata["filtered_rows"] == 3
    germany_group_map = {r["ship_mode"]: r["profit"] for r in res4.result}
    assert germany_group_map["Regular Air"] == 300.0
    assert germany_group_map["First Class"] == 900.0

    # TURN 5: Follow-up: "Only First Class."
    # Adds ship_mode=First Class filter to Germany
    resp5 = process_query_with_llm(
        "Only First Class.",
        schema=sample_schema,
        profile={},
        df=sample_sales_df,
        previous_query=res4.metadata["query_plan"]
    )
    assert resp5.type == "data_query"
    q5 = resp5.primary_query
    res5 = execute_query(q5, sample_sales_df)
    assert res5.success is True
    # 400 + 500 = 900.0
    if isinstance(res5.result, list):
        assert sum(r["profit"] for r in res5.result) == 900.0
    else:
        assert res5.result == 900.0
    assert res5.metadata["filtered_rows"] == 2

