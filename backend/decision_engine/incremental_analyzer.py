def analyze_incremental(scenarios):
    previous = 0.0
    for row in scenarios:
        row["incremental_benefit"] = row["impact"] - previous
        previous = row["impact"]
    return scenarios
