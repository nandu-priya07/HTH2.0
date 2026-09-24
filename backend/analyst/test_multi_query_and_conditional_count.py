"""
Comprehensive test suite for Multi-Column and Multi-Operation Query Processing.
Verifies:
1. Multi-column conditional counts ('list the A grade count in each subject code')
2. Multiple independent operations in one query ('what is the total profit and average profit')
3. 3-operation query ('give me total sales, average sales and unique customers')
4. Grouped queries ('what is total sales by region')
5. Count distinct queries ('how many unique customers are there')
6. Distinct list queries ('list unique countries')
7. Conjunction query clarification ('count students who got A in every subject')
8. Deterministic dataset-agnostic execution
"""

import pytest
import pandas as pd
from fastapi.testclient import TestClient

from analyst.models import QuerySpec, ConditionSpec, LLMResponse, ResponseType
from analyst.query_processor import process_query_with_llm
from analyst.query_executor import execute_query, execute_queries
from analyst.validator import validate_query_spec, validate_queries
from file_processing.schema_inference import infer_schema
from file_processing.data_profiler import profile_dataset
from storage.dataset_manager import register_dataset
from main import app


@pytest.fixture
def student_grades_df():
    """Sample dataset representing student course grades across multiple subject code columns."""
    data = {
        "student_id": ["STU001", "STU002", "STU003", "STU004", "STU005", "STU006", "STU007", "STU008", "STU009", "STU010"],
        "student_name": ["Alice", "Bob", "Charlie", "David", "Eva", "Frank", "Grace", "Hannah", "Ian", "Jack"],
        "CS23333": ["A", "A", "B", "A", "C", "A", "B", "A", "A", "A"],  # 7 A's
        "CS23331": ["B", "A", "B", "B", "C", "B", "A", "C", "B", "B"],  # 2 A's
        "CS23332": ["A", "B", "A", "C", "B", "A", "B", "A", "B", "C"],  # 4 A's
        "AI23331": ["A", "A", "A", "A", "B", "B", "A", "B", "C", "A"],  # 6 A's
        "MA23313": ["B", "B", "C", "A", "B", "C", "B", "A", "B", "B"],  # 2 A's
        "MC23112": ["A", "C", "B", "B", "A", "B", "C", "B", "B", "A"],  # 3 A's
        "IT23231": ["B", "A", "A", "B", "B", "A", "B", "B", "C", "A"],  # 4 A's
        "EE23133": ["C", "B", "B", "A", "B", "B", "A", "B", "C", "B"]   # 2 A's
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    return df, schema, profile


@pytest.fixture
def sales_df():
    """Standard business dataset with sales, profit, region, and customers."""
    data = {
        "order_id": [1, 2, 3, 4, 5, 6],
        "customer_id": ["C1", "C2", "C1", "C3", "C2", "C4"],
        "region": ["West", "East", "West", "Central", "South", "East"],
        "country": ["United States", "United States", "Canada", "United States", "Canada", "Mexico"],
        "sales": [100.0, 200.0, 150.0, 300.0, 250.0, 400.0],
        "profit": [20.0, 50.0, 30.0, 70.0, 60.0, 90.0]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    return df, schema, profile


# --------------------------------------------------------------------------
# Test 1: Multi-column conditional count (A grade count in each subject code)
# --------------------------------------------------------------------------

def test_multi_column_conditional_count_grades(student_grades_df):
    df, schema, profile = student_grades_df

    resp = process_query_with_llm("list the A grade count in each subject code", schema, profile, df)
    assert resp.type == "data_query"
    queries = resp.all_queries
    assert len(queries) >= 1

    q = queries[0]
    assert q.operation == "conditional_count"
    # Must NOT select only one column! Must contain multiple subject columns.
    assert len(q.columns) >= 6
    assert "CS23333" in q.columns
    assert "AI23331" in q.columns
    assert q.condition is not None
    cond_val = q.condition.get("value") if isinstance(q.condition, dict) else q.condition.value
    assert str(cond_val).upper() == "A"

    # Execute and verify exact calculated counts
    exec_res = execute_query(q, df)
    assert exec_res.success is True
    assert len(exec_res.result) == len(q.columns)

    counts_map = {item["column"]: item["count"] for item in exec_res.result}
    assert counts_map["CS23333"] == 7
    assert counts_map["CS23331"] == 2
    assert counts_map["CS23332"] == 4
    assert counts_map["AI23331"] == 6


# --------------------------------------------------------------------------
# Test 2: Two independent operations in one query (total profit and average profit)
# --------------------------------------------------------------------------

def test_two_queries_total_and_average_profit(sales_df):
    df, schema, profile = sales_df

    resp = process_query_with_llm("what is the total profit and average profit", schema, profile, df)
    assert resp.type == "data_query"
    queries = resp.all_queries
    assert len(queries) == 2

    ops = [q.operation for q in queries]
    assert "sum" in ops
    assert ("average" in ops or "mean" in ops)

    exec_res = execute_queries(queries, df)
    assert exec_res.success is True
    assert exec_res.scalars is not None
    assert len(exec_res.scalars) == 2

    # Total profit = 20 + 50 + 30 + 70 + 60 + 90 = 320.0
    # Average profit = 320 / 6 = 53.3333
    scalars_map = {s["aggregation"]: s["value"] for s in exec_res.scalars}
    assert scalars_map["sum"] == 320.0
    assert abs(scalars_map.get("average", scalars_map.get("mean", 0)) - 53.3333) < 0.01


# --------------------------------------------------------------------------
# Test 3: Three independent operations (total sales, average sales, unique customers)
# --------------------------------------------------------------------------

def test_three_queries_sales_avg_and_unique_customers(sales_df):
    df, schema, profile = sales_df

    resp = process_query_with_llm("give me total sales, average sales and unique customers", schema, profile, df)
    assert resp.type == "data_query"
    queries = resp.all_queries
    assert len(queries) == 3

    exec_res = execute_queries(queries, df)
    assert exec_res.success is True
    assert len(exec_res.scalars) == 3

    # Total sales = 1400.0, Average sales = 233.33, Unique customers = 4 (C1, C2, C3, C4)
    scalars_map = {s["aggregation"]: s["value"] for s in exec_res.scalars}
    assert scalars_map["sum"] == 1400.0
    assert abs(scalars_map.get("average", scalars_map.get("mean", 0)) - 233.3333) < 0.01
    assert scalars_map["count_distinct"] == 4


# --------------------------------------------------------------------------
# Test 4: Grouped query (total sales by region)
# --------------------------------------------------------------------------

def test_single_grouped_query_sales_by_region(sales_df):
    df, schema, profile = sales_df

    resp = process_query_with_llm("what is total sales by region", schema, profile, df)
    assert resp.type == "data_query"
    queries = resp.all_queries
    assert len(queries) == 1

    q = queries[0]
    assert q.operation == "sum"
    assert q.column == "sales"
    assert q.group_by == ["region"]

    exec_res = execute_query(q, df)
    assert exec_res.success is True
    assert len(exec_res.result) == 4


# --------------------------------------------------------------------------
# Test 5: Unique count (how many unique customers are there)
# --------------------------------------------------------------------------

def test_how_many_unique_customers(sales_df):
    df, schema, profile = sales_df

    resp = process_query_with_llm("how many unique customers are there", schema, profile, df)
    assert resp.type == "data_query"
    queries = resp.all_queries
    assert len(queries) == 1

    q = queries[0]
    assert q.operation == "count_distinct"
    assert q.column == "customer_id"

    exec_res = execute_query(q, df)
    assert exec_res.success is True
    assert exec_res.scalar["value"] == 4


# --------------------------------------------------------------------------
# Test 6: Distinct list (list unique countries)
# --------------------------------------------------------------------------

def test_list_unique_countries(sales_df):
    df, schema, profile = sales_df

    resp = process_query_with_llm("list unique countries", schema, profile, df)
    assert resp.type == "data_query"
    queries = resp.all_queries
    assert len(queries) == 1

    q = queries[0]
    assert q.operation == "distinct"
    assert q.column == "country"

    exec_res = execute_query(q, df)
    assert exec_res.success is True
    assert set(exec_res.result) == {"United States", "Canada", "Mexico"}


# --------------------------------------------------------------------------
# Test 7: Clarification for all-subject conjunction request
# --------------------------------------------------------------------------

def test_conjunction_clarification_students_got_a_in_every_subject(student_grades_df):
    df, schema, profile = student_grades_df

    resp = process_query_with_llm("count students who got A in every subject", schema, profile, df)
    assert resp.type == "clarification"
    assert resp.query is None
    assert len(resp.answer) > 0


# --------------------------------------------------------------------------
# Test 8: End-to-End API endpoint test with student grades
# --------------------------------------------------------------------------

def test_api_endpoint_multi_column_conditional_count(student_grades_df):
    df, schema, profile = student_grades_df
    ds_id = "test_grades_dataset_id"
    register_dataset(ds_id, {
        "dataset_id": ds_id,
        "filename": "grades.csv",
        "data": df,
        "schema": schema,
        "profile": profile,
        "result": {
            "dataset_id": ds_id,
            "schema": schema,
            "profile": profile,
            "metadata": {"rows": len(df), "columns": len(df.columns)}
        }
    })

    client = TestClient(app)
    response = client.post("/api/query", json={
        "question": "list the A grade count in each subject code",
        "dataset_id": ds_id
    })

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "data_result"
    assert data["status"] == "success"
    assert len(data["result"]) >= 6
    assert data.get("visualization") is not None
    assert data["visualization"]["type"] == "bar"
