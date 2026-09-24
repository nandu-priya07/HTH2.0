def analyze_impact(baseline, metric, scenarios, target_value=None):
    rows = []
    for scenario in scenarios:
        projected = baseline * scenario["multiplier"]
        rows.append({**scenario, "projected_value": projected, "impact": projected - baseline,
                     "target_gap": None if target_value is None else target_value - projected,
                     "target_reached": None if target_value is None else projected >= target_value})
    return {"baseline": {metric: baseline}, "scenarios": rows, "method": "proportional scaling scenario; assumes outcome changes at the stated percentage"}
