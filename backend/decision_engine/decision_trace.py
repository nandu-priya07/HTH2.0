from datetime import datetime, timezone


def make_trace(question, file_id, intent, factors, impact, boundary, counter_tests, evidence, visualization):
    return {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "user_question": question,
            "intent": intent, "selected_file_id": file_id, "factor_discovery": factors,
            "scenario_analysis": impact, "incremental_benefits": impact["scenarios"],
            "boundary": boundary, "counter_tests": counter_tests, "evidence": evidence,
            "visualization": visualization,
            "trace": [{"step": "decision_detection", "input": question}, {"step": "factor_discovery", "factors": factors.get("factors", [])}, {"step": "impact_analysis", "result": impact}, {"step": "boundary_detection", "result": boundary}, {"step": "counter_tests", "result": counter_tests}, {"step": "evidence", "result": evidence}, {"step": "visualization", "result": visualization}]}
