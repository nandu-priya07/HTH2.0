import re
import pandas as pd

# Controlled expressions only; no evaluation of model supplied code.
DERIVED_METRICS = {
    "revenue": {"required": ("quantity", "price"), "formula": "quantity * price"},
    "orders": {"required": ("orders",), "formula": "count_distinct(orders)"},
    "profit": {"required": ("revenue", "cost"), "formula": "revenue - cost"},
    "profit margin": {"required": ("profit", "revenue"), "formula": "profit / revenue"},
    "profit_margin": {"required": ("profit", "revenue"), "formula": "profit / revenue"},
    "average order value": {"required": ("revenue", "orders"), "formula": "revenue / orders"},
    "average_order_value": {"required": ("revenue", "orders"), "formula": "revenue / orders"},
    "conversion rate": {"required": ("conversions", "visits"), "formula": "conversions / visits"},
    "conversion_rate": {"required": ("conversions", "visits"), "formula": "conversions / visits"}
}
ALIASES = {"revenue": ("revenue", "sales", "amount"), "cost": ("cost", "expense"), "profit": ("profit", "margin"), "orders": ("order", "orders", "transaction", "invoice", "receipt"), "conversions": ("conversion", "conversions"), "visits": ("visit", "visits", "sessions")}
ALIASES["quantity"] = ("quantity", "qty", "units")
ALIASES["price"] = ("price", "unitprice", "unit_price")

def resolve_metric(df, requested, metric_type="existing_column"):
    canonical_names={"revenue":"Revenue","profit":"Profit","profit margin":"Profit Margin","profit_margin":"Profit Margin","average order value":"Average Order Value","average_order_value":"Average Order Value","conversion rate":"Conversion Rate","conversion_rate":"Conversion Rate","orders":"Orders"}
    names = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in df.columns}
    norm = re.sub(r"[^a-z0-9]", "", str(requested).lower())
    if norm in names and pd.api.types.is_numeric_dtype(df[names[norm]]):
        return {"column": names[norm], "name": canonical_names.get(str(requested).lower().strip(), names[norm]), "formula": None, "derived": False}
    # semantic direct match before derivation
    for c in df.columns:
        cn = re.sub(r"[^a-z0-9]", "", c.lower())
        if norm and (norm in cn or cn in norm) and pd.api.types.is_numeric_dtype(df[c]):
            return {"column": c, "name": canonical_names.get(str(requested).lower().strip(), c), "formula": None, "derived": False}
    definition = DERIVED_METRICS.get(str(requested).lower().strip())
    if not definition: return None
    display_name=canonical_names.get(str(requested).lower().strip(),str(requested))
    resolved = {}
    for concept in definition["required"]:
        aliases = ALIASES[concept]
        match = next((c for c in df.columns if any(a in re.sub(r"[^a-z0-9]", "", c.lower()) for a in aliases) and (concept == "orders" or pd.api.types.is_numeric_dtype(df[c]))), None)
        if concept == "profit" and not match:
            profit = DERIVED_METRICS["profit"]
            rev = next((c for c in df.columns if any(a in c.lower() for a in ALIASES["revenue"]) and pd.api.types.is_numeric_dtype(df[c])), None)
            cost = next((c for c in df.columns if "cost" in c.lower() and pd.api.types.is_numeric_dtype(df[c])), None)
            if rev and cost: resolved[concept] = ("derived_profit", rev, cost); continue
        if not match: return None
        resolved[concept] = match
    if definition["formula"] == "revenue - cost":
        a,b = resolved["revenue"],resolved["cost"]
        return {"column":"__derived_metric__", "name":display_name, "formula":f"{a} - {b}", "derived":True, "components":[a,b], "operation":"subtract"}
    if definition["formula"] == "quantity * price":
        a,b = resolved["quantity"],resolved["price"]
        return {"column":"__derived_metric__", "name":display_name, "formula":f"{a} * {b}", "derived":True, "components":[a,b], "operation":"multiply"}
    if definition["formula"] == "count_distinct(orders)":
        col=resolved["orders"]
        return {"column":col, "name":display_name, "formula":f"COUNT DISTINCT({col})", "derived":True, "components":[col], "operation":"count_distinct"}
    if definition["formula"] == "profit / revenue":
        p,r = resolved["profit"],resolved["revenue"]
        if isinstance(p, tuple): return None
        return {"column":"__derived_metric__", "name":display_name, "formula":f"{p} / {r}", "derived":True, "components":[p,r], "operation":"divide"}
    return None

def materialize_metric(df, metric):
    if not metric.get("derived"): return df, metric["column"]
    if metric.get("operation") == "count_distinct": return df, metric["column"]
    out = df.copy(); a,b = metric["components"]
    av,bv = pd.to_numeric(out[a], errors="coerce"), pd.to_numeric(out[b], errors="coerce")
    if metric["operation"] == "subtract": out["__derived_metric__"] = av - bv
    elif metric["operation"] == "multiply": out["__derived_metric__"] = av * bv
    else: out["__derived_metric__"] = av.div(bv.where(bv != 0))
    return out, "__derived_metric__"
