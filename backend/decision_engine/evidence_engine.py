def build_evidence(metric, factors, counter_tests, boundary):
    claim = "The scenario model indicates a candidate decision boundary." if boundary.get("boundary_value") is not None else "No supported decision boundary was identified from evaluated scenarios."
    return {"claim": claim, "evidence": [{"factor": f["name"], **f["evidence"]} for f in factors], "counter_tests": counter_tests,
            "interpretation": "Factor relationships are observational associations and do not establish causation."}
