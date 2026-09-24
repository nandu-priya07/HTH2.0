from .entity_discovery import discover_geo_profile

def discover_hierarchy(df, profile=None):
    profile = profile or discover_geo_profile(df)
    levels = [c for c in profile["geographic_columns"] if c["entity_type"] not in ("coordinate", "postal_code")]
    # Prefer finer levels first by observed cardinality, while requiring functional containment.
    levels.sort(key=lambda x: x["unique_count"])
    ordered = []
    for candidate in levels:
        if not ordered:
            ordered.append(candidate); continue
        prev = ordered[-1]["column"]
        if df.groupby(candidate["column"], dropna=True)[prev].nunique().max() <= 1:
            ordered.append(candidate)
    return [{"level": c["entity_type"], "column": c["column"]} for c in ordered]
