"""
Comprehensive Regression Test Suite for Multi-Grade and Value Distribution Questions.
Tests:
TEST 1: "how many A grades in each subject" -> conditional_count, value = A
TEST 2: "how many O grades in each subject" -> conditional_count, value = O
TEST 3: "each grade count for each subjects" -> multi_column_value_distribution, condition = null
TEST 4: "grade distribution for each subject" -> multi_column_value_distribution, condition = null
TEST 5: "count every grade across subjects" -> multi_column_value_distribution, condition = null
TEST 6: "only B grade for each subject" -> conditional_count, value = B
TEST 7: "show A and B counts for each subject" -> multi_column_value_distribution, condition = [A, B]
TEST 8: Follow-up conversational context: "each grade count for each subject" -> "only B"
TEST 9: Single column distribution: "grade distribution for cs23333" -> value_distribution
TEST 10: Deterministic Execution: exact counts and pivot table generation
TEST 11: End-to-end API verification via /api/query
"""

import pytest
import pandas as pd
from fastapi.testclient import TestClient

from analyst.models import QuerySpec, ConditionSpec, LLMResponse
from analyst.query_processor import process_query_with_llm
from analyst.query_executor import execute_query
from analyst.validator import validate_query_spec
from chat.context_resolver import ContextResolver
from file_processing.schema_inference import infer_schema
from file_processing.data_profiler import profile_dataset
from storage.dataset_manager import register_dataset
from main import app


