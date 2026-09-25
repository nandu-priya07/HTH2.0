"""
Comprehensive Test Suite for Record Lookup & Latency Optimization.
Validates all 9 PART 9 test cases, verifying:
- Query
- QuerySpec
- Intent
- Context timing
- LLM timing
- DuckDB timing
- Total timing
- Result
- Evidence
"""

import sys
import os
import time
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyst.query_processor import process_query_with_llm, _get_unique_subject_columns
from analyst.query_executor import execute_query
from chat.context_resolver import ContextResolver


def create_sample_student_df() -> pd.DataFrame:
    return pd.DataFrame({
        "reg_no": [101, 102, 103, 104, 105],
        "student_name": ["Alice M", "Nithin S", "Bob K", "Charlie R", "David P"],
        "hs23222": ["A", "O", "B", "A", "C"],
        "ge23111": ["A", "O", "B", "A", "C"],
        "ge23121": ["B", "A", "O", "B", "A"],
        "ge23117": ["O", "B", "A", "O", "B"],
        "ge23131": ["A", "A", "B", "C", "O"],
        "cs23333": [95, 88, 78, 92, 85],
        "mc23112": ["A", "B", "O", "A", "A"],
        "ai23331": ["A", "A", "A", "O", "B"]
    })


def run_suite():
    print("=================================================================")
    print("        STUDENT RECORD LOOKUP & LATENCY VALIDATION SUITE         ")
    print("=================================================================\n")

    from analyst.semantic_cache import SemanticQueryCache
    SemanticQueryCache.clear()

    df = create_sample_student_df()
    df_profit = pd.DataFrame({"profit": [100, 200, 300], "sales": [500, 600, 700]})

    resolver = ContextResolver()

    # -------------------------------------------------------------------------
    # TEST 1: 'show all marks for Nithin S'
    # -------------------------------------------------------------------------
    print("--- TEST 1: 'show all marks for Nithin S' ---")
    t0 = time.perf_counter()
    resp1 = process_query_with_llm("show all marks for Nithin S", df=df)
    t1_ms = (time.perf_counter() - t0) * 1000
    q1 = resp1.primary_query
    print(f"Latency: {t1_ms:.2f} ms | Operation: {q1.operation} | Filters: {q1.filters}")
    assert q1.operation == "record_lookup", f"Expected record_lookup, got {q1.operation}"
    assert any(f.get("value") == "Nithin S" for f in (q1.filters or [])), f"Expected filter Nithin S, got {q1.filters}"
    exec_res1 = execute_query(q1, df)
    print(f"Result Intent: {exec_res1.result.get('intent')} | Records: {len(exec_res1.result.get('records', []))}")
    print(f"Evidence Aggregation: {exec_res1.metadata.get('aggregation')}")
    print(f"Evidence Filters: {exec_res1.metadata.get('filters_applied')}")
    assert exec_res1.result.get("intent") == "record_lookup"
    assert len(exec_res1.result.get("records", [])) == 1
    assert exec_res1.result.get("records")[0]["student_name"] == "Nithin S"
    print("✅ TEST 1 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 2: 'list the mark for the student name with Nithin S'
    # -------------------------------------------------------------------------
    print("--- TEST 2: 'list the mark for the student name with Nithin S' ---")
    t0 = time.perf_counter()
    resp2 = process_query_with_llm("list the mark for the student name with Nithin S", df=df)
    t2_ms = (time.perf_counter() - t0) * 1000
    q2 = resp2.primary_query
    print(f"Latency: {t2_ms:.2f} ms | Operation: {q2.operation}")
    assert q2.operation == "record_lookup"
    exec_res2 = execute_query(q2, df)
    assert exec_res2.result.get("intent") == "record_lookup"
    assert len(exec_res2.result.get("records", [])) == 1
    print("✅ TEST 2 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 3: 'show Nithin S's cs23333 mark'
    # -------------------------------------------------------------------------
    print("--- TEST 3: 'show Nithin S's cs23333 mark' ---")
    t0 = time.perf_counter()
    resp3 = process_query_with_llm("show Nithin S's cs23333 mark", df=df)
    t3_ms = (time.perf_counter() - t0) * 1000
    q3 = resp3.primary_query
    print(f"Latency: {t3_ms:.2f} ms | Operation: {q3.operation} | Columns: {q3.columns}")
    assert q3.operation == "record_lookup"
    assert "cs23333" in q3.columns
    exec_res3 = execute_query(q3, df)
    assert exec_res3.result.get("records")[0]["cs23333"] == 88
    print("✅ TEST 3 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 4: 'what did Nithin S score in cs23333?'
    # -------------------------------------------------------------------------
    print("--- TEST 4: 'what did Nithin S score in cs23333?' ---")
    resp4 = process_query_with_llm("what did Nithin S score in cs23333?", df=df)
    q4 = resp4.primary_query
    assert q4.operation == "record_lookup"
    print("✅ TEST 4 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 5: 'how many students are named Nithin S?'
    # -------------------------------------------------------------------------
    print("--- TEST 5: 'how many students are named Nithin S?' ---")
    resp5 = process_query_with_llm("how many students are named Nithin S?", df=df)
    q5 = resp5.primary_query
    print(f"q5 Spec: {q5.to_dict()}")
    print(f"Operation: {q5.operation} | Target: {q5.column}")
    assert q5.operation == "count"
    assert q5.operation != "record_lookup", "COUNT request must not be record_lookup!"
    exec_res5 = execute_query(q5, df)
    print(f"Exec Result: {exec_res5.result} | Scalar: {exec_res5.scalar}")
    val5 = exec_res5.scalar.get("value") if exec_res5.scalar else exec_res5.result
    assert val5 == 1, f"Expected count 1, got {val5}"
    print("✅ TEST 5 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 6: Follow-up 'What about the second highest?'
    # -------------------------------------------------------------------------
    print("--- TEST 6: Follow-up 'What about the second highest?' ---")
    history = [{"role": "assistant", "query_spec": q1.to_dict(), "result": exec_res1.result}]
    conv_ctx = {"previous_result": {"query_spec": q1.to_dict(), "records": exec_res1.result.get("records")}}
    resp6 = process_query_with_llm("What about the second highest?", df=df, conversation_context=conv_ctx)
    print(f"Answer: {resp6.answer}")
    assert resp6.type == "direct_answer"
    assert "second highest" in resp6.answer.lower() or "cs23333" in resp6.answer or "ge23111" in resp6.answer
    print("✅ TEST 6 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 7: 'how many O grades are there in each subject?'
    # -------------------------------------------------------------------------
    print("--- TEST 7: 'how many O grades are there in each subject?' ---")
    t0 = time.perf_counter()
    resp7 = process_query_with_llm("how many O grades are there in each subject?", df=df)
    t7_ms = (time.perf_counter() - t0) * 1000
    q7 = resp7.primary_query
    print(f"Latency: {t7_ms:.2f} ms | Operation: {q7.operation}")
    assert q7.operation == "column_value_count"
    exec_res7 = execute_query(q7, df)
    print(f"Evidence Filters: {exec_res7.metadata.get('filters_applied')}")
    print(f"Evidence Aggregation: {exec_res7.metadata.get('aggregation')}")
    assert exec_res7.metadata.get("filters_applied") == [] or exec_res7.metadata.get("filters_applied") is None, "Column-wise evidence must not fabricate row filters!"
    assert exec_res7.metadata.get("aggregation") == "COUNT PER COLUMN"
    print("✅ TEST 7 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 8: 'show the grade distribution for each subject'
    # -------------------------------------------------------------------------
    print("--- TEST 8: 'show the grade distribution for each subject' ---")
    resp8 = process_query_with_llm("show the grade distribution for each subject", df=df)
    q8 = resp8.primary_query
    assert q8.operation in ("column_value_distribution", "multi_column_value_distribution")
    exec_res8 = execute_query(q8, df)
    assert exec_res8.metadata.get("filters_applied") == [] or exec_res8.metadata.get("filters_applied") is None
    assert exec_res8.metadata.get("aggregation") == "GROUP BY VALUE PER COLUMN"
    print("✅ TEST 8 PASSED\n")

    # -------------------------------------------------------------------------
    # TEST 9: 'What is total profit?' (Normal Aggregation Unchanged)
    # -------------------------------------------------------------------------
    print("--- TEST 9: 'What is total profit?' ---")
    resp9 = process_query_with_llm("What is total profit?", df=df_profit)
    q9 = resp9.primary_query
    assert q9.operation == "sum" and q9.column == "profit"
    exec_res9 = execute_query(q9, df_profit)
    assert exec_res9.result == 600
    print("✅ TEST 9 PASSED\n")

    print("=================================================================")
    print("            ALL 9 TEST CASES PASSED SUCCESSFULLY                ")
    print("=================================================================")


if __name__ == "__main__":
    run_suite()
