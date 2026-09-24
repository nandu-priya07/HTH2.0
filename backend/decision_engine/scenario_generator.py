def generate_scenarios(baseline, target_value=None, requested_percent=None, maximum=8):
    if requested_percent is not None:
        levels = [requested_percent]
    elif target_value is not None and baseline and target_value <= baseline:
        levels = [0]
    elif target_value is not None and baseline and target_value > baseline:
        required = (target_value / baseline - 1) * 100
        step = max(1, round(required / 4 / 5) * 5)
        levels = sorted(set([step, step * 2, step * 3, step * 4, round(required, 2)]))
        levels = [x for x in levels if x > 0]
    else:
        return []
    return [{"increase_percent": float(x), "multiplier": 1 + float(x) / 100} for x in levels[:maximum]]
