import numpy as np
import pandas as pd


def discover_factors(df: pd.DataFrame, target: str, max_factors: int = 12):
    factors = []
    if target not in df or not pd.api.types.is_numeric_dtype(df[target]):
        return {"factors": factors, "limitation": "The selected outcome must be a numeric dataset column."}
    y = pd.to_numeric(df[target], errors="coerce")
    for col in df.columns:
        if col == target or df[col].nunique(dropna=True) < 2:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            x = pd.to_numeric(df[col], errors="coerce")
            pair = pd.concat([x, y], axis=1).dropna()
            corr = float(pair.iloc[:, 0].corr(pair.iloc[:, 1])) if len(pair) >= 3 else None
            if corr is not None and np.isfinite(corr):
                factors.append({"name": str(col), "type": "numeric", "relationship": "positive_association" if corr >= 0 else "negative_association", "strength": abs(corr), "evidence": {"metric": "pearson_correlation", "value": corr, "n": int(len(pair))}})
        else:
            groups = pd.DataFrame({"group": df[col].astype(str), "outcome": y}).dropna().groupby("group").outcome.agg(["mean", "count"])
            if len(groups) >= 2:
                spread = float((groups["mean"].max() - groups["mean"].min()) / max(abs(float(y.mean())), 1e-12))
                factors.append({"name": str(col), "type": "categorical", "relationship": "group_variation", "strength": spread, "evidence": {"metric": "relative_group_mean_range", "value": spread, "groups": groups.head(30).reset_index().to_dict("records")}})
    factors.sort(key=lambda f: f["strength"], reverse=True)
    return {"factors": factors[:max_factors]}
