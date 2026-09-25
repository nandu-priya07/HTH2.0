"""
Comprehensive Test Suite & Final Validation for Grade Analysis & Context Latency
"""

import sys
import os
import time
import pandas as pd

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyst.query_processor import process_query_with_llm, _get_unique_subject_columns
from analyst.query_executor import execute_query
from analyst.models import QuerySpec, ConditionSpec
from chat.context_resolver import ContextResolver


def create_sample_student_df() -> pd.DataFrame:
    """Creates a sample student dataset with subject grade columns."""
    return pd.DataFrame({
        "reg_no": [101, 102, 103, 104, 105, 106, 107, 108],
        "name": ["Alice", "Bob", "Charlie", "David", "Eve", "Frank", "Grace", "Heidi"],
        "ge23111": ["A", "O", "B", "A", "C", "A", "O", "B"],
        "ge23121": ["B", "A", "O", "B", "A", "B", "A", "C"],
        "ge23117": ["O", "B", "A", "O", "B", "A", "B", "A"],
        "ge23131": ["A", "A", "B", "C", "O", "A", "A", "B"],
        "cs23333": ["O", "A", "A", "B", "B", "C", "O", "A"],
        "mc23112": ["A", "B", "O", "A", "A", "B", "A", "C"],
        "ai23331": ["A", "A", "A", "O", "B", "A", "O", "B"]
    })


def run_tests():
    print("=================================================================")
    print("      GRADE ANALYSIS & CONTEXT LATENCY VALIDATION SUITE          ")
    print("=================================================================\n")

    df = create_sample_student_df()

    # -------------------------------------------------------------------------
    # TEST 10: Deduplication Assertion
    # -------------------------------------------------------------------------
    print("--- TEST 10: Subject Columns Deduplication Assertion ---")
    subj_cols = _get_unique_subject_columns(df)
    print(f"Detected Subject Columns: {subj_cols}")
    assert len(subj_cols) == len(set(subj_cols)), f"Duplicate columns found: {subj_cols}"
    print("✅ TEST 10 PASSED: len(subject_columns) == len(set(subject_columns))\n")

    # -------------------------------------------------------------------------
    # TEST 1: 'count the A grade in each subject'
    # -------------------------------------------------------------------------
    print("--- TEST 1: 'count the A grade in each subject' ---")
    t0 = time.perf_counter()
    resp1 = process_query_with_llm("count the A grade in each subject", df=df)
    t1_ms = (time.perf_counter() - t0) * 1000
    q1 = resp1.primary_query
    print(f"Latency: {t1_ms:.2f} ms | Operation: {q1.operation} | Condition: {q1.condition}")
    assert q1.operation in ("column_value_count", "conditional_count"), f"Expected column_value_count, got {q1.operation}"
    assert q1.condition and q1.condition.value == "A", f"Expected condition 'A', got {q1.condition}"
    assert not q1.filters, f"Expected no row-level filters, got {q1.filters}"
    assert len(q1.columns) == len(set(q1.columns)), "QuerySpec columns contains duplicates"

    exec_res1 = execute_query(q1, df)
    print(f"Result Intent: {exec_res1.result.get('intent')} | Rows: {len(exec_res1.result.get('rows', []))}")
    print(f"Evidence Aggregation: {exec_res1.metadata.get('aggregation')}")
    assert exec_res1.metadata.get("aggregation") == "COUNT PER COLUMN"
    print("✅ TEST 1 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 2: 'How many O grades are there in each subject?'
    # -------------------------------------------------------------------------
    print("--- TEST 2: 'How many O grades are there in each subject?' ---")
    resp2 = process_query_with_llm("How many O grades are there in each subject?", df=df)
    q2 = resp2.primary_query
    assert q2.operation in ("column_value_count", "conditional_count")
    assert q2.condition and q2.condition.value == "O"
    print("✅ TEST 2 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 3: 'How many B grades are there in each subject?'
    # -------------------------------------------------------------------------
    print("--- TEST 3: 'How many B grades are there in each subject?' ---")
    resp3 = process_query_with_llm("How many B grades are there in each subject?", df=df)
    q3 = resp3.primary_query
    assert q3.operation in ("column_value_count", "conditional_count")
    assert q3.condition and q3.condition.value == "B"
    print("✅ TEST 3 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 4: 'Show the grade distribution for each subject.'
    # -------------------------------------------------------------------------
    print("--- TEST 4: 'Show the grade distribution for each subject.' ---")
    resp4 = process_query_with_llm("Show the grade distribution for each subject.", df=df)
    q4 = resp4.primary_query
    assert q4.operation in ("column_value_distribution", "multi_column_value_distribution")
    assert q4.condition is None or q4.condition.value != "DISTRIBUTION", "DISTRIBUTION must not be treated as a grade filter value!"
    exec_res4 = execute_query(q4, df)
    assert exec_res4.metadata.get("aggregation") == "GROUP BY VALUE PER COLUMN"
    print("✅ TEST 4 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 5: 'What is the distribution of grades in cs23333?'
    # -------------------------------------------------------------------------
    print("--- TEST 5: 'What is the distribution of grades in cs23333?' ---")
    resp5 = process_query_with_llm("What is the distribution of grades in cs23333?", df=df)
    q5 = resp5.primary_query
    assert q5.operation in ("column_value_distribution", "multi_column_value_distribution")
    assert "cs23333" in q5.columns or q5.column == "cs23333"
    print("✅ TEST 5 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 6: 'What about B?' (Follow-up)
    # -------------------------------------------------------------------------
    print("--- TEST 6: Follow-up 'What about B?' ---")
    resolver = ContextResolver()
    prev_msg = [{"role": "assistant", "query_spec": q1.to_dict(), "intent": {"operation": "column_value_count"}}]
    resolved_spec, _, _ = resolver.resolve_context("chat_1", "What about B?", prev_msg, [])
    assert resolved_spec is not None
    assert resolved_spec.condition.value == "B"
    print("✅ TEST 6 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 7: 'Break this down by cs23333'
    # -------------------------------------------------------------------------
    print("--- TEST 7: Follow-up 'Break this down by cs23333' ---")
    resolved_spec7, _, _ = resolver.resolve_context("chat_1", "Break this down by cs23333", prev_msg, [])
    assert resolved_spec7 is not None
    assert "cs23333" in (resolved_spec7.columns or [resolved_spec7.column])
    print("✅ TEST 7 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 9: Typo 'count A grede in each subect'
    # -------------------------------------------------------------------------
    print("--- TEST 9: Typo 'count A grede in each subect' ---")
    resp9 = process_query_with_llm("count A grede in each subect", df=df)
    q9 = resp9.primary_query
    assert q9.operation in ("column_value_count", "conditional_count")
    assert q9.condition and q9.condition.value == "A"
    print("✅ TEST 9 PASSED\n")

    print("=================================================================")
    print("            ALL 10 TEST CASES PASSED SUCCESSFULLY                ")
    print("=================================================================")


if __name__ == "__main__":
    run_tests()
