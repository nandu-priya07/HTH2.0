"""
Natural-language answers for executed QueryLens queries.

Pipeline:
    QueryResult (deterministic numbers)
        -> facts        (pre-formatted strings, the only numbers allowed in the answer)
        -> draft        (deterministic template answer, always available)
        -> Qwen3 polish (optional; rejected unless every number it states appears in the facts)

The LLM never calculates: totals, shares and rankings are computed here from the
executor's output, and the model may only rephrase them.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .models import QuerySpec, QueryResult
from .semantics import CONCEPTS, display_name, humanize, is_monetary, column_tokens

logger = logging.getLogger(__name__)

CURRENCY_SYMBOL = os.environ.get("QUERYLENS_CURRENCY_SYMBOL", "$")
STANDARD_OPS = {"sum", "average", "mean", "min", "max", "count", "count_distinct", "distinct"}
_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"]


# ==============================================================================
# Formatting
# ==============================================================================

def format_value(value: Any, monetary: bool = False) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if monetary:
        sign = "-" if value < 0 else ""
        return f"{sign}{CURRENCY_SYMBOL}{abs(value):,.2f}"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def format_percent(p: float) -> str:
    if p >= 99.5 and p < 100:
        return "over 99%"
    if p >= 10:
        return f"{round(p):.0f}%"
    if p >= 1:
        return f"{p:.1f}%"
    return "less than 1%"


def _label(value: Any) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "(blank)"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _join(items: List[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + (", and " if len(items) > 2 else " and ") + items[-1]


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _count(n: Any, noun: str) -> str:
    return f"{format_value(n)} {noun}{'' if n == 1 else 's'}"


# ==============================================================================
# Filter descriptions
# ==============================================================================

def _f_get(f: Any, key: str, default: Any = None) -> Any:
    return f.get(key, default) if isinstance(f, dict) else getattr(f, key, default)


def _period_label(v1: Any, v2: Any) -> Optional[str]:
    """'2024-01-01'..'2024-12-31' -> '2024'; whole months / quarters get their names."""
    m1 = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(v1))
    m2 = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(v2))
    if not (m1 and m2):
        return None
    y1, mo1, d1 = map(int, m1.groups())
    y2, mo2, d2 = map(int, m2.groups())
    import calendar
    whole_start = d1 == 1
    whole_end = d2 == calendar.monthrange(y2, mo2)[1]
    if not (whole_start and whole_end):
        return None
    if y1 == y2 and mo1 == 1 and mo2 == 12:
        return str(y1)
    if y1 == y2 and mo1 == mo2:
        return f"{_MONTH_NAMES[mo1 - 1]} {y1}"
    if y1 == y2 and mo2 - mo1 == 2 and mo1 in (1, 4, 7, 10):
        return f"Q{(mo1 - 1) // 3 + 1} {y1}"
    if mo1 == 1 and mo2 == 12:
        return f"{y1}–{y2}"
    return None


def _is_temporal_col(col: str) -> bool:
    return bool(set(column_tokens(col)) & {"year", "yr", "fy", "date", "time", "month", "period", "day"})


def describe_filters(filters: List[Any], style: str = "phrase") -> str:
    """
    style="phrase": ' for Canada in 2024' style (leading preposition, used after a metric)
    style="values": 'Canada in 2024' (used in 'no records for ...')
    """
    categorical, temporal = [], []
    for f in filters or []:
        col = str(_f_get(f, "column", ""))
        op = str(_f_get(f, "operator", "=")).lower()
        val = _f_get(f, "value")
        is_temporal = _is_temporal_col(col)

        if op in ("between", "range") and isinstance(val, (list, tuple)) and len(val) == 2:
            period = _period_label(val[0], val[1])
            if period:
                temporal.append(f"in {period}")
            elif is_temporal and all(isinstance(v, (int, float)) for v in val):
                temporal.append(f"in {_label(val[0])}–{_label(val[1])}")
            else:
                categorical.append(f"where {humanize(col)} is between {_label(val[0])} and {_label(val[1])}")
        elif op in ("=", "==", "equals", "eq", "is"):
            if is_temporal:
                temporal.append(f"in {_label(val)}")
            else:
                categorical.append(f"for {_label(val)}")
        elif op in ("in", "is_in") and isinstance(val, (list, tuple)):
            (temporal if is_temporal else categorical).append(
                ("in " if is_temporal else "for ") + _join([_label(v) for v in val]))
        elif op in ("!=", "<>", "not_equals", "neq", "is_not"):
            categorical.append(f"excluding {_label(val)}")
        elif op == "contains":
            categorical.append(f"where {humanize(col)} contains '{val}'")
        else:
            sym = {"gt": ">", "gte": "≥", ">=": "≥", "lt": "<", "lte": "≤", "<=": "≤"}.get(op, op)
            categorical.append(f"where {humanize(col)} {sym} {_label(val)}")

    phrase = " ".join(p for p in [" and ".join(categorical), " ".join(temporal)] if p).strip()
    if style == "values":
        phrase = re.sub(r"^(for|in)\s+", "", phrase)
    return phrase


# ==============================================================================
# Metric labels
# ==============================================================================

def _metric_info(spec: QuerySpec, result: QueryResult) -> Tuple[str, bool, Optional[str]]:
    """(inline metric label, is_monetary, extra note)."""
    derived = spec.derived_metric
    note = None
    if derived is not None:
        concept = CONCEPTS.get(derived.name)
        label = concept.label if concept else humanize(derived.name)
        monetary = is_monetary(derived.name)
        if derived.kind == "expression":
            note = f"calculated as {derived.formula}"
        else:
            note = f"counted as distinct {display_name(derived.source_column)} values"
        return label, monetary, note

    mapping = spec.metric_mapping or {}
    if mapping.get("via_synonym") and mapping.get("requested") in CONCEPTS:
        label = CONCEPTS[mapping["requested"]].label
        note = f"using the {display_name(mapping['column'])} field"
        return label, is_monetary(mapping["requested"]), note

    col = spec.column
    if not col:
        return "records", False, None
    return humanize(col), is_monetary(col), None


# ==============================================================================
# Facts + draft
# ==============================================================================

def _scalar_sentence(spec: QuerySpec, result_value: Any, rows: Optional[int], metric: str,
                     monetary: bool, note: Optional[str], filters_phrase: str) -> Tuple[str, Dict[str, Any]]:
    op = (spec.operation or "sum").lower()
    fp = f" {filters_phrase}" if filters_phrase else ""
    rows_txt = f" across {_count(rows, 'record')}" if isinstance(rows, int) else ""
    value_txt = format_value(result_value, monetary and op != "count")
    facts = {"value": value_txt, "records": f"{rows:,}" if isinstance(rows, int) else None}

    if op == "sum":
        s = f"Total {metric}{fp} is {value_txt}{rows_txt}"
    elif op in ("average", "mean"):
        s = f"Average {metric}{fp} is {value_txt}{rows_txt}"
    elif op == "max":
        s = f"The highest {metric}{fp} is {value_txt}"
    elif op == "min":
        s = f"The lowest {metric}{fp} is {value_txt}"
    elif op == "count_distinct":
        if spec.derived_metric is not None and spec.derived_metric.kind == "count_distinct":
            s = f"There are {value_txt} unique {metric}{fp}"
        else:
            s = f"There are {value_txt} unique {metric} values{fp}"
    elif op == "count":
        if spec.column:
            s = f"{_cap(metric)} has {value_txt} non-empty values{fp}"
        else:
            s = f"There {'is' if result_value == 1 else 'are'} {_count(result_value, 'record')}{fp}"
    else:
        return "", facts
    s = _cap(s)
    if note:
        s += f", {note}"
    return s + ".", facts


def _group_sentences(spec: QuerySpec, result: QueryResult, metric: str, monetary: bool,
                     note: Optional[str], filters_phrase: str) -> Tuple[List[str], Dict[str, Any]]:
    meta = result.metadata or {}
    records = result.result if isinstance(result.result, list) else []
    group_cols = list(meta.get("group_by") or spec.group_by or [])
    val_col = meta.get("value_column")
    if not records or not group_cols or not val_col:
        return [], {}

    op = (spec.operation or "sum").lower()
    money = monetary and op not in ("count", "count_distinct")
    rows = [(" / ".join(_label(r.get(g)) for g in group_cols), r.get(val_col)) for r in records]
    rows = [(g, v) for g, v in rows if isinstance(v, (int, float))]
    if not rows:
        return [], {}

    fp = f" {filters_phrase}" if filters_phrase else ""
    fmt = lambda v: format_value(v, money)
    total = meta.get("total")
    overall = meta.get("overall_value")
    groups_total = meta.get("groups_total") or len(rows)
    limited = bool(spec.limit) and groups_total > len(rows)
    dim = humanize(group_cols[-1]) if len(group_cols) == 1 else " / ".join(humanize(g) for g in group_cols)
    ordered = sorted(rows, key=lambda gv: gv[1], reverse=True)
    top, bottom = ordered[0], ordered[-1]
    sentences: List[str] = []
    facts: Dict[str, Any] = {
        "groups": [{"group": g, "value": fmt(v)} for g, v in ordered[:12]],
        "group_count": groups_total,
    }

    if op in ("sum", "count") and isinstance(total, (int, float)):
        noun = f"total {metric}" if op == "sum" else "records"
        head = (f"Total {metric}{fp} is {fmt(total)}" if op == "sum"
                else f"There are {format_value(total)} records{fp} across {groups_total} {dim} groups")
        if note:
            head += f", {note}"
        sentences.append(head + ".")
        facts["total"] = fmt(total) if op == "sum" else format_value(total)

        shares_ok = total > 0 and all(v >= 0 for _, v in rows)
        share = (lambda v: format_percent(v / total * 100)) if shares_ok else None
        if limited:
            listed = _join([f"{g} ({fmt(v)})" for g, v in ordered[:3]])
            lead = f"The top {len(rows)} of {groups_total} {dim} groups are led by {listed}"
            if shares_ok:
                subtotal = sum(v for _, v in rows)
                lead += f"; together they account for {share(subtotal)} of the total"
                facts["top_share"] = share(subtotal)
            sentences.append(lead + ".")
        elif len(rows) == 1:
            sentences.append(f"All of it comes from {top[0]}.")
        elif len(rows) == 2:
            sentences.append(f"{top[0]} contributes {fmt(top[1])}, while {bottom[0]} contributes {fmt(bottom[1])}.")
            if shares_ok:
                sentences.append(f"{top[0]} accounts for about {share(top[1])} of {noun}.")
        else:
            follow = _join([f"{g} ({fmt(v)})" for g, v in ordered[1:3]])
            lead = f"{top[0]} leads with {fmt(top[1])}"
            if shares_ok:
                lead += f" ({share(top[1])} of the total)"
            sentences.append(f"{lead}, followed by {follow}.")
            if len(rows) > 3:
                sentences.append(f"The lowest is {bottom[0]} at {fmt(bottom[1])}, across {len(rows)} {dim} groups.")
        if shares_ok:
            facts["shares"] = {g: share(v) for g, v in ordered[:12]}
        return sentences, facts

    agg_word = {"average": "average", "mean": "average", "min": "minimum", "max": "maximum",
                "count_distinct": "unique"}.get(op, op)
    if op == "count_distinct":
        head = f"{top[0]} has the most unique {metric} ({fmt(top[1])})"
        if len(rows) > 1:
            head += f", and {bottom[0]} has the fewest ({fmt(bottom[1])})"
        sentences.append(head + f", across {groups_total} {dim} groups{fp}.")
        if isinstance(overall, (int, float)):
            sentences.append(f"Overall there are {format_value(overall)} unique {metric}.")
            facts["overall"] = format_value(overall)
        return sentences, facts

    if isinstance(overall, (int, float)) and op in ("average", "mean"):
        head = f"Overall {agg_word} {metric}{fp} is {fmt(overall)}"
        if note:
            head += f", {note}"
        sentences.append(head + ".")
        facts["overall"] = fmt(overall)
    if len(rows) == 1:
        sentences.append(f"{_cap(agg_word)} {metric} for {top[0]} is {fmt(top[1])}.")
    else:
        sentences.append(f"{_cap(agg_word)} {metric} is highest for {top[0]} ({fmt(top[1])}) "
                         f"and lowest for {bottom[0]} ({fmt(bottom[1])}), across {len(rows)} {dim} groups.")
    return sentences, facts


def build_facts_and_draft(question: str, spec: QuerySpec, result: QueryResult) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Returns (facts, draft). (None, None) when the operation keeps its executor-generated text."""
    op = (spec.operation or "").lower()
    if op not in STANDARD_OPS or not result.success:
        return None, None

    metric, monetary, note = _metric_info(spec, result)
    filters_phrase = describe_filters(result.filters_applied or spec.filters or [])
    rows = result.rows_after_filter
    facts: Dict[str, Any] = {
        "question": question,
        "metric": metric,
        "aggregation": op,
        "filters": filters_phrase or "none",
        "rows_analyzed": f"{rows:,}" if isinstance(rows, int) else None,
    }
    if spec.derived_metric is not None:
        facts["derived_metric"] = {"name": metric, "formula": spec.derived_metric.formula}
    if note:
        facts["note"] = note

    if op == "distinct":
        values = result.list.get("values", []) if result.list else []
        shown = [_label(v) for v in values[:5]]
        more = len(values) - len(shown)
        fp = f" {filters_phrase}" if filters_phrase else ""
        draft = f"There are {len(values):,} unique {metric} values{fp}: {_join(shown)}"
        draft += f", and {more:,} more." if more > 0 else "."
        facts.update({"count": f"{len(values):,}", "values": shown})
        return facts, draft

    if spec.group_by and (result.metadata or {}).get("group_by"):
        sentences, gfacts = _group_sentences(spec, result, metric, monetary, note, filters_phrase)
        if not sentences:
            return None, None
        facts.update(gfacts)
        return facts, " ".join(sentences)

    if result.scalar is None:
        return None, None
    sentence, sfacts = _scalar_sentence(spec, result.scalar.get("value"), rows, metric, monetary, note, filters_phrase)
    if not sentence:
        return None, None
    facts.update(sfacts)
    return facts, sentence


