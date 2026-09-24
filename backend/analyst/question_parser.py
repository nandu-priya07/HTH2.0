
import re

from .query_planner import create_query_plan


def contains_phrase(text, phrase):
    pattern = r"\b" + re.escape(phrase) + r"\b"
    return re.search(pattern, text) is not None


def detect_operation(text):

    if (
        contains_phrase(text, "unique")
        or contains_phrase(text, "distinct")
        or contains_phrase(text, "different")
    ):
        return "count_distinct"

    if (
        contains_phrase(text, "average")
        or contains_phrase(text, "avg")
        or contains_phrase(text, "mean")
    ):
        return "average"

    if (
        contains_phrase(text, "count")
        or contains_phrase(text, "how many")
        or contains_phrase(text, "number of")
    ):
        return "count"

    if (
        contains_phrase(text, "minimum")
        or contains_phrase(text, "min")
        or contains_phrase(text, "lowest")
    ):
        return "min"

    if (
        contains_phrase(text, "maximum")
        or contains_phrase(text, "max")
        or contains_phrase(text, "highest")
    ):
        return "max"

    if (
        contains_phrase(text, "total")
        or contains_phrase(text, "sum")
        or contains_phrase(text, "revenue")
        or contains_phrase(text, "sales")
    ):
        return "sum"

    return None


def detect_metric(text):

    metric_patterns = [
        (
            "revenue",
            [
                "revenue",
                "sales",
                "total sales",
                "sales amount"
            ]
        ),
        (
            "profit",
            [
                "profit",
                "earnings"
            ]
        ),
        (
            "quantity",
            [
                "quantity",
                "units sold",
                "number of units"
            ]
        ),
        (
            "unit_price",
            [
                "unit price",
                "price per unit",
                "price"
            ]
        ),
        (
            "discount",
            [
                "discount"
            ]
        )
    ]

    for metric, keywords in metric_patterns:

        if any(
            contains_phrase(text, keyword)
            for keyword in keywords
        ):
            return metric

    return None


def detect_group_by(text):

    group_patterns = [
        (
            "product",
            ["product", "products", "item", "items"]
        ),
        (
            "category",
            ["category", "categories"]
        ),
        (
            "customer",
            ["customer", "customers"]
        ),
        (
            "country",
            ["country", "countries"]
        ),
        (
            "state",
            ["state", "states", "province"]
        ),
        (
            "city",
            ["city", "cities"]
        ),
        (
            "region",
            ["region", "regions"]
        ),
        (
            "date",
            ["date", "dates"]
        )
    ]

    for group, keywords in group_patterns:

        if any(
            contains_phrase(text, keyword)
            for keyword in keywords
        ):
            return group

    return None


def clean_filter_value(value):

    value = value.strip()

    value = re.sub(
        r"[?.!,;]+$",
        "",
        value
    ).strip()

    value = re.sub(
        r"^(the|a|an)\s+",
        "",
        value,
        flags=re.IGNORECASE
    ).strip()

    value = re.sub(
        r"\s+(region|area)$",
        "",
        value,
        flags=re.IGNORECASE
    ).strip()

    return value


def detect_filter(question, group_by=None):

    text = question.strip()

    # Example:
    # where category = Technology
    where_match = re.search(
        r"\bwhere\s+(.+?)(?:\?|$)",
        text,
        flags=re.IGNORECASE
    )

    if where_match:

        condition = where_match.group(1).strip()

        match = re.match(
            r"(.+?)\s*(=|!=|>=|<=|>|<|is|equals?)\s*(.+)",
            condition,
            flags=re.IGNORECASE
        )

        if match:

            column = match.group(1).strip()

            operator = match.group(2).lower().strip()

            value = clean_filter_value(
                match.group(3)
            )

            if operator in {
                "is",
                "equals"
            }:
                operator = "="

            return {
                "column": column,
                "operator": operator,
                "value": value
            }

    # Example:
    # revenue in Technology
    in_match = re.search(
        r"\bin\s+(?:the\s+)?([A-Za-z][A-Za-z\s/&-]*?)(?:\?|$)",
        text,
        flags=re.IGNORECASE
    )

    if in_match:

        value = clean_filter_value(
            in_match.group(1)
        )

        ignored_values = {
            "products",
            "product",
            "customers",
            "customer",
            "categories",
            "category",
            "countries",
            "country",
            "regions",
            "region"
        }

        if value.lower() not in ignored_values:

            value_lower = value.lower()

            if value_lower in {
                "technology",
                "office supplies",
                "furniture"
            }:
                column = "category"

            elif value_lower in {
                "west",
                "east",
                "central",
                "south"
            }:
                column = "region"

            else:
                column = group_by

            if column:

                return {
                    "column": column,
                    "operator": "=",
                    "value": value
                }

    return None


def parse_question(question):

    text = question.lower().strip()

    operation = detect_operation(text)

    metric = detect_metric(text)

    group_by = detect_group_by(text)

    # Unique customer question
    if (
        operation == "count_distinct"
        and (
            contains_phrase(text, "customer")
            or contains_phrase(text, "customers")
        )
    ):
        metric = "customer_id"
        group_by = None

    # Top N
    limit = None
    sort = None

    top_match = re.search(
        r"\btop\s+(\d+)\b",
        text
    )

    if top_match:

        limit = int(
            top_match.group(1)
        )

        sort = "desc"

    # Bottom N
    bottom_match = re.search(
        r"\b(?:bottom|lowest)\s+(\d+)\b",
        text
    )

    if bottom_match:

        limit = int(
            bottom_match.group(1)
        )

        sort = "asc"

    filters = []

    detected_filter = detect_filter(
        question,
        group_by=group_by
    )

    if detected_filter:
        filters.append(
            detected_filter
        )

    return create_query_plan(
        operation=operation,
        metric=metric,
        group_by=group_by,
        filters=filters,
        sort=sort,
        limit=limit
    )
