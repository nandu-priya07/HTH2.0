import re
from typing import Any, Dict, Optional


DECISION_RE = re.compile(
    r"\b(should (?:we|i)|how much should|what level should|at what point should|"
    r"which .* should .* focus|which .* gives .* improvement|how much .* (?:increase|decrease|change)|"
    r"what percentage .* (?:required|increase|reach)|by what percentage .* increase|what if .* (?:increase|decrease)|"
    r"decision boundary|diminishing returns|intervention)\b", re.I
)
FOLLOWUP_RE = re.compile(r"\b(what if|could .* affecting|counter.?test|decision boundary|decision visually|show .* decision)\b", re.I)


def detect_decision(question: str, columns=None, previous_trace: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Conservative decision intent detection; ordinary descriptive queries stay in analyst flow."""
    text = (question or "").strip()
    matched = bool(DECISION_RE.search(text)) or bool(previous_trace and FOLLOWUP_RE.search(text))
    if not matched:
        return {"is_decision": False}
    cols = list(columns) if columns is not None else []
    lower = text.lower()
    target = next((c for c in cols if re.search(r"\b" + re.escape(str(c).lower()) + r"\b", lower)), None)
    if not target and previous_trace:
        target = previous_trace.get("intent", {}).get("target_metric")
    goal = "reach_target" if re.search(r"\b(reach|achieve|target|goal|at least)\b", lower) else "improve_outcome"
    currency = re.search(r"(?:₹|\$|€|£)\s*([\d,.]+)\s*([kKmMbB])?", text)
    target_value = None
    if currency:
        target_value = float(currency.group(1).replace(",", ""))
        target_value *= {"k": 1e3, "m": 1e6, "b": 1e9}.get((currency.group(2) or "").lower(), 1)
    explicit = re.search(r"\b(\d+(?:\.\d+)?)\s*%", text)
    return {"is_decision": True, "decision_question": text, "target_metric": target,
            "objective": goal, "decision_variable": target if explicit else None,
            "target_value": target_value, "constraints": [], "assumptions": [],
            "requested_percent": float(explicit.group(1)) if explicit else None}
