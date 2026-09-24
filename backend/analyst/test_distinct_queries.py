"""
Comprehensive test suite for distinct, count_distinct, column resolution, and regression queries.
"""

import pytest
import pandas as pd
from pathlib import Path

from analyst.question_parser import parse_query
from analyst.query_executor import execute_query
from analyst.query_types import QueryStatus, ResultType
from file_processing.schema_inference import infer_schema
from file_processing.data_profiler import profile_dataset


@pytest.fixture(scope="module")
def dataset_context():
    csv_path = Path(__file__).resolve().parent.parent / "uploads" / "processed" / "f790d82c-da5f-47b1-a9db-f1e88ab45f52.csv"
    if not csv_path.exists():
        # Fallback to any csv in processed
        processed_dir = Path(__file__).resolve().parent.parent / "uploads" / "processed"
        csv_files = list(processed_dir.glob("*.csv"))
        if csv_files:
            csv_path = csv_files[0]
        else:
            pytest.skip("No processed dataset found for test execution")

    df = pd.read_csv(csv_path)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    return df, schema, profile


def test_distinct_country_regions(dataset_context):
    df, schema, profile = dataset_context
    queries = [
        "list the unique country_regions",
        "list unique country regions",
        "show unique country regions",
        "show distinct country regions",
        "display unique countries",
        "what are the unique country regions"
    ]
    for q in queries:
        spec = parse_query(q, schema, profile)
        assert spec.status == QueryStatus.VALID, f"Failed for {q}: {spec.message}"
        assert spec.operation == "distinct", f"Operation mismatch for {q}: {spec.operation}"
        assert spec.column == "country_region", f"Column mismatch for {q}: {spec.column}"
        assert spec.metric is None
        assert spec.aggregation is None

        res = execute_query(spec, df)
        assert res.success is True
        assert res.result_type == ResultType.LIST
        assert res.column == "country_region"
        assert isinstance(res.values, list)
        assert len(res.values) > 0
        assert res.count == len(res.values)


def test_distinct_regions(dataset_context):
    df, schema, profile = dataset_context
    spec = parse_query("list all distinct regions", schema, profile)
    assert spec.status == QueryStatus.VALID
    assert spec.operation == "distinct"
    assert spec.column == "region"
    assert spec.metric is None

    res = execute_query(spec, df)
    assert res.success is True
    assert res.result_type == ResultType.LIST
    assert res.column == "region"
    assert set(res.values) == {"Central", "East", "South", "West"}


def test_count_distinct_country_regions(dataset_context):
    df, schema, profile = dataset_context
    queries = [
        "how many unique country regions",
        "count unique country regions",
        "number of distinct country regions"
    ]
    for q in queries:
        spec = parse_query(q, schema, profile)
        assert spec.status == QueryStatus.VALID, f"Failed for {q}: {spec.message}"
        assert spec.operation == "count_distinct", f"Operation mismatch for {q}: {spec.operation}"
        assert spec.column == "country_region", f"Column mismatch for {q}: {spec.column}"

        res = execute_query(spec, df)
        assert res.success is True
        assert res.result_type == ResultType.SCALAR
        assert res.value == 2


def test_missing_operation_clarification(dataset_context):
    df, schema, profile = dataset_context
    spec = parse_query("country_region", schema, profile)
    assert spec.status == QueryStatus.NEEDS_CLARIFICATION
    assert spec.reason == "MISSING_OPERATION"
    assert spec.detected_column == "country_region"
    assert "What would you like to know about country_region?" in (spec.message or "")


def test_distinct_with_filter(dataset_context):
    df, schema, profile = dataset_context
    spec = parse_query("list unique country regions in 2024", schema, profile)
    assert spec.status == QueryStatus.VALID
    assert spec.operation == "distinct"
    assert spec.column == "country_region"
    assert len(spec.filters) >= 1
    assert spec.filters[0].column in ("order_date", "ship_date")

    res = execute_query(spec, df)
    assert res.success is True
    assert res.result_type == ResultType.LIST
    assert isinstance(res.values, list)


def test_regression_queries(dataset_context):
    df, schema, profile = dataset_context

    # 1. Total sales
    spec1 = parse_query("total sales", schema, profile)
    assert spec1.status == QueryStatus.VALID
    assert spec1.operation == "aggregation"
    assert spec1.aggregation == "sum"
    res1 = execute_query(spec1, df)
    assert res1.success is True
    assert res1.result_type == ResultType.SCALAR
    assert res1.value > 0

    # 2. Average profit
    spec2 = parse_query("average profit", schema, profile)
    assert spec2.status == QueryStatus.VALID
    assert spec2.operation == "aggregation"
    assert spec2.aggregation in ("mean", "average")
    res2 = execute_query(spec2, df)
    assert res2.success is True
    assert res2.result_type == ResultType.SCALAR

    # 3. Sales by region
    spec3 = parse_query("sales by region", schema, profile)
    assert spec3.status == QueryStatus.VALID
    assert spec3.operation == "group_by"
    assert spec3.group_by == ["region"]
    res3 = execute_query(spec3, df)
    assert res3.success is True
    assert res3.result_type == ResultType.TABLE
    assert len(res3.rows) == 4

    # 4. Top 5 products by sales
    spec4 = parse_query("top 5 products by sales", schema, profile)
    assert spec4.status == QueryStatus.VALID
    assert spec4.operation == "group_by"
    assert spec4.metric == "sales"
    assert spec4.limit == 5
    res4 = execute_query(spec4, df)
    assert res4.success is True
    assert len(res4.rows) <= 5

    # 5. Sales in 2024
    spec5 = parse_query("sales in 2024", schema, profile)
    assert spec5.status == QueryStatus.VALID
    assert spec5.operation == "aggregation"
    assert spec5.metric == "sales"
    assert len(spec5.filters) >= 1
    res5 = execute_query(spec5, df)
    assert res5.success is True

    # 6. Sales by region in 2024
    spec6 = parse_query("sales by region in 2024", schema, profile)
    assert spec6.status == QueryStatus.VALID
    assert spec6.operation == "group_by"
    assert spec6.group_by == ["region"]
    assert len(spec6.filters) >= 1
    res6 = execute_query(spec6, df)
    assert res6.success is True
    assert res6.result_type == ResultType.TABLE

    # 7. Count customers
    spec7 = parse_query("count customers", schema, profile)
    assert spec7.status == QueryStatus.VALID
    assert spec7.operation == "count"
    res7 = execute_query(spec7, df)
    assert res7.success is True
    assert res7.result_type == ResultType.SCALAR

    # 8. Count unique customers
    spec8 = parse_query("count unique customers", schema, profile)
    assert spec8.status == QueryStatus.VALID
    assert spec8.operation == "count_distinct"
    assert spec8.column in ("customer_id", "customer_name")
    res8 = execute_query(spec8, df)
    assert res8.success is True
    assert res8.result_type == ResultType.SCALAR
    assert res8.value == df[spec8.column].nunique()
