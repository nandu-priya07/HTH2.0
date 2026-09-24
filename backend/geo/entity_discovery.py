import re
import pandas as pd

_HINTS = {
    "country": ("country", "nation"), "state": ("state", "province", "territory"),
    "district": ("county", "district"), "city": ("city", "town", "municipality", "village"), "region": ("region", "area", "zone"),
    "postal_code": ("postal", "zip", "postcode")
}

def _name_type(name):
    n = re.sub(r"[^a-z]", "_", str(name).lower())
    for kind, hints in _HINTS.items():
        if any(re.search(rf"(?:^|_){re.escape(h)}(?:_|$)", n) for h in hints): return kind
    return None

def discover_geo_profile(df, metadata=None):
    """Score geo candidates from column semantics, metadata, and recognizable values."""
    result = []
    for col in df.columns:
        series = df[col].dropna()
        if not len(series): continue
        name_kind = _name_type(col)
        samples = [str(v).strip() for v in series.head(80)]
        value_geo = sum(bool(re.search(r"[,\d].*\b(?:street|road|avenue|st|rd)\b", s, re.I)) for s in samples) / len(samples)
        dtype_geo = not pd.api.types.is_numeric_dtype(series) and series.nunique() < max(500, len(series) * .9)
        coords = bool(re.search(r"lat|latitude|lon|lng|longitude", str(col), re.I)) and pd.api.types.is_numeric_dtype(series)
        conf = .94 if name_kind else (.82 if value_geo > .25 else .0)
        if metadata:
            for item in metadata.get("geographic_columns", []):
                if item.get("column") == col:
                    conf = max(conf, float(item.get("confidence", 0)))
                    name_kind = item.get("entity_type", name_kind)
        if coords: conf = .99
        if conf >= .55 and dtype_geo or coords:
            result.append({"column": str(col), "entity_type": "coordinate" if coords else (name_kind or "location"), "confidence": round(conf, 2), "unique_count": int(series.nunique()), "coordinate_role": "latitude" if re.search(r"lat", str(col), re.I) else "longitude" if re.search(r"lon|lng", str(col), re.I) else None})
    return {"geographic_columns": result}
