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
    requested=spec.get("geographic_dimension")
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
    for f in spec.get("filters",[]):
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
    working, metric_col=materialize_metric(working, metric)
    agg=metric_spec.get("aggregation","sum").lower()
    if metric.get("operation") == "count_distinct": agg="count_distinct"
    if agg not in ("sum","average","mean","count_distinct"):
        return {"success":False,"error":f"Unsupported geographic aggregation '{agg}'."}
    values=pd.to_numeric(working[metric_col],errors="coerce")
    if metric.get("operation") == "count_distinct" or agg == "count_distinct":
        data=working.groupby(dim,dropna=True)[metric_col].nunique()
    else:
        data=working.assign(__metric_values=values).groupby(dim,dropna=True)["__metric_values"].agg("mean" if agg in ("average","mean") else "sum")
    data=data.sort_values(ascending=(spec.get("comparison",{}).get("direction") in ("lowest","ascending","asc")))
    raw=[{"location":str(k),"metric":float(v)} for k,v in data.items() if pd.notna(v)]
    total=float(sum(x["metric"] for x in raw))
    transaction_col=next((c for c in working.columns if any(token in c.casefold() for token in ("invoice","order","transaction","receipt"))),None)
    transaction_counts=working.groupby(dim,dropna=True)[transaction_col].nunique().to_dict() if transaction_col else {}
    rows=[]
    for i,item in enumerate(raw,1):
        rows.append({dim:item["location"],"location":item["location"],"name":item["location"],"metric":round(item["metric"],4),"value":round(item["metric"],4),"metric_value":round(item["metric"],4),"rank":i,"contribution":round(item["metric"]/total*100,2) if total else None,"share":round(item["metric"]/total,6) if total else None,"transactions":int(transaction_counts[item["location"]]) if transaction_col else None})
    all_rows=rows
    median_metric=float(pd.Series([r["metric"] for r in all_rows]).median()) if all_rows else None
    for row in all_rows:
        row["difference_from_median"] = round(row["metric"]-median_metric,4) if median_metric is not None else None
    intent=spec.get("intent","group_comparison")
    anomaly=detect_anomalies(all_rows,"low" if spec.get("comparison",{}).get("direction")=="lowest" else "both") if intent=="anomaly" else None
    limit=spec.get("limit")
    if isinstance(limit,int) and limit > 0:
        selected_name=spec.get("selected_location")
        rows=all_rows[:limit]
        selected_outside=next((r for r in all_rows if selected_name and str(r[dim]).casefold()==str(selected_name).casefold()),None)
        if selected_outside and selected_outside not in rows: rows.append(selected_outside)
    map_data, unresolved=build_map_data(working,rows,dim,profile)
    selected=(anomaly or {}).get("locations",[]) if anomaly else rows[:min(5,len(rows))]
    selected_name=spec.get("selected_location")
    selected_row=next((r for r in rows if str(r[dim]).casefold()==str(selected_name).casefold()),None) if selected_name else None
    answer=(f"{len(rows)} locations were compared by {metric['name']} ({agg}). " + (f"{selected_row[dim]} contributes {selected_row['contribution']}% of the displayed total and ranks #{selected_row['rank']}." if selected_row else f"{len(selected or [])} locations fell outside the robust anomaly threshold." if anomaly else f"{rows[0][dim]} ranks first at {rows[0]['metric']:,.4g}." if rows else "No matching locations were found."))
    evidence={"question":spec.get("question"),"metric":metric,"aggregation":agg,"geographic_level":dim,"filters":spec.get("filters",[]),"baseline":anomaly.get("baseline") if anomaly else None,"anomaly_method":anomaly.get("method") if anomaly else None,"anomaly_threshold":anomaly.get("threshold") if anomaly else None}
    return {"success":True,"analysis_type":"geographic_analysis","query_spec":spec,"geography":{"column":dim,"entity_type":next((c["entity_type"] for c in profile["geographic_columns"] if c["column"]==dim),"location")},"metric_detail":{"name":metric["name"],"type":"derived" if metric["derived"] else "existing","formula":metric.get("formula"),"required_columns":metric.get("components",[]),"aggregation":agg},"results":rows,"result":{"metric":metric["name"],"dimension":dim,"ranking":"ascending" if spec.get("comparison",{}).get("direction") in ("lowest","ascending","asc") else "descending","locations":rows,"anomaly":anomaly},"geo":{"profile":profile,"hierarchy":hierarchy,"locations":rows,"map_data":map_data,"unresolved_count":unresolved},"map":{"type":"choropleth" if next((c["entity_type"] for c in profile["geographic_columns"] if c["column"]==dim),None)=="country" else "points","features":map_data},"visualization":{"type":"geo_map","supporting":"anomaly_distribution" if anomaly else "horizontal_bar"},"evidence":evidence,"answer":answer}
