import pandas as pd
from .entity_discovery import discover_geo_profile
from .hierarchy_discovery import discover_hierarchy
from .metric_synthesis import resolve_metric, materialize_metric
from .anomaly_detector import detect_anomalies
from .map_data import build_map_data


def run_geo_analysis(df, spec):
    if spec.get("analysis_type") != "geographic_analysis":
        return {"success":False,"error":"Invalid geographic analysis type."}
    profile=discover_geo_profile(df)
    hierarchy=discover_hierarchy(df, profile)
    if not profile["geographic_columns"]:
        return {"success":False,"error":"No geographic fields were detected in this dataset, so geographic analysis cannot be performed."}
    geography_spec = spec.get("geography") or {}
    requested=geography_spec.get("column") or spec.get("geographic_dimension")
    dim=next((c["column"] for c in profile["geographic_columns"] if c["column"].lower()==str(requested).lower()),None)
    if not dim:
        # Resolve the LLM's entity type to the discovered field.
        dim=next((x["column"] for x in hierarchy if x["level"].lower()==str(requested).lower()),None)
    if not dim:
        return {"success":False,"error":f"Geographic field '{requested}' was not found in the dataset."}
    metric_spec=spec.get("metric") or {}
    metric=resolve_metric(df, metric_spec.get("column") or metric_spec.get("name"), metric_spec.get("type","existing_column"))
    if not metric:
        wanted=metric_spec.get("column") or metric_spec.get("name") or "requested metric"
        return {"success":False,"error":f"{wanted.title()} cannot be derived because the dataset does not contain supported required numeric fields."}
    working=df.copy()
    analysis_filters=list(spec.get("filters",[]))
    parent=geography_spec.get("parent")
    if parent and parent.get("column") and not any(
        str(item.get("column","")).casefold()==str(parent["column"]).casefold()
        and str(item.get("value","")).casefold()==str(parent.get("value","")).casefold()
        for item in analysis_filters
    ):
        analysis_filters.append({"column":parent["column"],"operator":"=","value":parent.get("value")})
    for f in analysis_filters:
        col=next((c for c in working.columns if c.lower()==str(f.get("column","")).lower()),None)
        if f.get("operator") == "continent":
            from .geo_resolver import GeoResolver
            resolver = GeoResolver()
            keep = working[col].astype(str).map(resolver.continent_for).str.casefold() == str(f.get("value","")).casefold() if col else pd.Series(False, index=working.index)
            if not col: return {"success":False,"error":f"Filter field '{f.get('column')}' was not found in the dataset."}
            working = working[keep]
            continue
        if not col: return {"success":False,"error":f"Filter field '{f.get('column')}' was not found in the dataset."}
        val=f.get("value"); op=f.get("operator","=")
        if op not in ("=","==","!=","in"): return {"success":False,"error":f"Unsupported geographic filter operator '{op}'."}
        if op in ("=","=="): working=working[working[col].astype(str).str.casefold()==str(val).casefold()]
        elif op=="!=": working=working[working[col].astype(str).str.casefold()!=str(val).casefold()]
        elif op=="in" and isinstance(val,list): working=working[working[col].astype(str).str.casefold().isin([str(v).casefold() for v in val])]
    spec={**spec,"filters":analysis_filters}
    working, metric_col=materialize_metric(working, metric)
    agg=metric_spec.get("aggregation","sum").lower()
    if metric.get("operation") == "count_distinct": agg="count_distinct"
    if agg not in ("sum","average","mean","count_distinct"):
        return {"success":False,"error":f"Unsupported geographic aggregation '{agg}'."}
    values=pd.to_numeric(working[metric_col],errors="coerce")
    # Include verified ancestors in the grouping key. This prevents same-named
    # subdivisions in different parents from being merged (e.g. Georgia).
    hierarchy_columns = [item["column"] for item in hierarchy]
    level_index = next((i for i, item in enumerate(hierarchy) if item["column"] == dim), None)
    group_cols = hierarchy_columns[:level_index + 1] if level_index is not None else [dim]
    group_cols = [c for c in group_cols if c in working.columns]
    if dim not in group_cols: group_cols.append(dim)
    if metric.get("operation") == "count_distinct" or agg == "count_distinct":
        data=working.groupby(group_cols,dropna=True)[metric_col].nunique()
    else:
        data=working.assign(__metric_values=values).groupby(group_cols,dropna=True)["__metric_values"].agg("mean" if agg in ("average","mean") else "sum")
    data=data.sort_values(ascending=(spec.get("comparison",{}).get("direction") in ("lowest","ascending","asc")))
    raw=[]
    for key, value in data.items():
        if pd.isna(value): continue
        key = key if isinstance(key, tuple) else (key,)
        parts = {column: str(part) for column, part in zip(group_cols, key)}
        parents = {column: value for column, value in parts.items() if column != dim}
        label = " — ".join([*parents.values(), parts[dim]])
        raw.append({"location": label, "entity": parts[dim], "parents": parents, "metric": float(value)})
    total=float(sum(x["metric"] for x in raw))
    parent_columns=[column for column in group_cols if column != dim]
    parent_totals={}
    parent_members={}
    for item in raw:
        parent_key=tuple(item["parents"].get(column) for column in parent_columns)
        parent_totals[parent_key]=parent_totals.get(parent_key,0.0)+item["metric"]
        parent_members.setdefault(parent_key,[]).append(item)
    ascending=spec.get("comparison",{}).get("direction") in ("lowest","ascending","asc")
    parent_ranks={}
    parent_medians={}
    for parent_key, members in parent_members.items():
        ordered=sorted(members,key=lambda item:item["metric"],reverse=not ascending)
        for rank,item in enumerate(ordered,1): parent_ranks[(parent_key,item["entity"])]=rank
        parent_medians[parent_key]=float(pd.Series([item["metric"] for item in members]).median())
    transaction_col=next((c for c in working.columns if any(token in c.casefold() for token in ("invoice","order","transaction","receipt"))),None)
    transaction_counts=working.groupby(group_cols,dropna=True)[transaction_col].nunique().to_dict() if transaction_col else {}
    child_column=hierarchy[level_index+1]["column"] if level_index is not None and level_index+1<len(hierarchy) else None
    child_counts={}
    if child_column:
        counts=working.groupby(group_cols,dropna=True)[child_column].nunique(dropna=True)
        for key, count in counts.items():
            key=key if isinstance(key,tuple) else (key,)
            child_counts[tuple(str(value) for value in key)]=int(count)
    rows=[]
    for i,item in enumerate(raw,1):
        parent_key = tuple(item["parents"].get(col) for col in parent_columns)
        transaction_key = parent_key + (item["entity"],)
        if len(transaction_key) == 1: transaction_key = transaction_key[0]
        child_key=tuple([*(item["parents"].get(col) for col in group_cols if col != dim),item["entity"]])
        scoped_total=parent_totals.get(parent_key,total)
        rows.append({dim:item["entity"],"entity":item["entity"],"parents":item["parents"],"location":item["location"],"name":item["location"],"metric":round(item["metric"],4),"value":round(item["metric"],4),"metric_value":round(item["metric"],4),"rank":parent_ranks.get((parent_key,item["entity"]),i),"global_rank":i,"contribution":round(item["metric"]/scoped_total*100,2) if scoped_total else None,"share":round(item["metric"]/scoped_total,6) if scoped_total else None,"transactions":int(transaction_counts.get(transaction_key, 0)) if transaction_col else None,"child_count":child_counts.get(child_key,0) if child_column else 0,"child_dimension":child_column})
    all_rows=rows
    for row in all_rows:
        parent_key=tuple(row.get("parents",{}).get(column) for column in parent_columns)
        median_metric=parent_medians.get(parent_key)
        row["difference_from_median"] = round(row["metric"]-median_metric,4) if median_metric is not None else None
    intent=spec.get("intent","group_comparison")
    anomaly=detect_anomalies(all_rows,"low" if spec.get("comparison",{}).get("direction")=="lowest" else "both") if intent=="anomaly" else None
    limit=spec.get("limit")
    if isinstance(limit,int) and limit > 0:
        selected_name=spec.get("selected_location")
        rows=all_rows[:limit]
        selected_outside=next((r for r in all_rows if selected_name and str(r["location"]).casefold()==str(selected_name).casefold()),None)
        if selected_outside and selected_outside not in rows: rows.append(selected_outside)
    map_data, unresolved, boundary_features=build_map_data(working,rows,dim,profile)
    selected=(anomaly or {}).get("locations",[]) if anomaly else rows[:min(5,len(rows))]
    selected_name=spec.get("selected_location")
    selected_row=next((r for r in rows if str(r["location"]).casefold()==str(selected_name).casefold()),None) if selected_name else None
    answer=(f"{len(rows)} locations were compared by {metric['name']} ({agg}). " + (f"{selected_row[dim]} contributes {selected_row['contribution']}% of the displayed total and ranks #{selected_row['rank']}." if selected_row else f"{len(selected or [])} locations fell outside the robust anomaly threshold." if anomaly else f"{rows[0][dim]} ranks first at {rows[0]['metric']:,.4g}." if rows else "No matching locations were found."))
    evidence={"question":spec.get("question"),"metric":metric,"aggregation":agg,"geographic_level":dim,"group_by":group_cols,"filters":analysis_filters,"baseline":anomaly.get("baseline") if anomaly else None,"anomaly_method":anomaly.get("method") if anomaly else None,"anomaly_threshold":anomaly.get("threshold") if anomaly else None}
    geo_level=next((item for item in hierarchy if item["column"]==dim),{})
    if geo_level.get("entity_type")=="country":
        boundary_status="available" if rows and not unresolved else "partial" if map_data else "unavailable"
    else:
        boundary_status="available" if rows and len(boundary_features)==len(rows) else "partial" if boundary_features else "unavailable"
    boundary_sources=sorted({(feature.get("properties") or {}).get("querylens_boundary_source") for feature in boundary_features if (feature.get("properties") or {}).get("querylens_boundary_source")})
    return {"success":True,"analysis_type":"geographic_analysis","query_spec":spec,"geography":{"column":dim,"level":geo_level.get("id",geo_level.get("level")),"label":geo_level.get("label",dim),"entity_type":geo_level.get("entity_type",next((c["entity_type"] for c in profile["geographic_columns"] if c["column"]==dim),"location")),"parent_columns":group_cols[:-1]},"metric_detail":{"name":metric["name"],"type":"derived" if metric["derived"] else "existing","formula":metric.get("formula"),"required_columns":metric.get("components",[]),"aggregation":agg},"results":rows,"result":{"metric":metric["name"],"dimension":dim,"ranking":"ascending" if spec.get("comparison",{}).get("direction") in ("lowest","ascending","asc") else "descending","locations":rows,"anomaly":anomaly},"geo":{"profile":profile,"hierarchy":hierarchy,"locations":rows,"map_data":map_data,"unresolved_count":unresolved},"map":{"type":"choropleth" if geo_level.get("entity_type")=="country" else "administrative_choropleth" if boundary_features else "dataset_coordinates","boundary_status":boundary_status,"boundary_sources":boundary_sources,"features":map_data,"boundaries":{"type":"FeatureCollection","features":boundary_features} if boundary_features else None},"visualization":{"type":"geo_map","supporting":"anomaly_distribution" if anomaly else "horizontal_bar"},"evidence":evidence,"answer":answer}
