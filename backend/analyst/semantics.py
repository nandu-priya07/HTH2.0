"""
Schema-aware metric semantics for QueryLens.

Decides deterministically whether a requested business metric is:

    DIRECT         - a dataset column represents it
    DERIVED        - it can be computed from a controlled derivation rule
    AMBIGUOUS      - several columns could represent it (ask the user)
    NOT_AVAILABLE  - it is absent and no valid rule applies

The LLM may suggest a column, but this layer is the final authority: a metric is
never silently substituted by an unrelated column (e.g. revenue -> cost), and a
formula is only used when every required column actually exists.

It also resolves year / date references so a year-specific question is either
filtered on a real temporal field or reported as not answerable.
"""

import re
import calendar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .models import LLMResponse, QuerySpec, FilterSpec, DerivedMetricSpec


# ==============================================================================
# Name helpers
# ==============================================================================

def _singular(token: str) -> str:
    if len(token) > 3 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def column_tokens(name: str) -> List[str]:
    """'TotalRevenue' / 'total_revenue' / 'Total Revenue' -> ['total', 'revenue']."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    return [_singular(t) for t in re.split(r"[^A-Za-z0-9]+", s.lower()) if t]


def display_name(name: str) -> str:
    """Human label for a column: 'unit_price' -> 'Unit Price', 'Net Sales' stays."""
    s = str(name)
    if s.islower() or "_" in s:
        return " ".join(w.capitalize() for w in re.split(r"[_\s]+", s) if w)
    return s


def humanize(name: str) -> str:
    """Inline (mid-sentence) label: 'country_region' -> 'country region'."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    s = re.sub(r"[_\-]+", " ", s).strip()
    return s if s.isupper() else s.lower()


def _has_phrase(tokens: Sequence[str], phrase: Sequence[str]) -> bool:
    n = len(phrase)
    return any(list(tokens[i:i + n]) == list(phrase) for i in range(len(tokens) - n + 1))


