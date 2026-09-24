import pandas as pd

from decision_engine import detect_decision, run_decision_analysis


def test_descriptive_query_stays_on_analyst_route():
    assert detect_decision("How many B grades are there?", ["grade", "sales"])["is_decision"] is False


def test_decision_question_generates_reproducible_scenarios_and_boundary():
    df = pd.DataFrame({"sales": [100, 110, 120, 130], "quantity": [10, 11, 12, 13]})
    intent = detect_decision("By what percentage should sales increase to reach $180?", df.columns)
    output = run_decision_analysis(df, intent, "file-1")["decision_analysis"]
    assert output["scenario_analysis"]["baseline"]["sales"] == 460
    assert output["boundary"]["boundary_type"] == "target"
    assert output["scenario_analysis"]["scenarios"]
    assert output["trace"][-1]["step"] == "visualization"


def test_missing_target_asks_for_clarification():
    df = pd.DataFrame({"sales": [100, 110]})
    intent = detect_decision("By what percentage should sales increase?", df.columns)
    assert run_decision_analysis(df, intent, "file-1")["needs_clarification"] is True
