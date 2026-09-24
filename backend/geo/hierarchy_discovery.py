"""Discover a dataset's observed geographic drill path without requiring fixed headers."""
import re

from .entity_discovery import discover_geo_profile


_ORDER = {
    "continent": 0, "country": 10, "region": 20, "state": 30,
    "province": 30, "administrative_area_level_1": 30,
    "county": 40, "district": 40, "administrative_area_level_2": 40,
    "city": 50, "town": 50, "municipality": 50, "village": 50,
}


def _semantic_level(item):
    kind = str(item.get("entity_type") or "location").casefold()
    name = re.sub(r"[^a-z0-9]+", " ", str(item.get("column", "")).casefold()).strip()
    if kind in ("state", "province", "territory"):
        return "administrative_area_level_1"
    if kind in ("district", "county"):
        return "administrative_area_level_2"
    if kind == "region":
        # Region is only a level label; its position is verified from actual containment.
        return "region"
    if kind in ("city", "town", "municipality", "village"):
        return "city" if kind == "city" else kind
    if kind in ("country", "continent"):
        return kind
    if "postal" in name or "zip" in name or "postcode" in name:
        return "postal_code"
    return kind


def discover_hierarchy(df, profile=None):
    """Return normalized levels ordered coarsest-to-finest with observed parent links.

    A proposed parent/child pair is retained only when observed data contains
    nonempty parent-child pairs and the child field has at least as much granularity.
    Duplicate child labels across different parents remain distinct through their key.
    """
    profile = profile or discover_geo_profile(df)
    candidates = [
        {**item, "semantic_level": _semantic_level(item)}
        for item in profile.get("geographic_columns", [])
        if item.get("entity_type") not in ("coordinate", "postal_code")
        and item.get("column") in df.columns
    ]
    candidates.sort(key=lambda item: (
        _ORDER.get(item["semantic_level"], 25),
        int(item.get("unique_count", df[item["column"]].nunique(dropna=True))),
    ))

    chosen = []
    links = []
    for candidate in candidates:
        col = candidate["column"]
        if not chosen:
            chosen.append(candidate)
            continue
        # Insert only where actual parent-child row pairs prove the relationship.
        inserted = False
        for index in range(len(chosen) - 1, -1, -1):
            parent = chosen[index]["column"]
            pairs = df[[col, parent]].dropna().drop_duplicates()
            # Repeated child labels across parents are valid (e.g. two places named
            # Georgia). Keep the relationship and carry the parent key downstream.
            if pairs.empty:
                continue
            # The child should be at least as granular as its proposed parent.
            if df[col].nunique(dropna=True) < df[parent].nunique(dropna=True):
                continue
            chosen.insert(index + 1, candidate)
            links.append((parent, col))
            inserted = True
            break
        if not inserted:
            # A disconnected geography can still be explored independently, but we
            # do not claim it is a child of another field.
            if candidate["semantic_level"] == "country" or not any(
                x["semantic_level"] == candidate["semantic_level"] for x in chosen
            ):
                chosen.append(candidate)

    result = []
    for index, item in enumerate(chosen):
        parent = chosen[index - 1] if index and (chosen[index - 1]["column"], item["column"]) in links else None
        kind = item["semantic_level"]
        entity_type = "administrative_area_level_1" if kind in ("state", "province", "administrative_area_level_1") else "administrative_area_level_2" if kind in ("county", "district", "administrative_area_level_2") else kind
        result.append({
            "id": kind if not any(x["id"] == kind for x in result) else f"{kind}_{index}",
            "level": kind,
            "label": str(item["column"]),
            "column": str(item["column"]),
            "entity_type": entity_type,
            "order": index,
            "parent_column": parent["column"] if parent else None,
            "relationship_verified": bool(parent),
        })
    return result