def build_multi_draft(question: str, specs: List[QuerySpec], result: QueryResult) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    subs = (result.metadata or {}).get("sub_results") or []
    if len(subs) != len(specs):
        return None, None
    sentences, values = [], []
    for spec, sub in zip(specs, subs):
        scalar = sub.get("scalar")
        if not scalar or (spec.operation or "").lower() not in STANDARD_OPS:
            return None, None
        metric, monetary, note = _metric_info(spec, result)
        fp = describe_filters(spec.filters or [])
        s, f = _scalar_sentence(spec, scalar.get("value"), None, metric, monetary, note, fp)
        if not s:
            return None, None
        sentences.append(s)
        values.append(f.get("value"))
    rows = result.rows_before_filter
    facts = {"question": question, "values": values, "rows_analyzed": f"{rows:,}" if isinstance(rows, int) else None}
    return facts, " ".join(sentences)


# ==============================================================================
# No-data message
# ==============================================================================

def describe_no_data(spec: Optional[QuerySpec], result: QueryResult, df=None) -> str:
    meta = result.metadata or {}
    filters = result.filters_applied or meta.get("filters_applied") or []
    empty = meta.get("empty_filter")
    values_phrase = describe_filters([empty] if empty else filters, style="values")
    text = f"I couldn't find any records for {values_phrase} in this dataset." if values_phrase else \
        "I couldn't find any records matching those filters in this dataset."

    if spec is not None:
        metric, _, _ = _metric_info(spec, result)
        if metric != "records":
            text += f" {_cap(metric)} is available, but no rows match {'that filter' if len(filters) <= 1 else 'those filters'}."

    if df is not None and empty is not None and _is_temporal_col(str(empty.get("column", ""))):
        coverage = _temporal_coverage(df, str(empty["column"]))
        if coverage:
            text += f" The data covers {coverage}."
    return text


