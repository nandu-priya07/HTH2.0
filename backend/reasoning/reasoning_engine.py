"""
Analytical Reasoning Engine.
Receives user question, QuerySpec, canonical analytical result, and evidence payload.
Interprets analytical computations without inventing numbers or hallucinating causes.
Uses strict JSON response structure with deterministic fallback.
"""

from typing import Any, Dict, List, Optional
import json
import logging
import re
from analyst.models import QuerySpec, QueryResult
from llm.client import OllamaClient

logger = logging.getLogger(__name__)

REASONING_SYSTEM_PROMPT = """You are an expert AI Data Analyst reasoning engine.
Your sole job is to interpret pre-computed, canonical analytical results and provide clear, evidence-backed analytical reasoning.

CRITICAL RULES:
1. STRICT GROUNDING: You MUST ONLY use the numbers, dates, trends, and metrics supplied in the Canonical Result and Evidence.
2. NO HALLUCINATION: You MUST NEVER invent numerical facts, dates, forecasts, or causes not present in the evidence.
3. CAUSALITY SAFETY: Do NOT claim a relationship is causal unless explicit contribution evidence is provided. If evidence is insufficient, state that the dataset does not provide explicit causal reasons.
4. STRUCTURED OUTPUT: You MUST return a valid JSON object only. No markdown fences outside the JSON.

Expected JSON schema for standard analytics:
{
  "summary": "High-level direct synthesis of the computed result",
  "key_findings": [
    "Key finding 1 with exact numbers",
    "Key finding 2 with exact numbers"
  ],
  "reasoning": [
    "Analytical interpretation line 1",
    "Analytical interpretation line 2"
  ],
  "limitations": [
    "Dataset limitation or assumption if applicable"
  ]
}

Expected JSON schema for forecasts:
{
  "summary": "Summary of historical direction and projected horizon forecast",
  "trend": "Description of historical pattern influencing model",
  "forecast_interpretation": "Detailed breakdown of future projected values",
  "uncertainty": "Explanation of prediction interval / confidence bounds",
  "limitations": "Model limitations and assumptions"
}
"""


def should_invoke_reasoning(question: str, spec: QuerySpec, result: QueryResult) -> bool:
    """
    Decision Policy for Reasoning LLM:
    Level 1 (Deterministic): FALSE -> sum, avg, count, min, max, ranking, lookup, distribution.
    Level 2 & 3 (Complex / Interpretive): TRUE -> dataset_summary, trend, forecast, anomaly, why/cause, decision.
    """
    if not result or not result.success:
        return False

    op = (spec.operation or "").lower().strip()
    query_intent = (result.query.get("intent") or "") if isinstance(result.query, dict) else ""
    intent = (spec.intent or query_intent or "").lower().strip()

    # Special Analytical Operations ALWAYS require interpretation
    if op in ("dataset_summary", "trend", "forecast", "anomaly_detection", "complex_insight", "decision_analysis", "why", "cause"):
        return True
    if intent in ("dataset_summary", "trend", "forecast", "anomaly_detection", "complex_insight", "decision_analysis", "why", "cause"):
        return True

    # Check question keywords for natural language interpretation triggers
    q_lower = (question or "").lower()
    analytical_keywords = (
        "why", "explain", "interpret", "how come", "what caused", "reason",
        "predict", "forecast", "should we", "prioritize", "recommend",
        "unusual", "outlier", "anomaly", "pattern", "insight", "underperform"
    )
    if any(re.search(rf"\b{re.escape(kw)}\b", q_lower) for kw in analytical_keywords):
        return True

    # Level 1 Deterministic queries MUST stay fast (False)
    return False


