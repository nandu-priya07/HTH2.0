
QUERY_OPERATIONS = {
    "sum",
    "average",
    "count",
    "count_distinct",
    "min",
    "max"
}


def create_query_plan(
    operation,
    metric=None,
    group_by=None,
    filters=None,
    sort=None,
    limit=None
):
    operation = operation.lower().strip()

    if operation not in QUERY_OPERATIONS:
        raise ValueError(
            f"Unsupported operation: {operation}"
        )

    return {
        "operation": operation,
        "metric": metric,
        "group_by": group_by,
        "filters": filters or [],
        "sort": sort,
        "limit": limit
    }