def _is_numeric_like(series: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(series):
        return False
    if pd.api.types.is_numeric_dtype(series):
        return True
    sample = series.dropna().head(200)
    if len(sample) == 0:
        return False
    return pd.to_numeric(sample, errors="coerce").notna().mean() >= 0.9


# ==============================================================================
# Concept registry
# ==============================================================================

_QUALIFIER_TOKENS = frozenset({
    "unit", "per", "avg", "average", "mean", "rate", "pct", "percent", "percentage",
    "margin", "ratio", "count", "id", "growth", "share", "target", "forecast",
    "budget", "goal", "tax", "rank", "index", "flag", "score",
})


@dataclass(frozen=True)
class Concept:
    name: str
    label: str
    question_pattern: str
    column_terms: Tuple[Tuple[str, ...], ...] = ()
    synonyms: Tuple[str, ...] = ()
    exclude_tokens: frozenset = _QUALIFIER_TOKENS
    kind: str = "measure"  # "measure" (numeric column) | "count" (distinct entities) | "identifier"
    monetary: bool = False
    entity: Optional[str] = None  # for count / identifier concepts


CONCEPTS: Dict[str, Concept] = {c.name: c for c in [
    Concept("unit_cost", "unit cost", r"\bunit\s+costs?\b|\bcosts?\s+per\s+unit\b|\bcost\s+price\b",
            column_terms=(("unit", "cost"), ("cost", "per", "unit"), ("cost", "price")),
            exclude_tokens=frozenset({"id", "count", "total"}), monetary=True),
    Concept("selling_price", "selling price", r"\b(?:selling|sale|sales|unit)\s+prices?\b|\bprices?\b",
            column_terms=(("selling", "price"), ("sale", "price"), ("unit", "price"), ("price",)),
            exclude_tokens=frozenset({"id", "count", "cost", "total"}), monetary=True),
    Concept("customer_count", "customers",
            r"\b(?:how\s+many|number\s+of|count\s+of|count|total|unique|distinct)\s+(?:the\s+)?"
            r"(?:unique\s+|distinct\s+|different\s+)?customers?\b|\bcustomer\s+count\b",
            kind="count", entity="customer"),
    Concept("order_count", "orders",
            r"\b(?:how\s+many|number\s+of|count\s+of|count|total|unique|distinct)\s+(?:the\s+)?"
            r"(?:unique\s+|distinct\s+|different\s+)?orders?\b|\border\s+count\b",
            kind="count", entity="order"),
    Concept("revenue", "revenue", r"\brevenues?\b|\bturnover\b",
            column_terms=(("revenue",), ("turnover",)), synonyms=("sales",), monetary=True),
    Concept("sales", "sales", r"\bsales\b",
            column_terms=(("sale",),), synonyms=("revenue",),
            exclude_tokens=_QUALIFIER_TOKENS | {"rep", "person", "channel", "manager", "team", "agent", "price"},
            monetary=True),
    Concept("profit", "profit", r"\bprofits?\b",
            column_terms=(("profit",), ("net", "income")), monetary=True),
    Concept("cost", "cost", r"\bcosts?\b|\bexpenses?\b|\bcogs\b",
            column_terms=(("cost",), ("expense",), ("cog",)),
            exclude_tokens=_QUALIFIER_TOKENS | {"price"}, monetary=True),
    Concept("quantity", "quantity", r"\bquantit(?:y|ies)\b|\bunits\s+sold\b|\bqty\b",
            column_terms=(("quantity",), ("qty",), ("unit", "sold")),
            exclude_tokens=frozenset({"id", "price", "cost"})),
    # Identifier concepts: only used as derivation components.
    Concept("customer_id", "customer ID", r"(?!)", kind="identifier", entity="customer"),
    Concept("order_id", "order ID", r"(?!)", kind="identifier", entity="order"),
]}

# Order matters: more specific phrases are detected (and masked) first.
_DETECTION_ORDER = ["unit_cost", "selling_price", "customer_count", "order_count",
                    "revenue", "sales", "profit", "cost", "quantity"]

MONETARY_TOKENS = frozenset({"revenue", "sale", "profit", "cost", "price", "amount", "income",
                             "spend", "expense", "turnover", "cog", "salary", "fee", "payment"})


@dataclass(frozen=True)
class DerivationRule:
    target: str
    operator: str  # "+", "-", "*", "count_distinct"
    components: Tuple[str, ...]


# The ONLY formulas QueryLens will use to derive a metric that is not a column.
DERIVATION_RULES: List[DerivationRule] = [
    DerivationRule("revenue", "+", ("cost", "profit")),
    DerivationRule("revenue", "*", ("selling_price", "quantity")),
    DerivationRule("sales", "*", ("selling_price", "quantity")),
    DerivationRule("sales", "+", ("cost", "profit")),
    DerivationRule("profit", "-", ("revenue", "cost")),
    DerivationRule("cost", "*", ("unit_cost", "quantity")),
    DerivationRule("cost", "-", ("revenue", "profit")),
    DerivationRule("customer_count", "count_distinct", ("customer_id",)),
    DerivationRule("order_count", "count_distinct", ("order_id",)),
]

_OP_SYMBOL = {"+": "+", "-": "-", "*": "×"}


def _rule_text(rule: DerivationRule) -> str:
    if rule.operator == "count_distinct":
        return f"a {CONCEPTS[rule.components[0]].label} field"
    labels = [display_name(CONCEPTS[c].label) for c in rule.components]
    return f" {_OP_SYMBOL[rule.operator]} ".join(labels)


# ==============================================================================
# Column classification & resolution
# ==============================================================================

def _column_matches(concept: Concept, col: str) -> bool:
    tokens = column_tokens(col)
    if not tokens:
        return False
    matched_phrase = None
    for phrase in concept.column_terms:
        if _has_phrase(tokens, phrase):
            matched_phrase = phrase
            break
    if not matched_phrase:
        return False
    remaining = set(tokens) - set(matched_phrase)
    return not (remaining & concept.exclude_tokens)


def _entity_columns(entity: str, df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """(id-like columns, name-like columns) for an entity such as 'customer'."""
    id_cols, name_cols = [], []
    for col in df.columns:
        tokens = column_tokens(col)
        if entity not in tokens:
            continue
        rest = set(tokens) - {entity}
        if rest & {"id", "key", "code", "no", "number", "num"}:
            id_cols.append(col)
        elif not rest or rest <= {"name"}:
            name_cols.append(col)
    return id_cols, name_cols


def direct_columns(concept_name: str, df: pd.DataFrame) -> List[str]:
    concept = CONCEPTS[concept_name]
    if concept.kind == "identifier":
        ids, names = _entity_columns(concept.entity, df)
        return ids or names
    if concept.kind != "measure":
        return []
    return [c for c in df.columns if _column_matches(concept, c) and _is_numeric_like(df[c])]


def column_concepts(col: Optional[str]) -> List[str]:
    """Measure concepts a column name represents (e.g. 'Total Revenue' -> ['revenue'])."""
    if not col:
        return []
    return [name for name, c in CONCEPTS.items() if c.kind == "measure" and _column_matches(c, col)]


def _exact_names(concept: Concept) -> set:
    base = concept.label
    return {base, f"total {base}", _singular(base), f"total {_singular(base)}"}


@dataclass
class MetricResolution:
    concept: str
    status: str  # "direct" | "derived" | "ambiguous" | "not_available"
    column: Optional[str] = None
    candidates: List[str] = field(default_factory=list)
    derived: Optional[DerivedMetricSpec] = None
    via_synonym: Optional[str] = None
    rule_options: List[str] = field(default_factory=list)


def _pick_single(concept: Concept, cols: List[str]) -> Optional[str]:
    if len(cols) == 1:
        return cols[0]
    exact = [c for c in cols if " ".join(column_tokens(c)) in {" ".join(column_tokens(n)) for n in _exact_names(concept)}]
    return exact[0] if len(exact) == 1 else None


def _resolve_component(concept_name: str, df: pd.DataFrame) -> Optional[str]:
    """Single unambiguous direct column for a derivation component, else None."""
    concept = CONCEPTS[concept_name]
    primary = direct_columns(concept_name, df)
    if primary:
        return _pick_single(concept, primary)
    syn = [c for s in concept.synonyms for c in direct_columns(s, df)]
    return syn[0] if len(syn) == 1 else None


def resolve_concept(concept_name: str, df: pd.DataFrame) -> MetricResolution:
    concept = CONCEPTS[concept_name]

    if concept.kind == "measure":
        primary = direct_columns(concept_name, df)
        if primary:
            chosen = _pick_single(concept, primary)
            if chosen:
                return MetricResolution(concept_name, "direct", column=chosen, candidates=primary)
            synonyms = [c for s in concept.synonyms for c in direct_columns(s, df) if c not in primary]
            return MetricResolution(concept_name, "ambiguous", candidates=primary + synonyms)

        synonyms = []
        for s in concept.synonyms:
            synonyms += [c for c in direct_columns(s, df) if c not in synonyms]
        if len(synonyms) == 1:
            return MetricResolution(concept_name, "direct", column=synonyms[0], candidates=synonyms,
                                    via_synonym=synonyms[0])
        if len(synonyms) > 1:
            return MetricResolution(concept_name, "ambiguous", candidates=synonyms)

    rules = [r for r in DERIVATION_RULES if r.target == concept_name]
    for rule in rules:
        cols = [_resolve_component(c, df) for c in rule.components]
        if not all(cols):
            continue
        if rule.operator == "count_distinct":
            src = cols[0]
            derived = DerivedMetricSpec(
                name=concept_name, formula=f"COUNT DISTINCT {display_name(src)}",
                kind="count_distinct", source_column=src, required_columns=[src])
        else:
            if not all(_is_numeric_like(df[c]) for c in cols):
                continue
            derived = DerivedMetricSpec(
                name=concept_name,
                formula=f" {_OP_SYMBOL[rule.operator]} ".join(display_name(c) for c in cols),
                kind="expression", operator=rule.operator, operands=list(cols), required_columns=list(cols))
        return MetricResolution(concept_name, "derived", derived=derived)

    return MetricResolution(concept_name, "not_available", rule_options=[_rule_text(r) for r in rules])


def describe_metric_availability(df: Optional[pd.DataFrame]) -> List[str]:
    """Compact lines for the LLM prompt describing which business metrics exist or can be derived."""
    if df is None:
        return []
    lines = []
    for name in _DETECTION_ORDER:
        res = resolve_concept(name, df)
        label = CONCEPTS[name].label
        if res.status == "direct":
            lines.append(f"- {label}: column '{res.column}'")
        elif res.status == "derived":
            lines.append(f"- {label}: NOT a column; derivable as {res.derived.formula}")
        elif res.status == "ambiguous":
            lines.append(f"- {label}: ambiguous between {', '.join(res.candidates)}")
    return lines


# ==============================================================================
# Question analysis
# ==============================================================================

def _mask_literal_columns(q_lower: str, columns: Sequence[str]) -> str:
    """Blank out spans that literally name a dataset column so they are trusted as-is."""
    phrases = set()
    for col in columns:
        raw = str(col).lower().strip()
        spaced = re.sub(r"[_\-]+", " ", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(col))).lower().strip()
        for p in (raw, spaced):
            if len(p) >= 3:
                phrases.add(p)
    for p in sorted(phrases, key=len, reverse=True):
        q_lower = re.sub(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", lambda m: " " * len(m.group(0)), q_lower)
    return q_lower


def detect_concepts(question: str, columns: Sequence[str] = ()) -> List[str]:
    """Registry concepts mentioned in the question (ignoring literal column names), in order of appearance."""
    q = _mask_literal_columns(question.lower(), columns)
    found: List[Tuple[int, str]] = []
    for name in _DETECTION_ORDER:
        pattern = CONCEPTS[name].question_pattern
        for m in re.finditer(pattern, q):
            found.append((m.start(), name))
            q = q[:m.start()] + " " * (m.end() - m.start()) + q[m.end():]
            break
    return [name for _, name in sorted(found)]


def mentions_column_literally(question: str, col: Optional[str]) -> bool:
    if not col:
        return False
    q = question.lower()
    return _mask_literal_columns(q, [col]) != q


def match_concept_term(term: Optional[str]) -> Optional[str]:
    if not term:
        return None
    t = str(term).lower().replace("_", " ").strip()
    for name in _DETECTION_ORDER:
        if re.search(CONCEPTS[name].question_pattern, t):
            return name
        if t in (name.replace("_", " "), CONCEPTS[name].label, _singular(CONCEPTS[name].label)):
            return name
    concepts = column_concepts(t)
    return concepts[0] if len(concepts) == 1 else None


def is_monetary(name: Optional[str]) -> bool:
    if not name:
        return False
    if name in CONCEPTS:
        return CONCEPTS[name].monetary
    return bool(set(column_tokens(name)) & MONETARY_TOKENS)


# ==============================================================================
# Temporal handling
# ==============================================================================

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
_YEAR_RE = re.compile(
    r"(?<![\d$.,])(?<!top )(?<!first )(?<!last )(?<!bottom )\b(19\d{2}|20\d{2})\b"
    r"(?!\d|[.,]\d|\s*(?:%|rows|records|units|items))"
)


def is_year_series(series: pd.Series) -> bool:
    """Integer-valued column whose values all look like calendar years."""
    if pd.api.types.is_bool_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
        return False
    s = series.dropna()
    if len(s) == 0:
        return False
    nums = pd.to_numeric(s.head(500), errors="coerce")
    if nums.isna().any():
        return False
    return bool(((nums % 1 == 0) & (nums >= 1800) & (nums <= 2200)).all())


def _is_date_series(col: str, series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if pd.api.types.is_numeric_dtype(series):
        return False
    tokens = set(column_tokens(col))
    if not tokens & {"date", "time", "timestamp", "datetime", "day", "dt", "period", "month"}:
        return False
    sample = series.dropna().astype(str).head(100)
    if len(sample) == 0:
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return parsed.notna().mean() >= 0.8


def temporal_columns(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """(year columns, date columns) in the dataset."""
    year_cols, date_cols = [], []
    for col in df.columns:
        tokens = set(column_tokens(col))
        if tokens & {"year", "yr", "fy"} and is_year_series(df[col]):
            year_cols.append(col)
        elif _is_date_series(col, df[col]):
            date_cols.append(col)
    date_cols.sort(key=lambda c: (0 if "order" in column_tokens(c) else 1))
    return year_cols, date_cols


def extract_years(text: str) -> List[int]:
    years = []
    for m in _YEAR_RE.finditer(text.lower()):
        y = int(m.group(1))
        if y not in years:
            years.append(y)
    return years


def _extract_period(question: str, year: int) -> Optional[Tuple[str, str, str]]:
    """Month or quarter attached to a year -> (start, end, label)."""
    q = question.lower()
    qm = re.search(rf"\bq([1-4])\s*(?:of\s+)?{year}\b|\b{year}\s*q([1-4])\b", q)
    if qm:
        quarter = int(qm.group(1) or qm.group(2))
        m1 = 3 * (quarter - 1) + 1
        m3 = m1 + 2
        return f"{year}-{m1:02d}-01", f"{year}-{m3:02d}-{calendar.monthrange(year, m3)[1]:02d}", f"Q{quarter} {year}"
    for name, num in sorted(MONTHS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{name}\.?\s*(?:of\s+)?{year}\b", q):
            return (f"{year}-{num:02d}-01", f"{year}-{num:02d}-{calendar.monthrange(year, num)[1]:02d}",
                    f"{calendar.month_name[num]} {year}")
    return None


def _as_year(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and float(value).is_integer() and 1800 <= value <= 2200:
        return int(value)
    if isinstance(value, str):
        m = re.match(r"^\s*(\d{4})(?:-\d{2}(?:-\d{2})?)?", value)
        if m and 1800 <= int(m.group(1)) <= 2200:
            return int(m.group(1))
    return None


def _looks_temporal_name(col: str) -> bool:
    return bool(set(column_tokens(col)) & {"year", "yr", "fy", "date", "time", "month", "day", "period", "timestamp"})


def _filter_value_mentions_year(value: Any) -> bool:
    vals = value if isinstance(value, (list, tuple)) else [value]
    return any(_as_year(v) is not None for v in vals)


def _year_filter(col: str, is_year_col: bool, years: List[int]) -> FilterSpec:
    if is_year_col:
        if len(years) == 1:
            return FilterSpec(column=col, operator="equals", value=years[0])
        return FilterSpec(column=col, operator="between", value=[min(years), max(years)])
    return FilterSpec(column=col, operator="between", value=[f"{min(years)}-01-01", f"{max(years)}-12-31"])


def normalize_temporal_filters(spec: QuerySpec, question: str, df: pd.DataFrame) -> Optional[LLMResponse]:
    """
    Makes year / date filtering explicit and correct:
      - LLM filters on a non-existent temporal column are re-pointed at the real one
      - Year-column filters use integer years; date-column filters use date ranges
      - A year named in the question but missing from the plan is added
      - If the dataset has no temporal field, returns a not_available response
    """
    issue = _normalize_temporal(spec, question, df)
    return _no_temporal_response(spec, issue[0], df, has_year_only=issue[1]) if issue else None


def _normalize_temporal(spec: QuerySpec, question: str, df: pd.DataFrame) -> Optional[Tuple[str, bool]]:
    """Mutates spec.filters; returns (period_label, has_year_only) when the period can't be isolated."""
    year_cols, date_cols = temporal_columns(df)
    temporal = year_cols + date_cols
    years = extract_years(question)

    new_filters: List[FilterSpec] = []
    dropped_temporal = False
    for f in spec.filters:
        col = f.column
        if col not in df.columns:
            ci = {c.lower(): c for c in df.columns}
            col = ci.get(str(col).lower(), col)
        if col not in df.columns and (_looks_temporal_name(str(f.column)) or _filter_value_mentions_year(f.value)):
            if not temporal:
                dropped_temporal = True
                continue
            col = temporal[0]
        f = FilterSpec(column=col, operator=f.operator, value=f.value)

        if col in year_cols:
            op = str(f.operator).lower()
            vals = f.value if isinstance(f.value, (list, tuple)) else [f.value]
            ys = [_as_year(v) for v in vals]
            if all(y is not None for y in ys):
                if op in ("between", "range") and len(ys) == 2:
                    f = FilterSpec(column=col, operator="equals", value=ys[0]) if ys[0] == ys[1] else \
                        FilterSpec(column=col, operator="between", value=[min(ys), max(ys)])
                elif op in ("in", "is_in"):
                    f = FilterSpec(column=col, operator="in", value=ys)
                else:
                    f = FilterSpec(column=col, operator=f.operator, value=ys[0])
        elif col in date_cols:
            op = str(f.operator).lower()
            if op in ("=", "==", "equals", "eq", "is") and _as_year(f.value) is not None \
                    and re.fullmatch(r"\s*\d{4}\s*", str(f.value)):
                y = _as_year(f.value)
                period = _extract_period(question, y)
                start, end = (period[0], period[1]) if period else (f"{y}-01-01", f"{y}-12-31")
                f = FilterSpec(column=col, operator="between", value=[start, end])
        new_filters.append(f)
    spec.filters = new_filters

    has_temporal_filter = any(f.column in temporal for f in spec.filters)
    has_temporal_group = any(g in temporal for g in (spec.group_by or []))

    if (years or dropped_temporal) and not temporal and not has_temporal_group:
        return _years_label(years) or "a specific period", False

    if years and not has_temporal_filter and not has_temporal_group:
        if year_cols:
            period = _extract_period(question, years[0]) if len(years) == 1 else None
            if period and date_cols:
                spec.filters.append(FilterSpec(column=date_cols[0], operator="between", value=[period[0], period[1]]))
            elif period:
                return period[2], True
            else:
                spec.filters.append(_year_filter(year_cols[0], True, years))
        else:
            period = _extract_period(question, years[0]) if len(years) == 1 else None
            if period:
                spec.filters.append(FilterSpec(column=date_cols[0], operator="between", value=[period[0], period[1]]))
            else:
                spec.filters.append(_year_filter(date_cols[0], False, years))
    return None


def _years_label(years: List[int]) -> str:
    if not years:
        return ""
    if len(years) == 1:
        return str(years[0])
    return f"{min(years)}–{max(years)}"


def _metric_phrase(spec: QuerySpec) -> str:
    op = (spec.operation or "sum").lower()
    metric = spec.requested_metric or (spec.derived_metric.name if spec.derived_metric else None) or spec.column
    metric = humanize(CONCEPTS[metric].label) if metric in CONCEPTS else humanize(metric or "this metric")
    prefix = {"sum": "total ", "average": "average ", "mean": "average ", "min": "minimum ", "max": "maximum "}.get(op, "")
    return f"{prefix}{metric}"


def _no_temporal_response(spec: QuerySpec, label: str, df: pd.DataFrame, has_year_only: bool = False) -> LLMResponse:
    metric = _metric_phrase(spec)
    if has_year_only:
        reason = f"this dataset only has a year field, not dates"
    else:
        reason = "this dataset doesn't contain a date or year field"
    answer = f"I can calculate {metric}, but I can't isolate {label} because {reason}."
    return LLMResponse(
        type="not_available",
        answer=answer,
        details={
            "status": "not_available",
            "requested_metric": spec.requested_metric or spec.column,
            "requested_period": label,
            "reason": f"No temporal field to filter by {label}.",
            "available_fields": [str(c) for c in df.columns],
        },
    )


# ==============================================================================
# Metric resolution for a query plan
# ==============================================================================

MEASURE_OPS = {"sum", "average", "mean", "min", "max"}
COUNT_OPS = {"count", "count_distinct"}


def _join_names(names: List[str]) -> str:
    names = [display_name(n) for n in names]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + (", and " if len(names) > 2 else " and ") + names[-1]


def _fields_phrase(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    if len(cols) <= 6:
        return f"The dataset contains {_join_names(cols)}"
    return f"The available fields include {_join_names(cols[:6])}, and {len(cols) - 6} more"


def _filter_phrase_for_message(spec: QuerySpec) -> str:
    # Local import keeps semantics free of summarizer at import time.
    from .summarizer import describe_filters
    phrase = describe_filters(spec.filters or [], style="values")
    return f" for {phrase}" if phrase else ""


def _not_available_response(concept_name: str, res: MetricResolution, spec: QuerySpec, df: pd.DataFrame) -> LLMResponse:
    label = CONCEPTS[concept_name].label
    title = label[0].upper() + label[1:]
    fp = _filter_phrase_for_message(spec)
    answer = (f"{title} isn't available{fp} in this dataset. {_fields_phrase(df)}, "
              f"but there isn't enough information to derive {title} reliably.")
    suggestion = None
    if res.rule_options:
        suggestion = f"Add a {title} field, or provide " + " or ".join(res.rule_options) + "."
        answer += f" {suggestion}"
    return LLMResponse(
        type="not_available",
        answer=answer,
        details={
            "status": "not_available",
            "requested_metric": concept_name,
            "reason": f"No {label} column or valid derivation rule exists.",
            "available_fields": [str(c) for c in df.columns],
            "suggestion": suggestion,
        },
    )


def _ambiguous_response(concept_name: str, res: MetricResolution, question: str) -> LLMResponse:
    label = CONCEPTS[concept_name].label
    options = []
    pattern = CONCEPTS[concept_name].question_pattern
    for col in res.candidates:
        rewritten, n = re.subn(pattern, display_name(col), question, count=1, flags=re.IGNORECASE)
        options.append(rewritten if n else f"{question} (using {col})")
    answer = f"I found {_join_names(res.candidates)}. Which one should I use for '{label}'?"
    return LLMResponse(type="clarification", answer=answer,
                       details={"options": options, "candidates": res.candidates, "requested_metric": concept_name})


def _requested_concept(spec: QuerySpec, question: str, df: pd.DataFrame) -> Optional[str]:
    op = (spec.operation or "").lower()
    wanted_kind = "measure" if op in MEASURE_OPS else "count"

    if spec.requested_metric:
        literal = next((c for c in df.columns if str(c).lower() == str(spec.requested_metric).lower()), None)
        if literal is not None:
            return None
        concept = match_concept_term(spec.requested_metric)
        if concept and CONCEPTS[concept].kind == wanted_kind:
            return concept

    if spec.column and mentions_column_literally(question, spec.column):
        return None

    if spec.column and str(spec.column).lower() not in {str(c).lower() for c in df.columns}:
        # The planner named a column that doesn't exist (e.g. "revenue"); treat it as the requested term.
        concept = match_concept_term(spec.column)
        if concept and CONCEPTS[concept].kind == wanted_kind:
            return concept

    mentioned = [c for c in detect_concepts(question, list(df.columns)) if CONCEPTS[c].kind == wanted_kind]
    if not mentioned:
        return None
    if wanted_kind == "measure" and spec.column and spec.column in df.columns:
        shared = [c for c in mentioned if c in column_concepts(spec.column)]
        if shared:
            # The planner's column fits the concept, but if other columns fit equally well
            # the choice must go back to the user instead of being made silently.
            res = resolve_concept(shared[0], df)
            return shared[0] if res.status == "ambiguous" else None
        # Accept an LLM column that is a valid (single) resolution of a mentioned concept.
        for c in mentioned:
            if resolve_concept(c, df).column == spec.column:
                return None
    if wanted_kind == "count" and op == "count_distinct" and spec.column in df.columns:
        entity = CONCEPTS[mentioned[0]].entity
        if entity in column_tokens(spec.column):
            return None
    return mentioned[0]


def resolve_spec_metric(spec: QuerySpec, question: str, df: pd.DataFrame) -> Optional[LLMResponse]:
    """Validates / rewrites the metric of one QuerySpec. Returns a terminal response when not answerable."""
    op = (spec.operation or "").lower()
    if op not in MEASURE_OPS | COUNT_OPS:
        return None
    if spec.derived_metric is not None:
        return None

    concept_name = _requested_concept(spec, question, df)
    if not concept_name:
        return None

    res = resolve_concept(concept_name, df)
    spec.requested_metric = concept_name

    if res.status == "direct":
        if op == "count":
            return None
        if spec.column != res.column:
            spec.column = res.column
        spec.metric_mapping = {"requested": concept_name, "column": res.column,
                               "via_synonym": bool(res.via_synonym)} if res.via_synonym else None
        return None

    if res.status == "derived":
        derived = res.derived
        if derived.kind == "count_distinct":
            spec.operation = "count_distinct"
            spec.column = derived.source_column
        else:
            if op == "count":
                return None
            spec.column = None
        spec.derived_metric = derived
        return None

    if res.status == "ambiguous":
        return _ambiguous_response(concept_name, res, question)

    return _not_available_response(concept_name, res, spec, df)


def apply_semantic_layer(resp: LLMResponse, question: str, df: Optional[pd.DataFrame]) -> LLMResponse:
    """Runs temporal normalization and metric resolution over every query in a data_query response."""
    if df is None or resp.type != "data_query":
        return resp
    for spec in resp.all_queries:
        # Temporal filters first so "not available" messages can name the period;
        # a missing metric outranks a missing period, so it is reported first.
        temporal_issue = _normalize_temporal(spec, question, df)
        terminal = resolve_spec_metric(spec, question, df)
        if terminal is not None:
            return terminal
        if temporal_issue:
            return _no_temporal_response(spec, temporal_issue[0], df, has_year_only=temporal_issue[1])
    return resp


def infer_operation(question: str) -> str:
    q = question.lower()
    if re.search(r"\b(average|avg|mean)\b", q):
        return "average"
    if re.search(r"\b(maximum|max|highest|largest|biggest)\b", q):
        return "max"
    if re.search(r"\b(minimum|min|lowest|smallest)\b", q):
        return "min"
    return "sum"


def fallback_spec_for_concept(question: str, df: pd.DataFrame) -> Optional[QuerySpec]:
    """
    Minimal deterministic plan when neither the LLM nor the rule router produced one, but the
    question clearly names a registry metric (so it can be derived or reported as unavailable).
    """
    mentioned = detect_concepts(question, list(df.columns))
    if not mentioned:
        return None
    concept = mentioned[0]
    op = "count_distinct" if CONCEPTS[concept].kind == "count" else infer_operation(question)
    group_by = []
    m = re.search(r"\b(?:by|per|for each|for every|across each)\s+([a-z0-9_ ]+?)(?:\s+(?:in|for|during)\b|[?.!]|$)",
                  question.lower())
    if m:
        col = fuzzy_resolve_column(m.group(1), df)
        if col:
            group_by = [col]
    return QuerySpec(operation=op, column=None, requested_metric=concept, group_by=group_by,
                     filters=[], raw_question=question)


def fuzzy_resolve_column(term: str, df: pd.DataFrame) -> Optional[str]:
    """'country' -> 'country_region' when exactly one column contains the term's tokens."""
    t = str(term).strip().lower()
    t = re.sub(r"^(?:the|each|every)\s+", "", t)
    if not t:
        return None
    ci = {str(c).lower(): c for c in df.columns}
    if t in ci:
        return ci[t]
    t_tokens = column_tokens(t)
    if not t_tokens:
        return None
    exact = [c for c in df.columns if column_tokens(c) == t_tokens]
    if len(exact) == 1:
        return exact[0]
    containing = [c for c in df.columns if all(tok in column_tokens(c) for tok in t_tokens)]
    if len(containing) == 1:
        return containing[0]
    if containing:
        # Prefer the shortest name (e.g. 'region' over 'region_manager').
        containing.sort(key=lambda c: len(column_tokens(c)))
        if len(column_tokens(containing[0])) < len(column_tokens(containing[1])):
            return containing[0]
    return None
