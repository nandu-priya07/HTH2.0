from typing import Optional
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from geo.entity_discovery import discover_geo_profile
from geo.hierarchy_discovery import discover_hierarchy
from geo.metric_synthesis import resolve_metric
from storage.dataset_manager import get_or_load_dataset
from chat import get_chat_service

router = APIRouter(tags=["explorer"])

def _chat_dataset(chat_id: str, requested_file: Optional[str] = None):
    service = get_chat_service()
    conversation = service.get_conversation(chat_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Chat not found.")
    files = service.get_files(chat_id)
    file_ids = {f.get("file_id") for f in files}
    chosen = requested_file or conversation.dataset_id
    if not chosen and files:
        chosen = files[-1].get("file_id")
    if not chosen:
        raise HTTPException(status_code=404, detail="No dataset is attached to this chat.")
    if chosen not in file_ids and chosen != conversation.dataset_id:
        raise HTTPException(status_code=403, detail="The selected dataset does not belong to this chat.")
    dataset = get_or_load_dataset(chosen, chat_id=chat_id)
    if not dataset or not isinstance(dataset.get("data"), pd.DataFrame):
        raise HTTPException(status_code=404, detail="The selected dataset could not be loaded.")
    file_meta = next((f for f in files if f.get("file_id") == chosen), {})
    return conversation, file_meta, dataset

@router.get("/api/chats/{chat_id}/explorer")
async def get_explorer_context(chat_id: str, file_id: Optional[str] = Query(default=None)):
    """Return schema-derived dimensions and metrics for this chat's selected file."""
    _, file_meta, dataset = _chat_dataset(chat_id, file_id)
    df = dataset["data"]
    profile = discover_geo_profile(df)
    hierarchy = discover_hierarchy(df, profile)
    metrics = []
    for column in df.columns:
        if pd.api.types.is_numeric_dtype(df[column]) and not any(token in column.casefold() for token in ("id", "code", "postal", "zip", "invoice", "order", "transaction", "receipt")):
            metrics.append({"name": str(column), "column": str(column), "type": "existing", "aggregation": "sum"})
    revenue = resolve_metric(df, "Revenue")
    if revenue and not any(m["name"].casefold() == "revenue" for m in metrics):
        metrics.insert(0, {"name": "Revenue", "column": revenue["column"], "type": "derived" if revenue["derived"] else "existing", "formula": revenue.get("formula"), "required_columns": revenue.get("components", []), "aggregation": "sum"})
    orders = resolve_metric(df, "Orders")
    if orders and not any(m["name"].casefold() == "orders" for m in metrics):
        metrics.append({"name": "Orders", "column": orders["column"], "type": "derived", "formula": orders.get("formula"), "required_columns": orders.get("components", []), "aggregation": "count_distinct"})
    meta = dataset.get("metadata") or {}
    return {"chat_id": chat_id, "dataset": {"file_id": dataset.get("dataset_id"), "filename": file_meta.get("filename") or dataset.get("filename"), "rows": int(meta.get("row_count", len(df))), "columns": int(meta.get("column_count", len(df.columns)))}, "geographic_dimensions": profile["geographic_columns"], "hierarchy": hierarchy, "metrics": metrics, "default_metric": metrics[0]["name"] if metrics else None}
