"""
Comprehensive Test Suite for Analytical Reasoning, Insight & Real Prediction Engine.
Verifies all Master Prompt test cases, including deterministic fast-path execution,
real time-series forecasting, anomaly detection, dataset profiling, and analytical reasoning.
"""

import sys
import time
import pandas as pd
import numpy as np

from analyst.models import QuerySpec, QueryResult
from analyst.query_processor import process_query_with_llm
from analyst.query_executor import execute_query
from analyst.response_generator import ResponseGenerator
from analyst.profiler_engine import run_dataset_summary
from analyst.trend_engine import run_trend_analysis
from analyst.forecast_engine import run_forecast_analysis
from analyst.anomaly_engine import run_anomaly_detection
from analyst.insight_engine import run_complex_insight, run_comparison, run_decision_analysis
from reasoning.reasoning_engine import generate_analytical_reasoning, should_invoke_reasoning


def create_sample_sales_df() -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=24, freq="ME")
    categories = ["Technology", "Furniture", "Office Supplies"]
    states = ["California", "Texas", "New York", "Florida"]

    data = []
    for d in dates:
        for cat in categories:
            for st in states:
                sales = float(np.random.uniform(500, 5000))
                profit = float(sales * np.random.uniform(-0.1, 0.3))
                data.append({
                    "order_date": d,
                    "category": cat,
                    "state": st,
                    "sales": round(sales, 2),
                    "profit": round(profit, 2)
                })

    df = pd.DataFrame(data)
    # Add explicit anomaly in 2024-11
    df.loc[df["order_date"] == "2024-11-30", "sales"] = 55000.0
    return df


def create_sample_grade_df() -> pd.DataFrame:
    data = [
        {"student_name": "Nithin S", "reg_no": "101", "cs23333": "O", "cs23334": "A+", "cs23335": "A"},
        {"student_name": "Priya M", "reg_no": "102", "cs23333": "A", "cs23334": "O", "cs23335": "A+"},
        {"student_name": "Rahul K", "reg_no": "103", "cs23333": "B+", "cs23334": "A", "cs23335": "O"}
    ]
    return pd.DataFrame(data)


