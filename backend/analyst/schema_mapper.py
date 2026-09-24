
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


SEMANTIC_RULES = {
    "revenue": {
        "keywords": ["sales", "revenue", "amount", "income"],
        "dtype": ["int64", "float64"]
    },
    "profit": {
        "keywords": ["profit", "earnings"],
        "dtype": ["int64", "float64"]
    },
    "quantity": {
        "keywords": ["quantity", "qty", "units"],
        "dtype": ["int64", "float64"]
    },
    "unit_price": {
        "keywords": ["price", "unit price"],
        "dtype": ["int64", "float64"]
    },
    "discount": {
        "keywords": ["discount", "discount rate"],
        "dtype": ["int64", "float64"]
    },
    "product": {
        "keywords": ["product", "description", "item"],
        "dtype": ["object"]
    },
    "product_id": {
        "keywords": ["product id", "product code", "stock code"],
        "dtype": ["object"]
    },
    "customer": {
        "keywords": ["customer name", "customer", "buyer", "client"],
        "dtype": ["object"]
    },
    "customer_id": {
        "keywords": ["customer id", "customer number", "customer code"],
        "dtype": ["object", "float64", "int64"]
    },
    "country": {
        "keywords": ["country", "nation", "country region"],
        "dtype": ["object"]
    },
    "state": {
        "keywords": ["state", "province"],
        "dtype": ["object"]
    },
    "city": {
        "keywords": ["city"],
        "dtype": ["object"]
    },
    "region": {
        "keywords": ["region", "sales region", "geographic region"],
        "dtype": ["object"]
    },
    "date": {
        "keywords": ["date", "time", "timestamp"],
        "dtype": ["datetime64[ns]", "datetime64"]
    },
    "identifier": {
        "keywords": ["id", "identifier", "invoice", "order id"],
        "dtype": ["object", "int64", "float64"]
    }
}


EXACT_COLUMN_RULES = {
    "row id": "identifier",
    "order id": "identifier",
    "invoice": "identifier",
    "stockcode": "product_id",

    "customer id": "customer_id",
    "customer name": "customer",

    "product id": "product_id",
    "product name": "product",

    "order date": "date",
    "ship date": "date",
    "invoice date": "date",

    "sales": "revenue",
    "profit": "profit",
    "quantity": "quantity",
    "price": "unit_price",
    "discount": "discount",

    "category": "category",
    "sub-category": "category",

    "ship mode": "dimension",
    "segment": "dimension",

    "country": "country",
    "country/region": "country",

    "state": "state",
    "province": "state",
    "state/province": "state",

    "city": "city",
    "region": "region",

    "postal code": "postal_code",

    "description": "product"
}


def classify_column(
    column_name,
    dtype,
    semantic_model,
    semantic_embeddings
):
    column_lower = column_name.lower().strip()

    if column_lower in EXACT_COLUMN_RULES:
        semantic_type = EXACT_COLUMN_RULES[column_lower]

        return {
            "column": column_name,
            "semantic_type": semantic_type,
            "confidence": 1.0,
            "source": "exact_rule",
            "alternatives": []
        }

    column_embedding = semantic_model.encode(
        [column_name],
        normalize_embeddings=True
    )

    scores = []

    for label, embeddings in semantic_embeddings.items():

        similarities = cosine_similarity(
            column_embedding,
            embeddings
        )[0]

        embedding_score = float(np.max(similarities))

        scores.append({
            "semantic_type": label,
            "embedding_score": embedding_score
        })

    for item in scores:

        label = item["semantic_type"]

        rule = SEMANTIC_RULES.get(
            label,
            {}
        )

        keyword_match = any(
            keyword in column_lower
            for keyword in rule.get("keywords", [])
        )

        dtype_match = str(dtype) in rule.get(
            "dtype",
            []
        )

        final_score = item["embedding_score"]

        if keyword_match:
            final_score += 0.35

        if dtype_match:
            final_score += 0.10

        item["keyword_match"] = keyword_match
        item["dtype_match"] = dtype_match
        item["score"] = final_score

    scores.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    best = scores[0]

    return {
        "column": column_name,
        "semantic_type": best["semantic_type"],
        "confidence": round(
            min(best["score"], 1.0),
            4
        ),
        "source": "embedding_rules",
        "alternatives": scores[:3]
    }


def resolve_column(
    column_name,
    df,
    semantic_model,
    semantic_embeddings
):
    normalized_name = column_name.lower().strip()

    # Exact column match
    for column in df.columns:
        if column.lower().strip() == normalized_name:
            return column

    # Semantic role match
    matches = []

    for column in df.columns:

        result = classify_column(
            column,
            str(df[column].dtype),
            semantic_model,
            semantic_embeddings
        )

        if result["semantic_type"] == normalized_name:
            matches.append(column)

    if not matches:
        raise ValueError(
            f"Could not resolve column or semantic role: {column_name}"
        )

    if len(matches) == 1:
        return matches[0]

    raise ValueError(
        f"Ambiguous column '{column_name}'. "
        f"Possible columns: {matches}"
    )


def resolve_group_by(
    group_by,
    df,
    semantic_model,
    semantic_embeddings
):
    normalized_name = group_by.lower().strip()

    # Exact column match
    for column in df.columns:
        if column.lower().strip() == normalized_name:
            return column

    # Semantic role match
    matches = []

    for column in df.columns:

        result = classify_column(
            column,
            str(df[column].dtype),
            semantic_model,
            semantic_embeddings
        )

        if result["semantic_type"] == normalized_name:
            matches.append(column)

    if not matches:
        raise ValueError(
            f"Could not resolve group_by: {group_by}"
        )

    if len(matches) == 1:
        return matches[0]

    raise ValueError(
        f"Ambiguous group_by '{group_by}'. "
        f"Possible columns: {matches}. "
        f"Please specify the exact column or a more specific semantic role."
    )


METRIC_DEFINITIONS = {

    "revenue": {
        "description": "Total monetary value of transactions",
        "direct_columns": ["Sales"],
        "derived": {
            "required_columns": ["Quantity", "Price"],
            "expression": "Quantity * Price"
        }
    },

    "profit": {
        "description": "Profit generated from transactions",
        "direct_columns": ["Profit"],
        "derived": None
    },

    "quantity": {
        "description": "Number of units sold",
        "direct_columns": ["Quantity"],
        "derived": None
    },

    "unit_price": {
        "description": "Price per unit",
        "direct_columns": ["Price"],
        "derived": None
    },

    "discount": {
        "description": "Discount applied to transactions",
        "direct_columns": ["Discount"],
        "derived": None
    }
}


def resolve_metric(
    metric_name,
    df
):
    metric_name = metric_name.lower().strip()

    if metric_name not in METRIC_DEFINITIONS:
        raise ValueError(
            f"Unsupported metric: {metric_name}"
        )

    definition = METRIC_DEFINITIONS[metric_name]

    # Direct metric
    for column in definition["direct_columns"]:

        if column in df.columns:

            return {
                "metric": metric_name,
                "type": "direct",
                "column": column,
                "expression": None
            }

    # Derived metric
    derived = definition.get("derived")

    if derived is not None:

        required_columns = derived[
            "required_columns"
        ]

        if all(
            column in df.columns
            for column in required_columns
        ):

            return {
                "metric": metric_name,
                "type": "derived",
                "column": None,
                "required_columns": required_columns,
                "expression": derived["expression"]
            }

    raise ValueError(
        f"Metric '{metric_name}' "
        f"is not available for this dataset."
    )
