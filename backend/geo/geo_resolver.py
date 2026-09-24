from functools import lru_cache
from pathlib import Path
import json
import re
import pandas as pd


def _norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


@lru_cache(maxsize=1)
def _country_catalog():
    path = Path(__file__).resolve().parents[2] / "frontend" / "public" / "geo" / "ne_110m_admin_0_countries.geojson"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    catalog = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        entry = {"geometry_name": props.get("ADMIN") or props.get("NAME"), "continent": props.get("CONTINENT"), "iso_a3": props.get("ADM0_A3")}
        for field in ("ADMIN", "NAME", "NAME_EN", "NAME_LONG", "SOVEREIGNT", "NAME_SORT", "NAME_ALT"):
            value = props.get(field)
            if value:
                catalog[_norm(value)] = entry
                for alias in re.split(r"[|,;/]", str(value)):
                    if alias.strip(): catalog[_norm(alias)] = entry
    return catalog


class GeoResolver:
    """Resolves dataset values against bundled Natural Earth country geometry metadata."""
    def resolve_geometry_names(self, names):
        catalog = _country_catalog()
        resolved = {}
        for name in names:
            match = catalog.get(_norm(name))
            if match: resolved[str(name)] = match
        return resolved, len(names) - len(resolved)

    def continent_for(self, name):
        match = _country_catalog().get(_norm(name))
        return match.get("continent") if match else None

    def continent_mentioned(self, text):
        continents = {item.get("continent") for item in _country_catalog().values() if item.get("continent")}
        lowered = text.casefold()
        for continent in continents:
            variants = {continent.casefold()}
            parts = continent.casefold().split()
            last = parts[-1]
            variants.add(" ".join(parts[:-1] + [last[:-1] + "ean"]) if last.endswith("e") else " ".join(parts[:-1] + [last[:-1] + "an"]) if last.endswith("a") else continent.casefold())
            if any(re.search(rf"\b{re.escape(variant)}\b", lowered) for variant in variants if variant):
                return continent
        return None

    def resolve_dataset_coordinates(self, df, dimension, names):
        lat = next((c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and re.search(r"(?:^|_)lat(?:itude)?(?:_|$)", c.lower())), None)
        lon = next((c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and re.search(r"(?:^|_)(?:lon(?:gitude)?|lng)(?:_|$)", c.lower())), None)
        if not lat or not lon: return {}, len(names)
        pairs = df.groupby(dimension, dropna=True)[[lat, lon]].mean().to_dict("index")
        resolved, missing = {}, 0
        for name in names:
            try:
                y, x = float(pairs[name][lat]), float(pairs[name][lon])
                if -90 <= y <= 90 and -180 <= x <= 180: resolved[name] = {"latitude": y, "longitude": x}
                else: missing += 1
            except (KeyError, TypeError, ValueError): missing += 1
        return resolved, missing
