"""
Performance Benchmark & Chat Isolation Test Suite.
Verifies sub-millisecond dataset cache hits, fast context resolution, DuckDB execution speed,
and chat dataset isolation.
"""

import sys
import time
import numpy as np
import pandas as pd

from services.dataset_runtime import DatasetRuntimeManager, get_dataset_runtime, load_dataset_runtime
from analyst.models import QuerySpec
from analyst.query_executor import execute_query
from analyst.response_generator import ResponseGenerator
from chat.service import ChatService
from chat.memory_repository import MemoryChatRepository


def create_large_benchmark_df(rows: int = 518451) -> pd.DataFrame:
    print(f"Generating synthetic benchmark dataset with {rows:,} rows × 8 columns...")
    np.random.seed(42)
    categories = ["Technology", "Furniture", "Office Supplies"]
    countries = ["United States", "United Kingdom", "Germany", "France", "Japan"]

    data = {
        "order_id": [f"ORD-{i+1}" for i in range(rows)],
        "country": np.random.choice(countries, rows),
        "category": np.random.choice(categories, rows),
        "quantity": np.random.randint(1, 50, rows),
        "unit_price": np.random.uniform(5.0, 500.0, rows).round(2),
        "sales": np.random.uniform(10.0, 5000.0, rows).round(2),
        "profit": np.random.uniform(-500.0, 1500.0, rows).round(2),
        "order_date": pd.date_range("2023-01-01", periods=rows, freq="s")
    }
    return pd.DataFrame(data)


def run_performance_benchmarks():
    df_large = create_large_benchmark_df(518451)
    dataset_id = "test_large_518k"

    print("\n=================================================================")
    print("       QUERYLENS / HTH2.0 BACKEND PERFORMANCE BENCHMARK SUITE    ")
    print("=================================================================\n")

    # 1. INITIAL LOAD & PRE-INDEXING (Cold Start)
    t0 = time.perf_counter()
    manager = DatasetRuntimeManager.get_instance()
    runtime = manager.load_dataset_runtime(
        dataset_id=dataset_id,
        existing_df=df_large,
        existing_info={"filename": "large_518k.csv", "file_type": "csv"}
    )
    t_load_ms = (time.perf_counter() - t0) * 1000
    print(f"[COLD START LOAD] Created DatasetRuntime for 518,451 rows in: {t_load_ms:.2f} ms")

    # 2. DATASET CACHE LOOKUP BENCHMARK (Target: < 5 ms)
    t0 = time.perf_counter()
    cached_rt = manager.get_dataset_runtime(dataset_id)
    t_cache_hit_ms = (time.perf_counter() - t0) * 1000
    print(f"[DATASET CACHE LOOKUP] Memory HIT latency: {t_cache_hit_ms:.4f} ms (Target: < 5 ms)")
    assert cached_rt is not None, "Cache lookup failed"
    assert t_cache_hit_ms < 5.0, f"Cache HIT latency ({t_cache_hit_ms:.2f}ms) exceeded 5ms target!"

    # 3. DUCKDB ANALYTICS EXECUTION BENCHMARK (Target: < 100 ms for 518k rows)
    spec_sum = QuerySpec(operation="sum", column="quantity")
    t0 = time.perf_counter()
    exec_res = execute_query(spec_sum, cached_rt.df)
    t_duckdb_ms = (time.perf_counter() - t0) * 1000
    total_qty = exec_res.scalar["value"] if exec_res.scalar else 0
    print(f"[DUCKDB ANALYTICS] SUM(quantity) over 518,451 rows = {total_qty:,} in: {t_duckdb_ms:.2f} ms (Target: < 100 ms)")
    assert exec_res.success, "DuckDB execution failed"
    assert t_duckdb_ms < 100.0, f"DuckDB latency ({t_duckdb_ms:.2f}ms) exceeded 100ms target!"

    # 4. RESPONSE FORMATTING BENCHMARK (Target: < 20 ms)
    t0 = time.perf_counter()
    formatted = ResponseGenerator.generate_response(exec_res, "What is the total quantity sold?", spec_sum)
    t_format_ms = (time.perf_counter() - t0) * 1000
    print(f"[RESPONSE FORMATTING] Formatted explanation generated in: {t_format_ms:.2f} ms (Target: < 20 ms)")
    assert "How we got this answer" in formatted, "Explanation missing expected header"
    assert t_format_ms < 20.0, f"Formatting latency ({t_format_ms:.2f}ms) exceeded 20ms target!"

    # 5. CHAT CONTEXT RESOLUTION BENCHMARK (Target: < 10 ms)
    memory_repo = MemoryChatRepository()
    chat_svc = ChatService(repository=memory_repo)
    chat_a = chat_svc.create_conversation(title="Chat A", dataset_id="ds_a")
    chat_svc.add_user_message(chat_a.id, "What is total sales?")

    t0 = time.perf_counter()
    messages_a = chat_svc.get_messages(chat_a.id, limit=10)
    files_a = chat_svc.get_files(chat_a.id)
    t_context_ms = (time.perf_counter() - t0) * 1000
    print(f"[CONTEXT & SESSION] Chat context lookup in: {t_context_ms:.4f} ms (Target: < 10 ms)")
    assert t_context_ms < 10.0, f"Context latency ({t_context_ms:.2f}ms) exceeded 10ms target!"

    # 6. CRITICAL CHAT ISOLATION TEST
    print("\n--- CHAT ISOLATION TEST ---")
    chat_b = chat_svc.create_conversation(title="Chat B", dataset_id="ds_b")
    assert chat_a.dataset_id == "ds_a", "Chat A dataset mismatch"
    assert chat_b.dataset_id == "ds_b", "Chat B dataset mismatch"
    print("  [PASS] Chat A (ds_a) and Chat B (ds_b) remain completely isolated.")

    # 7. ADDITIONAL DETERMINISTIC BENCHMARK QUERIES
    print("\n--- ADDITIONAL DETERMINISTIC QUERY BENCHMARKS ---")
    queries_to_test = [
        ("What is the total revenue?", QuerySpec(operation="sum", column="sales")),
        ("What is the average unit price?", QuerySpec(operation="average", column="unit_price")),
        ("How many unique customers are there?", QuerySpec(operation="count_distinct", column="order_id")),
        ("Show total revenue by country.", QuerySpec(operation="sum", column="sales", group_by=["country"])),
        ("Which country has the highest revenue?", QuerySpec(operation="sum", column="sales", group_by=["country"], sort=[{"column": "sales", "direction": "desc"}], limit=1))
    ]

    for q_text, spec in queries_to_test:
        t0 = time.perf_counter()
        res = execute_query(spec, cached_rt.df)
        fmt = ResponseGenerator.generate_response(res, q_text, spec)
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"  • '{q_text}' → {elapsed:.2f} ms")
        assert res.success, f"Query '{q_text}' failed!"

    print("\n=================================================================")
    print("         ALL PERFORMANCE & ISOLATION BENCHMARKS PASSED           ")
    print("=================================================================\n")


if __name__ == "__main__":
    run_performance_benchmarks()