def generate_analytical_reasoning(
    question: str,
    spec: QuerySpec,
    result: QueryResult
) -> Optional[Dict[str, Any]]:
    """
    Generates structured analytical reasoning using Ollama Qwen3 model.
    Falls back gracefully to deterministic explanation if LLM call fails.
    """
    if not should_invoke_reasoning(question, spec, result):
        return None

    client = OllamaClient()
    if not client.is_available():
        return _deterministic_fallback_reasoning(question, spec, result)

    # Build compact analytical context (NO RAW DATASETS!)
    canonical = result.canonical_data or result.result or {}
    evidence_payload = {
        "operation": spec.operation,
        "raw_question": question,
        "fields_used": result.fields_used,
        "rows_analyzed": result.metadata.get("rows_analyzed") if result.metadata else None,
        "canonical_summary": canonical,
        "calculation_steps": result.calculation_steps
    }

    user_prompt = f"""User Question: "{question}"

Canonical Computed Result:
{json.dumps(evidence_payload, indent=2, default=str)}

Interpret this computed result adhering to all critical rules. Provide structured JSON."""

    try:
        raw_json = client.generate_json(
            system_prompt=REASONING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            think=False
        )

        if raw_json and isinstance(raw_json, dict) and ("summary" in raw_json or "key_findings" in raw_json):
            return raw_json
    except Exception as e:
        logger.warning(f"Analytical reasoning LLM generation failed ({e}). Using deterministic fallback.")

    return _deterministic_fallback_reasoning(question, spec, result)


def _deterministic_fallback_reasoning(
    question: str,
    spec: QuerySpec,
    result: QueryResult
) -> Dict[str, Any]:
    """
    Fallback explanation generator when LLM is unavailable or fails.
    """
    canonical = result.canonical_data or {}
    op = (spec.operation or "").lower()

    if op == "forecast" or canonical.get("intent") == "forecast":
        metric = canonical.get("metric", "metric")
        fc_items = canonical.get("forecast", [])
        model = canonical.get("model", "Statistical Model")
        conf = canonical.get("confidence", "Moderate")

        fc_summary = ", ".join(f"{f['period']}: {f['predicted']:,.2f}" for f in fc_items)
        return {
            "summary": f"Projected {metric} for the next {len(fc_items)} periods using {model}.",
            "trend": f"The model evaluated historical periods and calculated future values: {fc_summary}.",
            "forecast_interpretation": f"Forecast relies on baseline and trend parameters fitted over historical series.",
            "uncertainty": f"Confidence rating is {conf}. Prediction bounds widen as horizon extends.",
            "limitations": "Forecast assumes historical underlying distribution and trend remain stable."
        }
    elif op == "anomaly_detection" or canonical.get("intent") == "anomaly_detection":
        anomalies = canonical.get("anomalies", [])
        return {
            "summary": f"Identified {len(anomalies)} statistical anomalies exceeding 2.0 standard deviations.",
            "key_findings": [f"Anomaly in {a['period']}: value {a['value']:,.2f} vs expected {a['expected']:,.2f}" for a in anomalies[:3]],
            "reasoning": ["Deviation calculated using Z-Score statistical threshold."],
            "limitations": "Detection is based strictly on numerical variance within the current dataset."
        }
    elif op == "trend" or canonical.get("intent") == "trend":
        direction = canonical.get("trend_direction", "stable")
        peak = canonical.get("peak", {})
        trough = canonical.get("trough", {})
        return {
            "summary": f"Historical series exhibits an overall {direction} trend.",
            "key_findings": [
                f"Peak reached in {peak.get('period', 'N/A')} at {peak.get('value', 0):,.2f}.",
                f"Trough recorded in {trough.get('period', 'N/A')} at {trough.get('value', 0):,.2f}."
            ],
            "reasoning": [f"Evaluated period-over-period delta and slope direction."],
            "limitations": "Trend is calculated chronologically across available time entries."
        }
    else:
        return {
            "summary": result.text or "Computed analysis based on dataset records.",
            "key_findings": result.calculation_steps or [f"Analyzed {result.rows_before_filter or 0} records."],
            "reasoning": ["Result computed deterministically by analytics engine."],
            "limitations": ["Analysis is limited to fields and records present in dataset."]
        }