def _temporal_coverage(df, col: str) -> Optional[str]:
    import pandas as pd
    from .semantics import is_year_series
    if col not in df.columns:
        return None
    s = df[col].dropna()
    if len(s) == 0:
        return None
    if is_year_series(s):
        years = pd.to_numeric(s, errors="coerce").dropna().astype(int)
    else:
        years = pd.to_datetime(s, errors="coerce", format="mixed").dropna().dt.year
    if len(years) == 0:
        return None
    lo, hi = int(years.min()), int(years.max())
    return str(lo) if lo == hi else f"{lo} to {hi}"


# ==============================================================================
# LLM polishing with verification
# ==============================================================================

_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_SPECULATION_RE = re.compile(
    r"\b(because|due to|likely|probably|possibly|suggest\w*|indicat\w*|trend\w*|grow\w*|increas\w*|"
    r"decreas\w*|declin\w*|improv\w*|recommend\w*|should)\b", re.IGNORECASE)


def _numbers(text: str) -> List[float]:
    out = []
    for m in _NUMBER_RE.finditer(text or ""):
        try:
            out.append(round(float(m.group(0).replace(",", "")), 2))
        except ValueError:
            pass
    return out


def verify_answer(answer: str, facts: Dict[str, Any], draft: str) -> bool:
    """Accept only answers whose every number appears in the facts/draft and that add no speculation."""
    if not answer or len(answer) > 900:
        return False
    allowed_src = json.dumps(facts, ensure_ascii=False) + " " + draft
    allowed = set(_numbers(allowed_src))
    stated = _numbers(answer)
    if any(n not in allowed for n in stated):
        return False
    draft_numbers = _numbers(draft)
    if draft_numbers and draft_numbers[0] not in stated:
        return False  # must still lead with / contain the headline figure
    for m in _SPECULATION_RE.finditer(answer):
        if m.group(0).lower() not in draft.lower():
            return False
    if len(re.findall(r"[.!?](?:\s|$)", answer)) > 5:
        return False
    return True


