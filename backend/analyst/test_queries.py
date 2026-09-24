
import pandas as pd

from .question_parser import parse_question
from .query_executor import execute_query


def run_test(
    question,
    df,
    semantic_model,
    semantic_embeddings,
    expected_columns=None
):
    print("\n" + "=" * 80)
    print("QUESTION:", question)

    query_plan = parse_question(question)

    print("PLAN:", query_plan)

    result = execute_query(
        query_plan,
        df,
        semantic_model,
        semantic_embeddings
    )

    print("RESULT:")
    print(result.to_string(index=False))

    if expected_columns:
        actual_columns = result.columns.tolist()

        assert actual_columns == expected_columns, (
            f"Expected columns {expected_columns}, "
            f"got {actual_columns}"
        )

    assert len(result) > 0, (
        "Query returned no rows"
    )

    print("✅ PASSED")

    return result


def run_all_tests(
    superstore_df,
    online_retail_df,
    semantic_model,
    semantic_embeddings
):

    # --------------------------------------------------
    # SUPERSTORE TESTS
    # --------------------------------------------------

    run_test(
        "What is the average profit by category?",
        superstore_df,
        semantic_model,
        semantic_embeddings,
        ["Category", "value"]
    )

    run_test(
        "How many unique customers are there?",
        superstore_df,
        semantic_model,
        semantic_embeddings,
        ["value"]
    )

    run_test(
        "What is the total revenue by region?",
        superstore_df,
        semantic_model,
        semantic_embeddings,
        ["Region", "value"]
    )

    run_test(
        "What is the total revenue in the West region?",
        superstore_df,
        semantic_model,
        semantic_embeddings,
        ["Region", "value"]
    )

    run_test(
        "What are the top 5 products by revenue in Technology?",
        superstore_df,
        semantic_model,
        semantic_embeddings,
        ["Product Name", "value"]
    )

    # --------------------------------------------------
    # ONLINE RETAIL II TESTS
    # --------------------------------------------------

    run_test(
        "What are the top 5 countries by revenue?",
        online_retail_df,
        semantic_model,
        semantic_embeddings,
        ["Country", "value"]
    )

    print("\n" + "=" * 80)
    print("🎉 ALL ANALYST TESTS PASSED")
    print("=" * 80)
