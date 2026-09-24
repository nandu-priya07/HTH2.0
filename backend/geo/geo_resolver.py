from functools import lru_cache
from pathlib import Path
import json
import re
import os
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import pandas as pd


def _norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


_COUNTRY_ALIASES = {
    "us": "unitedstates", "usa": "unitedstates", "unitedstatesofamerica": "unitedstates",
    "uk": "unitedkingdom", "greatbritain": "unitedkingdom", "britain": "unitedkingdom",
}


def _country_norm(value):
    normalized=_norm(value)
    return _COUNTRY_ALIASES.get(normalized, normalized)


def _admin_norm(value):
    normalized=_norm(value)
    for suffix in ("state", "province", "unionterritory", "territory"):
        if normalized.endswith(suffix) and len(normalized)>len(suffix):
            normalized=normalized[:-len(suffix)]
            break
    return normalized


ADMIN1_GEOJSON_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_1_states_provinces.geojson"
ADMIN1_BUNDLED_PATH = Path(__file__).resolve().parents[2] / "frontend" / "public" / "geo" / "ne_50m_admin_1_states_provinces.geojson"
GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/{iso3}/ADM1/"


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

    @staticmethod
    @lru_cache(maxsize=2)
    def _admin_features(source):
        """Load and cache real admin GeoJSON, preferring a configured local dataset."""
        if not source:
            return ()
        try:
            if source.startswith("https://"):
                request=Request(source,headers={"User-Agent":"QueryLens-GeoExplorer/1.0"})
                with urlopen(request,timeout=12) as response:
                    payload=response.read(20_000_001)
                if len(payload)>20_000_000:
                    return ()
                data=json.loads(payload.decode("utf-8"))
            else:
                data = json.loads(Path(source).expanduser().resolve().read_text(encoding="utf-8"))
            return tuple(data.get("features", ()))
        except (OSError, json.JSONDecodeError, AttributeError, TimeoutError, ValueError):
            return ()

    @staticmethod
    @lru_cache(maxsize=2)
    def _admin_index(source, level):
        name_keys=(f"NAME_{level}",f"name_{level}","name","NAME","shapeName","admin1Name","admin2Name")
        parent_keys=(f"NAME_{level-1}",f"name_{level-1}","parent","country","admin_0","admin","geonunit")
        index={}
        for feature in GeoResolver._admin_features(source):
            props=feature.get("properties") or {}
            label=next((props.get(key) for key in name_keys if props.get(key)),None)
            parent=next((props.get(key) for key in parent_keys if props.get(key)),None)
            if label:
                index.setdefault(_admin_norm(label),[]).append((str(parent or ""),feature))
        return {name:tuple(matches) for name,matches in index.items()}

    @staticmethod
    @lru_cache(maxsize=4096)
    def _cached_admin_match(source, level, name, parent):
        candidates=GeoResolver._admin_index(source,level).get(name,())
        if parent:
            candidates=tuple(item for item in candidates if _country_norm(item[0])==parent)
        return candidates[0] if len(candidates)==1 else None

    @staticmethod
    @lru_cache(maxsize=100)
    def _geoboundary_features(iso3):
        """Lazy country-scoped fallback for admin-1 units absent from Natural Earth."""
        try:
            request=Request(GEOBOUNDARIES_API.format(iso3=iso3),headers={"User-Agent":"QueryLens-GeoExplorer/1.0"})
            with urlopen(request,timeout=12) as response:
                metadata=json.loads(response.read(1_000_001).decode("utf-8"))
            if isinstance(metadata,list): metadata=metadata[0] if metadata else {}
            download=metadata.get("simplifiedGeometryGeoJSON") or metadata.get("gjDownloadURL")
            parsed=urlparse(download or "")
            if parsed.scheme!="https" or parsed.hostname not in ("github.com","raw.githubusercontent.com"):
                return (), {}
            request=Request(download,headers={"User-Agent":"QueryLens-GeoExplorer/1.0"})
            with urlopen(request,timeout=18) as response:
                payload=response.read(20_000_001)
            if len(payload)>20_000_000: return (),metadata
            data=json.loads(payload.decode("utf-8"))
            return tuple(data.get("features",())),metadata
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
            return (),{}

    @staticmethod
    def _resolve_from_geoboundaries(names, parent_country):
        if not parent_country:
            return {},[]
        catalog=_country_catalog()
        country=catalog.get(_country_norm(parent_country)) or catalog.get(_norm(parent_country))
        iso3=(country or {}).get("iso_a3")
        if not iso3 or len(str(iso3))!=3:
            return {},[]
        features,metadata=GeoResolver._geoboundary_features(str(iso3))
        by_name={}
        for feature in features:
            props=feature.get("properties") or {}
            name=next((props.get(key) for key in ("shapeName","NAME_1","name_1","name","NAME") if props.get(key)),None)
            if name: by_name.setdefault(_admin_norm(name),[]).append((str(name),feature))
        resolved,selected_features={},[]
        for requested in names:
            candidates=by_name.get(_admin_norm(requested),[])
            if len(candidates)!=1: continue
            canonical,feature=candidates[0]
            props=feature.get("properties") or {}
            source=f"geoBoundaries gbOpen · {metadata.get('boundarySource','') or metadata.get('boundaryID','ADM1')} · {metadata.get('boundaryLicense','CC BY 4.0')}"
            feature={**feature,"properties":{**props,"querylens_name":requested,"querylens_parent":parent_country,"querylens_boundary_source":source}}
            resolved[str(requested)]={"geometry_name":str(requested),"parent_name":str(parent_country),"boundary_source":source}
            selected_features.append(feature)
        return resolved,selected_features

    def resolve_admin_boundaries(self, names, entity_type, parents=None):
        """Join names plus parent context to real admin GeoJSON features.

        Use an explicit local layer first, then the bundled Natural Earth Admin-1 file;
        use its fixed upstream only if the application bundle is incomplete.
        """
        source = os.environ.get("QUERYLENS_ADMIN_BOUNDARIES_GEOJSON") or (str(ADMIN1_BUNDLED_PATH) if ADMIN1_BUNDLED_PATH.exists() else ADMIN1_GEOJSON_URL)
        level = 2 if "level_2" in str(entity_type) or "district" in str(entity_type) or str(entity_type) in ("city", "municipality", "town", "village") else 1
        name_keys = (f"NAME_{level}", f"name_{level}", "name", "NAME", "shapeName", "admin1Name", "admin2Name")
        resolved, boundary_features = {}, []
        parents = parents or {}
        parent_value = next(reversed(parents.values()), None) if parents else None
        for name in names:
            if level == 1 and parent_value is None:
                continue
            match=self._cached_admin_match(source,level,_admin_norm(name),_country_norm(parent_value) if parent_value is not None else "")
            if match is None:
                continue
            parent, feature = match
            props = feature.get("properties") or {}
            label = next((props.get(k) for k in name_keys if props.get(k)), name)
            resolved[str(name)] = {"geometry_name": str(label), "parent_name": parent}
            boundary_features.append(feature)
        missing=[name for name in names if str(name) not in resolved]
        if missing and parent_value is not None and level==1:
            extra,extra_features=self._resolve_from_geoboundaries(missing,parent_value)
            resolved.update(extra)
            boundary_features.extend(extra_features)
        return resolved, boundary_features, len(names) - len(resolved)

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


class GeoBoundaryProvider:
    """Boundary lookup interface joining a normalized entity to real GeoJSON."""

    def __init__(self, resolver=None):
        self.resolver=resolver or GeoResolver()

    def resolve_boundary(self, *, entity_type, name, parent_name=None, parent_country=None):
        parent=parent_country or parent_name
        context={"parent":parent} if parent else None
        resolved, features, _ = self.resolver.resolve_admin_boundaries([name],entity_type,context)
        if not resolved or not features:
            return None
        feature=features[0]
        properties=feature.get("properties") or {}
        source=next(iter(resolved.values())).get("boundary_source") or "Natural Earth 1:50m Admin-1"
        properties={**properties,"querylens_name":name,"querylens_parent":parent,"querylens_boundary_source":source}
        return {
            "name":name,
            "normalized_name":_admin_norm(name),
            "parent":parent,
            "boundary_source":source,
            "type":"Feature",
            "geometry":feature.get("geometry"),
            "properties":properties,
        }
