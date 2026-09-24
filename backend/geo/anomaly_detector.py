import numpy as np
import pandas as pd

def detect_anomalies(rows, direction="both"):
    values = np.asarray([r["metric"] for r in rows if r.get("metric") is not None], dtype=float)
    if len(values) < 3:
        return {"baseline":{"method":"median","value":float(np.median(values)) if len(values) else None},"method":"robust_z_score","threshold":2.5,"locations":[]}
    median = float(np.median(values)); mad = float(np.median(np.abs(values - median)))
    scale = 1.4826 * mad
    method = "median_mad"
    if scale == 0:
        q1,q3 = np.percentile(values,[25,75]); scale = float((q3-q1)/1.349); method = "median_iqr"
    if scale == 0:
        scale = float(np.std(values)); method = "median_standard_deviation"
    if scale == 0: scale = 1.0
    scored=[]
    for row in rows:
        score=(float(row["metric"])-median)/scale
        cls="underperforming" if score <= -2.5 else "above_baseline" if score >= 2.5 else "typical"
        if (direction == "low" and score < 0) or (direction == "high" and score > 0) or direction == "both":
            scored.append({**row,"anomaly_score":round(score,3),"classification":cls})
    return {"baseline":{"method":"median","value":median},"method":"robust_z_score","dispersion":method,"threshold":2.5,"locations":[r for r in scored if abs(r["anomaly_score"]) >= 2.5]}
