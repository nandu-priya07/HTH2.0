
from .schema_mapper import (
    resolve_column,
    resolve_group_by,
    resolve_metric
)


QUERY_OPERATIONS = {
    "sum",
    "average",
    "count",
    "count_distinct",
    "min",
    "max"
}


def validate_query_plan(
    query_plan,
    df,
    semantic_model,
    semantic_embeddings
):
    errors = []

    operation = query_plan.get("operation")
    metric = query_plan.get("metric")
    group_by = query_plan.get("group_by")
    filters = query_plan.get("filters", [])
    sort = query_plan.get("sort")
    limit = query_plan.get("limit")

    # --------------------------------
    # 1. Validate operation
    # --------------------------------
    if operation not in QUERY_OPERATIONS:
        errors.append(
            f"Unsupported operation: {operation}"
        )

    # --------------------------------
    # 2. Validate metric
    # --------------------------------
    if metric is not None:

        if operation == "count_distinct":
            try:
                resolve_column(
                    metric,
                    df,
                    semantic_model,
                    semantic_embeddings
                )
            except ValueError:
                errors.append(
                    f"Column not found for count_distinct: {metric}"
                )

        elif operation != "count":
            try:
                resolve_metric(
                    metric,
                    df
                )
            except ValueError as e:
                errors.append(str(e))

    # --------------------------------
    # 3. Validate group_by
    # --------------------------------
    if group_by is not None:
        try:
            resolve_group_by(
                group_by,
                df,
                semantic_model,
                semantic_embeddings
            )
        except ValueError as e:
            errors.append(str(e))

    # --------------------------------
    # 4. Validate filters
    # --------------------------------
    allowed_operators = {
        "=",
        "!=",
        ">",
        "<",
        ">=",
        "<="
    }

    for filter_item in filters:

        if not isinstance(filter_item, dict):
            errors.append(
                "Each filter must be an object."
            )
            continue

        column = filter_item.get("column")
        operator = filter_item.get("operator")
        value = filter_item.get("value")

        # Validate column
        if column is None:
            errors.append(
                "Filter column is required."
            )
        else:
            try:
                resolve_column(
                    column,
                    df,
                    semantic_model,
                    semantic_embeddings
                )
            except ValueError:
                errors.append(
                    f"Filter column not found: {column}"
                )

        # Validate operator
        if operator not in allowed_operators:
            errors.append(
                f"Unsupported filter operator: {operator}"
            )

        # Validate value
        if value is None:
            errors.append(
                f"Filter value is required for column: {column}"
            )

    # --------------------------------
    # 5. Validate sorting
    # --------------------------------
    if sort is not None:

        if sort not in {"asc", "desc"}:
            errors.append(
                f"Sort must be 'asc' or 'desc', got: {sort}"
            )

    # --------------------------------
    # 6. Validate limit
    # --------------------------------
    if limit is not None:

        if not isinstance(limit, int):
            errors.append(
                "Limit must be an integer"
            )

        elif limit <= 0:
            errors.append(
                "Limit must be greater than 0"
            )

        elif limit > 100:
            errors.append(
                "Limit cannot exceed 100"
            )

    # --------------------------------
    # 7. Return result
    # --------------------------------
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }
