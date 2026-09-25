"""
Final Benchmark Runner for Student Record Lookup & Latency Optimization
Prints full breakdown for required benchmark queries.
"""

import sys
import os
import time
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyst.query_processor import process_query_with_llm, _get_unique_subject_columns
from analyst.query_executor import execute_query
from analyst.semantic_cache import SemanticQueryCache
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


def run_final_benchmark():
    print("=================================================================")
    print("           FINAL BENCHMARK & PERFORMANCE ACCEPTANCE SUITE        ")
    print("=================================================================\n")

    SemanticQueryCache.clear()
    df = create_sample_student_df()
    resolver = ContextResolver()

    benchmark_queries = [
        "show all marks for Nithin S",
        "What about the second highest?",
        "list the mark for the student name with Nithin S",
        "show Nithin S's cs23333 mark",
        "what did Nithin S score in cs23333?",
        "how many students are named Nithin S?",
        "how many O grades are there in each subject?",
        "show the grade distribution for each subject"
    ]

    history = []
    prev_spec = None
    prev_result = None

    for idx, q_text in enumerate(benchmark_queries, 1):
        print("-----------------------------------------------------------------")
        print(f"QUERY {idx}: \"{q_text}\"")
        print("-----------------------------------------------------------------")

        t_total_0 = time.perf_counter()

        # Context loading & resolution
        t_ctx_0 = time.perf_counter()
        conv_ctx = None
        if history:
            resolved_spec, resolved_text, _ = resolver.resolve_context("chat_bench", q_text, history, [])
            conv_ctx = {
                "previous_result": {
                    "query_spec": history[-1]["query_spec"],
                    "records": history[-1].get("result", {}).get("records") if isinstance(history[-1].get("result"), dict) else None,
                    "result": history[-1].get("result")
                }
            }
            if resolved_spec:
                prev_spec = resolved_spec.to_dict()
        ctx_ms = (time.perf_counter() - t_ctx_0) * 1000

        # LLM interpretation & Fast path
        t_llm_0 = time.perf_counter()
        resp = process_query_with_llm(q_text, df=df, conversation_context=conv_ctx, previous_query=prev_spec)
        llm_ms = (time.perf_counter() - t_llm_0) * 1000

        primary_q = resp.primary_query
        prompt_tokens = resp.timing.get("estimated_tokens", 0) if resp.timing else 0

        # DuckDB / Pandas Execution
        t_exec_0 = time.perf_counter()
        exec_res = None
        if primary_q:
            exec_res = execute_query(primary_q, df)
        exec_ms = (time.perf_counter() - t_exec_0) * 1000

        total_ms = (time.perf_counter() - t_total_0) * 1000

        print(f"• QuerySpec: {primary_q.to_dict() if primary_q else 'None'}")
        print(f"• Intent: {primary_q.operation if primary_q else resp.type}")
        print(f"• Context Timing: {ctx_ms:.2f} ms")
        print(f"• LLM Timing: {llm_ms:.2f} ms")
        print(f"• Execution (DuckDB/Pandas) Timing: {exec_ms:.2f} ms")
        print(f"• Total Timing: {total_ms:.2f} ms")
        print(f"• Prompt Token Count: ~{prompt_tokens} tokens")

        if exec_res:
            res_data = exec_res.result
            if isinstance(res_data, dict) and "records" in res_data:
                print(f"• Result: Intent = {res_data.get('intent')} | Returned Records = {len(res_data.get('records', []))}")
                print(f"  Record Sample: {json.dumps(res_data.get('records', [])[:1], indent=2)}")
            elif isinstance(res_data, dict) and "rows" in res_data:
                print(f"• Result: Intent = {res_data.get('intent')} | Row Count = {len(res_data.get('rows', []))}")
                print(f"  Row Sample: {json.dumps(res_data.get('rows', [])[:2], indent=2)}")
            else:
                print(f"• Result: {exec_res.scalar if exec_res.scalar else exec_res.result}")

            meta = exec_res.metadata or {}
            print(f"• Evidence Fields Used: {meta.get('fields_used')}")
            print(f"• Evidence Rows Analyzed: {meta.get('rows_analyzed')}")
            print(f"• Evidence Filters Applied: {meta.get('filters_applied')}")
            print(f"• Evidence Aggregation: {meta.get('aggregation')}")
        else:
            print(f"• Direct Answer Result: {resp.answer}")

        print("\n")

        if primary_q:
            prev_spec = primary_q.to_dict()
            prev_result = exec_res.result if exec_res else None
            history.append({
                "role": "assistant",
                "query_spec": prev_spec,
                "result": prev_result
            })

    print("=================================================================")
    print("                 BENCHMARK COMPLETED SUCCESSFULLY                ")
    print("=================================================================")


if __name__ == "__main__":
    run_final_benchmark()
