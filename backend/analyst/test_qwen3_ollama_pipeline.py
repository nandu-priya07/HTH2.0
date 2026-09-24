"""
Complete test suite for Qwen3:8b Ollama local query-processing system.
"""

import pytest
import pandas as pd
from pathlib import Path
from fastapi.testclient import TestClient

from analyst.query_processor import process_query_with_llm
from analyst.query_executor import execute_query
from analyst.models import LLMResponse, QueryResult, ResponseType
from file_processing.schema_inference import infer_schema
from file_processing.data_profiler import profile_dataset
from main import app


@pytest.fixture(scope="module")
def superstore_data():
    csv_path = Path(__file__).resolve().parent.parent / "uploads" / "processed" / "f790d82c-da5f-47b1-a9db-f1e88ab45f52.csv"
    if not csv_path.exists():
        processed_dir = Path(__file__).resolve().parent.parent / "uploads" / "processed"
        csv_files = sorted(list(processed_dir.glob("*.csv")), key=lambda p: p.stat().st_size, reverse=True)
        if csv_files:
            csv_path = csv_files[0]
        else:
            pytest.skip("No processed dataset found for test execution")

    df = pd.read_csv(csv_path)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    return df, schema, profile


def test_total_sales_query(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("What is the total sales?", schema, profile, df)
    assert resp.type == "data_query"
    assert resp.query.operation == "sum"
    assert resp.query.column == "sales"

    res = execute_query(resp.query, df)
    assert res.success is True
    assert res.type == "data_result"
    assert res.result > 0


def test_sales_by_region_query(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("Show sales by region.", schema, profile, df)
    assert resp.type == "data_query"
    assert resp.query.operation == "sum"
    assert resp.query.column == "sales"
    assert resp.query.group_by == ["region"]

    res = execute_query(resp.query, df)
    assert res.success is True
    assert len(res.result) == 4


def test_list_unique_country_regions(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("List the unique country regions.", schema, profile, df)
    assert resp.type == "data_query"
    assert resp.query.operation == "distinct"
    assert resp.query.column == "country_region"

    res = execute_query(resp.query, df)
    assert res.success is True
    assert set(res.result) == {"United States", "Canada"}


def test_critical_regression_country_regions(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("list the unique country_regions", schema, profile, df)
    assert resp.type == "data_query"
    assert resp.query.operation == "distinct"
    assert resp.query.column == "country_region"
    assert resp.query.operation != "sum"

    res = execute_query(resp.query, df)
    assert res.success is True
    assert isinstance(res.result, list)


def test_how_many_unique_customers(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("How many unique customers?", schema, profile, df)
    assert resp.type == "data_query"
    assert resp.query.operation == "count_distinct"
    assert resp.query.column in ("customer_id", "customer_name")

    res = execute_query(resp.query, df)
    assert res.success is True
    assert res.result == df[resp.query.column].nunique()


def test_average_profit(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("What is the average profit?", schema, profile, df)
    assert resp.type == "data_query"
    assert resp.query.operation in ("average", "mean")
    assert resp.query.column == "profit"

    res = execute_query(resp.query, df)
    assert res.success is True
    assert res.result > 0


def test_top_5_products_by_profit(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("Show the top 5 products by profit.", schema, profile, df)
    assert resp.type == "data_query"
    assert resp.query.operation == "sum"
    assert resp.query.column == "profit"
    assert resp.query.limit == 5

    res = execute_query(resp.query, df)
    assert res.success is True
    assert len(res.result) <= 5


def test_sales_in_2024(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("Show sales in 2024.", schema, profile, df)
    assert resp.type == "data_query"
    assert resp.query.operation == "sum"
    assert resp.query.column == "sales"
    assert len(resp.query.filters) >= 1

    res = execute_query(resp.query, df)
    assert res.success is True


def test_sales_for_technology(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("Show total sales for Technology.", schema, profile, df)
    assert resp.type == "data_query"
    assert resp.query.operation == "sum"
    assert resp.query.column == "sales"
    assert len(resp.query.filters) >= 1

    res = execute_query(resp.query, df)
    assert res.success is True


def test_direct_answer_hello(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("Hello", schema, profile, df)
    assert resp.type == "direct_answer"
    assert resp.query is None
    assert len(resp.answer) > 0


def test_direct_answer_what_can_you_do(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("What can you do?", schema, profile, df)
    assert resp.type == "direct_answer"
    assert resp.query is None
    assert len(resp.answer) > 0


def test_direct_answer_what_is_profit(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("What is profit?", schema, profile, df)
    assert resp.type == "direct_answer"
    assert resp.query is None
    assert len(resp.answer) > 0


def test_clarification_sales(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("sales?", schema, profile, df)
    assert resp.type == "clarification"
    assert resp.query is None
    assert "sales" in resp.answer.lower()


def test_clarification_show_locations(superstore_data):
    df, schema, profile = superstore_data
    resp = process_query_with_llm("show locations", schema, profile, df)
    assert resp.type == "clarification"
    assert resp.query is None
    assert "location" in resp.answer.lower() or "which" in resp.answer.lower()


def test_api_endpoint_queries(superstore_data):
    client = TestClient(app)

    # 1. Data query
    r1 = client.post("/api/query", json={"question": "show sales by region"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["type"] == "data_result"
    assert d1["query"]["operation"] == "sum"
    assert len(d1["result"]) == 4

    # 2. Direct answer
    r2 = client.post("/api/query", json={"question": "Hello"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["type"] == "direct_answer"
    assert len(d2["answer"]) > 0

    # 3. Clarification
    r3 = client.post("/api/query", json={"question": "sales?"})
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["type"] == "clarification"
    assert "sales" in d3["answer"].lower()
