
import pandas as pd

from .schema_mapper import (
    resolve_column,
    resolve_group_by,
    resolve_metric
)

from .query_validator import validate_query_plan


def apply_filters(
    df,
    filters,
    semantic_model,
    semantic_embeddings
):
    filtered_df = df.copy()

    for filter_item in filters:

        column_name = filter_item["column"]
        operator = filter_item["operator"]
        value = filter_item["value"]

        column = resolve_column(
            column_name,
            filtered_df,
            semantic_model,
            semantic_embeddings
        )

        if operator == "=":
            filtered_df = filtered_df[
                filtered_df[column] == value
            ]

        elif operator == "!=":
            filtered_df = filtered_df[
                filtered_df[column] != value
            ]

        elif operator == ">":
            filtered_df = filtered_df[
                filtered_df[column] > value
            ]

        elif operator == "<":
            filtered_df = filtered_df[
                filtered_df[column] < value
            ]

        elif operator == ">=":
            filtered_df = filtered_df[
                filtered_df[column] >= value
            ]

        elif operator == "<=":
            filtered_df = filtered_df[
                filtered_df[column] <= value
            ]

        else:
            raise ValueError(
                f"Unsupported filter operator: {operator}"
            )

    return filtered_df


def execute_query(
    query_plan,
    df,
    semantic_model,
    semantic_embeddings
):

    # Validate query plan
    validation = validate_query_plan(
        query_plan,
        df,
        semantic_model,
        semantic_embeddings
    )

    if not validation["valid"]:
        raise ValueError(
            f"Invalid query plan: {validation['errors']}"
        )

    operation = query_plan["operation"]
    metric = query_plan.get("metric")
    group_by = query_plan.get("group_by")
    filters = query_plan.get("filters", [])
    sort = query_plan.get("sort")
    limit = query_plan.get("limit")

    working_df = df.copy()

    # Apply filters
    if filters:
        working_df = apply_filters(
            working_df,
            filters,
            semantic_model,
            semantic_embeddings
        )

    # Resolve group-by column
    if group_by:

        group_column = resolve_group_by(
            group_by,
            working_df,
            semantic_model,
            semantic_embeddings
        )

    else:
        group_column = None

    # COUNT DISTINCT
    if operation == "count_distinct":

        if metric is None:
            raise ValueError(
                "count_distinct requires a metric"
            )

        metric_column = resolve_column(
            metric,
            working_df,
            semantic_model,
            semantic_embeddings
        )

        if group_column:

            result = (
                working_df
                .groupby(group_column)[metric_column]
                .nunique()
                .reset_index(name="value")
            )

        else:

            result = pd.DataFrame({
                "value": [
                    working_df[metric_column].nunique()
                ]
            })

    # COUNT
    elif operation == "count":

        if group_column:

            result = (
                working_df
                .groupby(group_column)
                .size()
                .reset_index(name="value")
            )

        else:

            result = pd.DataFrame({
                "value": [len(working_df)]
            })

    # Other aggregations
    else:

        if metric is None:
            raise ValueError(
                f"{operation} requires a metric"
            )

        metric_info = resolve_metric(
            metric,
            working_df
        )

        # Direct metric
        if metric_info["type"] == "direct":

            metric_column = metric_info["column"]

        # Derived metric
        else:

            required_columns = (
                metric_info["required_columns"]
            )

            expression = metric_info["expression"]

            if expression == "Quantity * Price":

                working_df["_metric"] = (
                    working_df[required_columns[0]]
                    * working_df[required_columns[1]]
                )

                metric_column = "_metric"

            else:

                raise ValueError(
                    f"Unsupported derived expression: "
                    f"{expression}"
                )

        # SUM
        if operation == "sum":

            if group_column:

                result = (
                    working_df
                    .groupby(group_column)[metric_column]
                    .sum()
                    .reset_index(name="value")
                )

            else:

                result = pd.DataFrame({
                    "value": [
                        working_df[metric_column].sum()
                    ]
                })

        # AVERAGE
        elif operation == "average":

            if group_column:

                result = (
                    working_df
                    .groupby(group_column)[metric_column]
                    .mean()
                    .reset_index(name="value")
                )

            else:

                result = pd.DataFrame({
                    "value": [
                        working_df[metric_column].mean()
                    ]
                })

        # MIN
        elif operation == "min":

            if group_column:

                result = (
                    working_df
                    .groupby(group_column)[metric_column]
                    .min()
                    .reset_index(name="value")
                )

            else:

                result = pd.DataFrame({
                    "value": [
                        working_df[metric_column].min()
                    ]
                })

        # MAX
        elif operation == "max":

            if group_column:

                result = (
                    working_df
                    .groupby(group_column)[metric_column]
                    .max()
                    .reset_index(name="value")
                )

            else:

                result = pd.DataFrame({
                    "value": [
                        working_df[metric_column].max()
                    ]
                })

        else:

            raise ValueError(
                f"Unsupported operation: {operation}"
            )

    # Sort grouped results
    if sort and group_column:

        result = result.sort_values(
            "value",
            ascending=(sort == "asc")
        )

    # Apply TOP N / LIMIT
    if limit:

        result = result.head(limit)

    return result.reset_index(drop=True)
