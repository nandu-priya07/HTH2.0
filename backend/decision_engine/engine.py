import numpy as np
import pandas as pd

from .factor_discovery import discover_factors
from .scenario_generator import generate_scenarios
from .impact_analyzer import analyze_impact
from .incremental_analyzer import analyze_incremental
from .boundary_detector import detect_boundary
from .counter_test import run_counter_tests
from .evidence_engine import build_evidence
from .visualization_selector import select_decision_visualization
from .decision_trace import make_trace


def run_decision_analysis(df: pd.DataFrame, intent, file_id, previous_trace=None):
    metric = intent.get("target_metric")
    if not metric or metric not in df:
        return {"needs_clarification": True, "answer": "Which numeric outcome should this decision analysis target? Please name a metric in the dataset."}
    values = pd.to_numeric(df[metric], errors="coerce").dropna()
    if values.empty:
        return {"needs_clarification": True, "answer": f"I can't establish a decision boundary because '{metric}' has no usable numeric observations."}
    baseline = float(values.sum())
    if intent.get("target_value") is None and intent.get("requested_percent") is None:
        return {"needs_clarification": True, "answer": f"What target should {metric} reach? I can compare scenario increases once you provide a target."}
    factors = discover_factors(df, metric)
    scenarios = generate_scenarios(baseline, intent.get("target_value"), intent.get("requested_percent"))
    if previous_trace and intent.get("requested_percent") is not None:
        prior_rows = previous_trace.get("scenario_analysis", {}).get("scenarios", [])
        prior_levels = [{"increase_percent": row["increase_percent"], "multiplier": row["multiplier"]}
                        for row in prior_rows if "increase_percent" in row and "multiplier" in row]
        by_level = {row["increase_percent"]: row for row in prior_levels + scenarios}
        scenarios = [by_level[level] for level in sorted(by_level)]
    impact = analyze_impact(baseline, metric, scenarios, intent.get("target_value"))
    analyze_incremental(impact["scenarios"])
    boundary = detect_boundary(impact["scenarios"], intent.get("target_value"), baseline)
    counter = run_counter_tests(df, metric, factors["factors"])
    evidence = build_evidence(metric, factors["factors"], counter, boundary)
    vis = select_decision_visualization(metric, impact)
    trace = make_trace(intent["decision_question"], file_id, intent, factors, impact, boundary, counter, evidence, vis)
    return {"decision_analysis": trace}