def _llm_enabled() -> bool:
    return os.environ.get("QUERYLENS_LLM_SUMMARY", "1").strip().lower() not in ("0", "false", "no", "off")


def polish_with_llm(question: str, facts: Dict[str, Any], draft: str, client=None) -> Optional[str]:
    from llm import OllamaClient, SUMMARY_SYSTEM_PROMPT, build_summary_prompt
    client = client or OllamaClient(timeout=float(os.environ.get("QUERYLENS_SUMMARY_TIMEOUT", "25")))
    if not client.is_available():
        return None
    try:
        data = client.generate_json(SUMMARY_SYSTEM_PROMPT, build_summary_prompt(question, facts, draft), think=False)
    except Exception as e:
        logger.warning(f"Answer summarization failed ({e}); using deterministic summary.")
        return None
    answer = str((data or {}).get("answer") or "").strip()
    if verify_answer(answer, facts, draft):
        return answer
    logger.info("Rejected LLM summary that failed fact verification; using deterministic summary.")
    return None


def generate_answer(question: str, specs: List[QuerySpec], result: QueryResult,
                    use_llm: Optional[bool] = None, client=None) -> Tuple[Optional[str], str]:
    """
    Returns (answer, source) where source is "llm", "template", or "executor".
    answer is None when the executor's own text should be kept (e.g. grade distributions).
    """
    if not specs or not result.success:
        return None, "executor"
    if len(specs) > 1:
        facts, draft = build_multi_draft(question, specs, result)
    else:
        facts, draft = build_facts_and_draft(question, specs[0], result)
    if not draft:
        return None, "executor"

    if use_llm is None:
        use_llm = _llm_enabled()
    if use_llm:
        polished = polish_with_llm(question, facts, draft, client=client)
        if polished:
            return polished, "llm"
    return draft, "template"