def run_all_tests():
    sales_df = create_sample_sales_df()
    grade_df = create_sample_grade_df()

    passed = 0
    total = 0

    def assert_test(condition: bool, name: str, details: str = ""):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            print(f"  [PASS] {name} {details}")
        else:
            print(f"  [FAIL] {name} {details}")
            sys.exit(1)

    print("\n=======================================================")
    print("RUNNING ANALYTICAL INTELLIGENCE & PREDICTION TEST SUITE")
    print("=======================================================\n")

    # 1. BASIC DETERMINISTIC TESTS (Level 1: MUST NOT call reasoning LLM)
    print("--- 1. BASIC DETERMINISTIC TESTS (LEVEL 1) ---")
    t0 = time.perf_counter()
    spec = QuerySpec(operation="sum", column="profit")
    res = execute_query(spec, sales_df)
    t_ms = (time.perf_counter() - t0) * 1000
    assert_test(res.success and res.scalar is not None, "What is total profit?", f"({t_ms:.2f} ms)")
    assert_test(not should_invoke_reasoning("What is total profit?", spec, res), "Level 1: No reasoning LLM call")

    spec2 = QuerySpec(operation="sum", column="sales")
    res2 = execute_query(spec2, sales_df)
    assert_test(res2.success and res2.scalar is not None, "What is total sales?")

    spec3 = QuerySpec(operation="sum", column="profit", group_by=["category"])
    res3 = execute_query(spec3, sales_df)
    assert_test(res3.success and res3.table is not None, "Show profit by category.")

    spec4 = QuerySpec(operation="sum", column="sales", group_by=["state"], sort=[{"column": "sales", "direction": "desc"}], limit=1)
    res4 = execute_query(spec4, sales_df)
    assert_test(res4.success and res4.table is not None, "Which state has highest sales?")


    # 2. DATASET SUMMARY ENGINE (PHASE 2)
    print("\n--- 2. DATASET SUMMARY ENGINE ---")
    sum_res = run_dataset_summary(sales_df)
    assert_test(sum_res.success and sum_res.canonical_data is not None, "Dataset Profiler Execution")
    assert_test(sum_res.canonical_data["rows"] == len(sales_df), "Rows count match")
    assert_test(sum_res.canonical_data["columns"] == len(sales_df.columns), "Cols count match")
    assert_test(should_invoke_reasoning("Summarize this dataset.", QuerySpec(operation="dataset_summary"), sum_res), "Level 2: Invokes reasoning for dataset summary")


    # 3. TREND ENGINE (PHASE 3)
    print("\n--- 3. TREND ENGINE ---")
    trend_spec = QuerySpec(operation="trend", column="sales", time_column="order_date", frequency="month")
    trend_res = run_trend_analysis(sales_df, trend_spec)
    assert_test(trend_res.success and trend_res.trend_data is not None, "Trend Execution")
    assert_test("trend_direction" in trend_res.trend_data, "Trend Direction Calculated")
    assert_test("peak" in trend_res.trend_data and "trough" in trend_res.trend_data, "Peak & Trough Detected")


    # 4. REAL FORECASTING / PREDICTION ENGINE (PHASE 4)
    print("\n--- 4. REAL FORECASTING / PREDICTION ENGINE ---")
    fc_spec = QuerySpec(operation="forecast", column="sales", time_column="order_date", horizon=3, frequency="month")
    fc_res = run_forecast_analysis(sales_df, fc_spec)
    assert_test(fc_res.success and fc_res.forecast_data is not None, "Real Forecast Execution")
    assert_test(len(fc_res.forecast_data["forecast"]) == 3, "Forecast Horizon = 3")
    assert_test(all("lower" in f and "upper" in f and "predicted" in f for f in fc_res.forecast_data["forecast"]), "Confidence Bounds Present")
    assert_test(fc_res.forecast_data["model"] != "", "Deterministic Model Selected")

    # Insufficient Data Check
    small_df = sales_df.head(2)
    fc_small = run_forecast_analysis(small_df, fc_spec)
    assert_test(not fc_small.success and "Insufficient historical data" in fc_small.error, "Insufficient historical data handling")


    # 5. ANOMALY DETECTION ENGINE (PHASE 5)
    print("\n--- 5. ANOMALY DETECTION ENGINE ---")
    anom_spec = QuerySpec(operation="anomaly_detection", column="sales", time_column="order_date")
    anom_res = run_anomaly_detection(sales_df, anom_spec)
    assert_test(anom_res.success and anom_res.anomaly_data is not None, "Anomaly Detection Execution")
    assert_test(anom_res.anomaly_data["anomalies_count"] >= 1, "Detects explicit outlier (2024-11)")


    # 6. COMPLEX INSIGHT & DECISION ENGINE (PHASE 8)
    print("\n--- 6. COMPLEX INSIGHT, COMPARISON & DECISION ---")
    ins_spec = QuerySpec(operation="complex_insight", column="profit", group_by=["category"])
    ins_res = run_complex_insight(sales_df, ins_spec)
    assert_test(ins_res.success and ins_res.canonical_data is not None, "Complex Insight Contribution Analysis")

    comp_spec = QuerySpec(operation="comparison", options=["Technology", "Furniture"])
    comp_res = run_comparison(sales_df, comp_spec)
    assert_test(comp_res.success and comp_res.comparison_data is not None, "Side-by-Side Comparison")

    dec_spec = QuerySpec(operation="decision_analysis")
    dec_res = run_decision_analysis(sales_df, dec_spec)
    assert_test(dec_res.success and dec_res.decision_data is not None, "Decision Matrix Generation")


    # 7. ANALYTICAL REASONING LAYER (PHASE 6)
    print("\n--- 7. ANALYTICAL REASONING LAYER ---")
    reasoning_out = generate_analytical_reasoning("Explain the sales trend.", trend_spec, trend_res)
    assert_test(reasoning_out is not None and "summary" in reasoning_out, "Analytical Reasoning Output Generated")


    # 8. GRADE DATASET BACKWARD COMPATIBILITY (PHASE 30)
    print("\n--- 8. GRADE DATASET BACKWARD COMPATIBILITY ---")
    g_spec1 = QuerySpec(operation="column_value_count", columns=["cs23333", "cs23334", "cs23335"], condition={"operator": "equals", "value": "O"})
    g_res1 = execute_query(g_spec1, grade_df)
    assert_test(g_res1.success and g_res1.table is not None, "How many O grades in each subject?")

    g_spec2 = QuerySpec(operation="record_lookup", columns=["student_name", "cs23333", "cs23334", "cs23335"], filters=[{"column": "student_name", "operator": "=", "value": "Nithin S"}])
    g_res2 = execute_query(g_spec2, grade_df)
    assert_test(g_res2.success and g_res2.result["records"][0]["student_name"] == "Nithin S", "Show all marks for Nithin S.")


    # 9. RESPONSE GENERATOR VERIFICATION (PHASE 7)
    print("\n--- 9. RESPONSE GENERATOR FORMATTING ---")
    resp_fc = ResponseGenerator.generate_response(fc_res, "Predict sales for the next 3 months.", fc_spec)
    assert_test("### Forecast" in resp_fc and "Confidence" in resp_fc, "ResponseGenerator Forecast formatting")

    resp_anom = ResponseGenerator.generate_response(anom_res, "Find unusual sales months.", anom_spec)
    assert_test("### Anomaly Detection Results" in resp_anom, "ResponseGenerator Anomaly formatting")

    print(f"\n=======================================================")
    print(f"ALL TESTS COMPLETED SUCCESSFULLY ({passed}/{total} PASSED)")
    print("=======================================================\n")


if __name__ == "__main__":
    run_all_tests()
