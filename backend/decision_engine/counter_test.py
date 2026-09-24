import pandas as pd


def run_counter_tests(df: pd.DataFrame, target: str, factors):
    tests = []
    factor = next((f for f in factors if f["type"] == "numeric" and f["evidence"].get("metric") == "pearson_correlation"), None)
    if factor:
        x, y = pd.to_numeric(df[factor["name"]], errors="coerce"), pd.to_numeric(df[target], errors="coerce")
        base = float(x.corr(y))
        group_cols = [c for c in df.select_dtypes(exclude="number").columns if df[c].nunique() <= 30]
        for col in group_cols[:6]:
            results = []
            for name, part in df.assign(_x=x, _y=y).groupby(col, dropna=True):
                pair = part[["_x", "_y"]].dropna()
                if len(pair) >= 5:
                    results.append({"group": str(name), "n": len(pair), "correlation": float(pair._x.corr(pair._y))})
            if results:
                tests.append({"test": "group_split", "factor": col, "result": "direction varies" if any((v["correlation"] >= 0) != (base >= 0) for v in results) else "direction consistent in evaluated groups", "groups": results})
        pair = pd.DataFrame({"x": x, "y": y}).dropna()
        trimmed = pair[(pair.x.between(pair.x.quantile(.05), pair.x.quantile(.95))) & pair.y.between(pair.y.quantile(.05), pair.y.quantile(.95))]
        if len(trimmed) >= 5:
            tests.append({"test": "outlier_sensitivity", "result": "association sensitive to extreme 5% tails" if abs(float(trimmed.x.corr(trimmed.y))) < abs(base) * .5 else "association direction/strength broadly persists after trimming 5% tails", "correlation_after_trim": float(trimmed.x.corr(trimmed.y)), "n": len(trimmed)})
    return tests