@pytest.fixture
def sem_iii_df():
    """
    Simulates SEM III.xlsx with multiple subject columns containing distinct grades
    (O, A+, A, B+, B, C, D, F, RA).
    """
    data = {
        "student_id": [f"STU{i:03d}" for i in range(1, 11)],
        "student_name": ["Alice", "Bob", "Charlie", "David", "Eva", "Frank", "Grace", "Hannah", "Ian", "Jack"],
        "cs23333": ["O", "A+", "A", "A", "B+", "B", "C", "D", "F", "RA"],
        "cs23331": ["A", "A", "O", "B+", "B+", "B", "RA", "A+", "O", "A"],
        "cs23332": ["B", "B+", "A+", "O", "A", "A", "B", "C", "RA", "F"],
        "ai23331": ["O", "O", "A+", "A+", "A", "B+", "B", "B", "C", "RA"],
        "ma23313": ["A", "B+", "B", "C", "D", "RA", "O", "A+", "A", "B+"],
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    return df, schema, profile


# --------------------------------------------------------------------------
# TEST 1: "how many A grades in each subject" -> conditional_count, value = A
# --------------------------------------------------------------------------
def test_1_single_value_count_a_grades(sem_iii_df):
    df, schema, profile = sem_iii_df
    resp = process_query_with_llm("how many A grades in each subject", schema, profile, df)
    assert resp.type == "data_query"
    q = resp.query
    assert q.operation == "conditional_count"
    assert q.condition is not None
    cond_val = q.condition.get("value") if isinstance(q.condition, dict) else q.condition.value
    assert str(cond_val).upper() == "A"
    assert len(q.columns) >= 4


# --------------------------------------------------------------------------
# TEST 2: "how many O grades in each subject" -> conditional_count, value = O
# --------------------------------------------------------------------------
def test_2_single_value_count_o_grades(sem_iii_df):
    df, schema, profile = sem_iii_df
    resp = process_query_with_llm("how many O grades in each subject", schema, profile, df)
    assert resp.type == "data_query"
    q = resp.query
    assert q.operation == "conditional_count"
    assert q.condition is not None
    cond_val = q.condition.get("value") if isinstance(q.condition, dict) else q.condition.value
    assert str(cond_val).upper() == "O"


# --------------------------------------------------------------------------
# TEST 3: "each grade count for each subjects" -> multi_column_value_distribution, condition = null
# --------------------------------------------------------------------------
def test_3_multi_column_distribution_each_grade_count(sem_iii_df):
    df, schema, profile = sem_iii_df
    resp = process_query_with_llm("each grade count for each subjects", schema, profile, df)
    assert resp.type == "data_query"
    q = resp.query
    assert q.operation == "multi_column_value_distribution"
    # CRITICAL: condition MUST be None (no hardcoded 'A'!)
    assert q.condition is None
    # CRITICAL: group_by MUST NOT contain subject columns
    assert q.group_by == []
    # Columns must contain detected subject columns
    assert len(q.columns) >= 4
    assert "cs23333" in q.columns
    assert "cs23331" in q.columns


# --------------------------------------------------------------------------
# TEST 4: "grade distribution for each subject" -> multi_column_value_distribution
# --------------------------------------------------------------------------
def test_4_grade_distribution_for_each_subject(sem_iii_df):
    df, schema, profile = sem_iii_df
    resp = process_query_with_llm("grade distribution for each subject", schema, profile, df)
    assert resp.type == "data_query"
    q = resp.query
    assert q.operation == "multi_column_value_distribution"
    assert q.condition is None
    assert len(q.columns) >= 4


# --------------------------------------------------------------------------
# TEST 5: "count every grade across subjects" -> multi_column_value_distribution
# --------------------------------------------------------------------------
def test_5_count_every_grade_across_subjects(sem_iii_df):
    df, schema, profile = sem_iii_df
    resp = process_query_with_llm("count every grade across subjects", schema, profile, df)
    assert resp.type == "data_query"
    q = resp.query
    assert q.operation == "multi_column_value_distribution"
    assert q.condition is None
    assert len(q.columns) >= 4


# --------------------------------------------------------------------------
# TEST 6: "only B grade for each subject" -> conditional_count, value = B
# --------------------------------------------------------------------------
def test_6_only_b_grade_for_each_subject(sem_iii_df):
    df, schema, profile = sem_iii_df
    resp = process_query_with_llm("only B grade for each subject", schema, profile, df)
    assert resp.type == "data_query"
    q = resp.query
    assert q.operation == "conditional_count"
    assert q.condition is not None
    cond_val = q.condition.get("value") if isinstance(q.condition, dict) else q.condition.value
    assert str(cond_val).upper() == "B"


# --------------------------------------------------------------------------
# TEST 7: "show A and B counts for each subject" -> multi_column_value_distribution, condition = [A, B]
# --------------------------------------------------------------------------
def test_7_multi_grade_subset_a_and_b(sem_iii_df):
    df, schema, profile = sem_iii_df
    resp = process_query_with_llm("show A and B counts for each subject", schema, profile, df)
    assert resp.type == "data_query"
    q = resp.query
    assert q.operation == "multi_column_value_distribution"
    assert q.condition is not None
    cond_vals = q.condition.get("value") if isinstance(q.condition, dict) else q.condition.value
    if isinstance(cond_vals, list):
        assert set(cond_vals) == {"A", "B"}
    else:
        assert str(cond_vals).upper() in ("A", "B")


# --------------------------------------------------------------------------
# TEST 8: Follow-up: "each grade count for each subject" -> "only B"
# --------------------------------------------------------------------------
def test_8_conversational_follow_up_narrow_to_b(sem_iii_df):
    df, schema, profile = sem_iii_df
    resolver = ContextResolver()

    # Step 1: Initial query
    initial_spec = QuerySpec(
        operation="multi_column_value_distribution",
        columns=["cs23333", "cs23331", "cs23332", "ai23331", "ma23313"],
        condition=None,
        file_id="test_file_sem3"
    )

    # Step 2: Follow-up question "only B"
    messages = [
        {
            "role": "user",
            "content": "each grade count for each subjects"
        },
        {
            "role": "assistant",
            "content": "Calculated grade distribution across 5 subjects",
            "query_spec": initial_spec.to_dict(),
            "intent": {
                "operation": "multi_column_value_distribution",
                "scope": "all_subject_columns",
                "condition": None
            },
            "file_id": "test_file_sem3"
        }
    ]
    files = [{"file_id": "test_file_sem3", "filename": "SEM III.xlsx"}]

    inherited_spec, compact_ctx, selected_fid = resolver.resolve_context(
        chat_id="test_chat_id",
        current_query="only B",
        messages=messages,
        files=files
    )

    assert inherited_spec is not None
    assert inherited_spec.operation == "conditional_count"
    assert inherited_spec.columns == initial_spec.columns
    assert inherited_spec.condition is not None
    cond_val = inherited_spec.condition.get("value") if isinstance(inherited_spec.condition, dict) else inherited_spec.condition.value
    assert str(cond_val).upper() == "B"
    assert selected_fid == "test_file_sem3"


# --------------------------------------------------------------------------
# TEST 9: Single column distribution: "grade distribution for cs23333" -> value_distribution
# --------------------------------------------------------------------------
def test_9_single_column_grade_distribution(sem_iii_df):
    df, schema, profile = sem_iii_df
    resp = process_query_with_llm("grade distribution for cs23333", schema, profile, df)
    assert resp.type == "data_query"
    q = resp.query
    assert q.operation in ("value_distribution", "multi_column_value_distribution")
    assert q.condition is None
    cols = q.columns or [q.column]
    assert "cs23333" in cols


# --------------------------------------------------------------------------
# TEST 10: Deterministic Execution: exact counts and pivot table generation
# --------------------------------------------------------------------------
def test_10_deterministic_execution_grade_distribution(sem_iii_df):
    df, schema, profile = sem_iii_df
    spec = QuerySpec(
        operation="multi_column_value_distribution",
        columns=["cs23333", "cs23331"],
        condition=None
    )

    # 1. Validation
    is_valid, err = validate_query_spec(spec, df, schema)
    assert is_valid is True, err

    # 2. Execution
    exec_res = execute_query(spec, df)
    assert exec_res.success is True
    assert exec_res.result is not None
    assert isinstance(exec_res.result, list)

    # Verify records have subject, grade, count
    sample_rec = exec_res.result[0]
    assert "subject" in sample_rec
    assert "grade" in sample_rec
    assert "count" in sample_rec

    # Verify pivot table headers and rows
    table = exec_res.table
    assert table is not None
    assert table["headers"][0] == "Subject"
    # Discovered distinct grades present in data
    assert "O" in table["headers"]
    assert "A" in table["headers"]
    assert "RA" in table["headers"]

    # Verify exact counts for cs23333
    cs23333_records = {r["grade"]: r["count"] for r in exec_res.result if r["subject"] == "cs23333"}
    assert cs23333_records["O"] == 1
    assert cs23333_records["A"] == 2
    assert cs23333_records["RA"] == 1


# --------------------------------------------------------------------------
# TEST 11: End-to-End API verification with /api/query
# --------------------------------------------------------------------------
def test_11_api_endpoint_each_grade_count(sem_iii_df):
    df, schema, profile = sem_iii_df
    ds_id = "test_sem_iii_dataset"
    register_dataset(ds_id, {
        "dataset_id": ds_id,
        "filename": "SEM III.xlsx",
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
        "question": "each grade count for each subjects",
        "dataset_id": ds_id
    })

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "data_result"
    assert data["status"] == "success"

    # Query Spec verification
    q_spec = data.get("query_spec") or {}
    assert q_spec.get("operation") == "multi_column_value_distribution"
    assert q_spec.get("condition") is None
    assert q_spec.get("group_by") == []

    # Result data verification
    results = data.get("result") or []
    assert len(results) > 0
    assert "subject" in results[0]
    assert "grade" in results[0]
    assert "count" in results[0]

    # Pivot Table verification
    table = data.get("table") or {}
    assert "headers" in table
    assert table["headers"][0] == "Subject"
    assert len(table.get("rows", [])) >= 4

    # Visualization verification
    vis = data.get("visualization") or {}
    assert vis.get("type") in ("bar", "table")
    if vis.get("type") == "bar":
        assert vis.get("orientation") == "horizontal"
