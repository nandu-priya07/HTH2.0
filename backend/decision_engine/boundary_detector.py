def detect_boundary(scenarios, target_value=None, baseline=None):
    if target_value is not None:
        match = next((s for s in scenarios if s.get("target_reached")), None)
        if match:
            return {"boundary_type": "target", "boundary_value": match["increase_percent"], "reason": "First evaluated scenario whose projected value reaches the target", "supporting_scenario": match}
    if len(scenarios) >= 3:
        gains = [s["incremental_benefit"] for s in scenarios]
        for i in range(1, len(gains)):
            if gains[i] < gains[i-1] * .2:
                return {"boundary_type": "diminishing_return", "boundary_value": scenarios[i]["increase_percent"], "reason": "First evaluated level whose incremental benefit is below 20% of the prior increment", "supporting_scenario": scenarios[i]}
    return {"boundary_type": None, "boundary_value": None, "reason": "No target was reached and evaluated scenarios did not show a defined diminishing-return boundary", "supporting_scenario": None}
