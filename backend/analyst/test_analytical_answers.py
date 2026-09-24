"""
Regression tests for schema-aware metric derivation, calculation-safe answers,
natural-language summaries, and aggregate follow-up context.

All tests are deterministic: the Qwen3 planner/summarizer is disabled, so these
exercise the rule router + semantic layer + Pandas executor + template summaries.
"""

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from analyst.models import QuerySpec, FilterSpec, LLMResponse
from analyst.query_executor import execute_query
from analyst.query_processor import process_query_with_llm
from analyst.semantics import (
    apply_semantic_layer, resolve_concept, detect_concepts, extract_years, temporal_columns,
)
from analyst.summarizer import generate_answer, describe_no_data, verify_answer
from analyst.follow_up import resolve_analytical_follow_up


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    import llm.client as client_mod
    monkeypatch.setattr(client_mod.OllamaClient, "is_available", lambda self: False)
    monkeypatch.setenv("QUERYLENS_LLM_SUMMARY", "0")


@pytest.fixture
def superstore_df():
    return pd.DataFrame({
        "order_id": ["O-1", "O-1", "O-2", "O-3", "O-4"],
        "customer_id": ["C-1", "C-1", "C-2", "C-3", "C-3"],
        "country_region": ["United States", "United States", "Canada", "United States", "Canada"],
        "region": ["West", "East", "East", "West", "Central"],
        "profit": [200000.00, 86397.02, 5000.00, 0.00, 899.79],
        "order_date": ["2024-01-05", "2024-06-01", "2023-03-02", "2024-12-31 15:30:00", "2022-07-19"],
    })


def _answer(question, df):
    """Full deterministic pipeline: plan -> semantic layer -> execute -> summarize."""
    resp = process_query_with_llm(question, None, None, df)
    if resp.type != "data_query":
        return resp.type, resp.answer, resp, None
    specs = resp.all_queries
    res = execute_query(specs[0], df)
    if not res.success:
        return res.status, describe_no_data(specs[0], res, df), resp, res
    text, _ = generate_answer(question, specs, res, use_llm=False)
    return "success", text, resp, res


# ==============================================================================
# TEST 1-3: totals, filter-before-aggregate, grouped summaries
# ==============================================================================

def test_1_total_profit_summary(superstore_df):
    status, text, _, res = _answer("What is the total profit?", superstore_df)
    assert status == "success"
    assert text == "Total profit is $292,296.81 across 5 records."
    assert res.rows_after_filter == 5


def test_2_total_profit_for_canada_filters_before_sum(superstore_df):
    status, text, resp, res = _answer("What is the total profit for Canada?", superstore_df)
    assert status == "success"
    assert res.result == pytest.approx(5899.79)
    assert res.rows_before_filter == 5 and res.rows_after_filter == 2
    assert text.startswith("Total profit for Canada is $5,899.79")
    assert res.calculation_steps[1].startswith("Filtered country_region = Canada")


def test_3_profit_for_each_country_leads_with_total():
    df = pd.DataFrame({
        "country_region": ["United States", "Canada", "United States"],
        "profit": [200000.00, 5899.79, 86397.02],
    })
    spec = QuerySpec(operation="sum", column="profit", group_by=["country_region"])
    res = execute_query(spec, df)
    text, _ = generate_answer("What is the total profit for each country?", [spec], res, use_llm=False)
    assert text.startswith("Total profit is $292,296.81.")
    assert "United States contributes $286,397.02, while Canada contributes $5,899.79" in text
    assert "about 98%" in text
    assert res.table["rows"][0][0] == "United States"
    assert "Breakdown of" not in text


def test_3b_group_by_phrase_each_country_via_rules(superstore_df):
    status, text, resp, res = _answer("What is the total profit for each country region?", superstore_df)
    assert status == "success"
    assert resp.all_queries[0].group_by == ["country_region"]
    assert text.startswith("Total profit is $292,296.81.")


# ==============================================================================
# TEST 4-8: revenue availability states
# ==============================================================================

def test_4_revenue_direct_with_year_column():
    df = pd.DataFrame({"Revenue": [100.0, 200.0, 300.0, 50.0], "Year": [2023, 2024, 2024, 2022]})
    status, text, resp, res = _answer("What is the revenue for 2024?", df)
    assert status == "success"
    assert res.result == 500.0
    assert resp.all_queries[0].filters[0].column == "Year"
    assert resp.all_queries[0].filters[0].value == 2024
    assert text == "Total revenue in 2024 is $500.00 across 2 records."


def test_5_revenue_derived_from_cost_plus_profit():
    df = pd.DataFrame({"Cost": [60.0, 120.0, 150.0], "Profit": [40.0, 80.0, 150.0], "Year": [2023, 2024, 2024]})
    status, text, resp, res = _answer("What is the revenue for 2024?", df)
    assert status == "success"
    spec = resp.all_queries[0]
    assert spec.derived_metric is not None and spec.derived_metric.formula == "Cost + Profit"
    assert res.result == 500.0  # (120+80) + (150+150), 2024 only
    assert "calculated as Cost + Profit" in text
    assert res.derived_metric["formula"] == "Cost + Profit"
    assert set(res.fields_used) >= {"Cost", "Profit", "Year"}
    assert "revenue" not in res.fields_used


def test_6_revenue_never_equals_cost():
    df = pd.DataFrame({"Cost": [60.0, 120.0], "Year": [2023, 2024]})
    status, text, resp, _ = _answer("What is the revenue for 2024?", df)
    assert status == "not_available"
    assert text.startswith("Revenue isn't available for 2024 in this dataset.")
    assert "The dataset contains Cost and Year" in text
    assert "derive Revenue reliably" in text
    assert resp.details["requested_metric"] == "revenue"


def test_6b_llm_mapping_revenue_to_cost_is_overridden():
    df = pd.DataFrame({"Cost": [60.0, 120.0], "Year": [2023, 2024]})
    spec = QuerySpec(operation="sum", column="Cost", requested_metric="revenue")
    resp = apply_semantic_layer(LLMResponse(type="data_query", query=spec, queries=[spec]),
                                "What is the revenue for 2024?", df)
    assert resp.type == "not_available"


def test_6c_profit_never_equals_revenue():
    df = pd.DataFrame({"Revenue": [100.0, 200.0], "Year": [2023, 2024]})
    status, text, _, _ = _answer("What is profit for 2024?", df)
    assert status == "not_available"
    assert "Cost" in text  # tells the user which component is missing


def test_7_profit_derived_from_revenue_minus_cost():
    df = pd.DataFrame({"Revenue": [100.0, 200.0, 300.0], "Cost": [70.0, 150.0, 100.0], "Year": [2023, 2024, 2024]})
    status, text, resp, res = _answer("What is profit for 2024?", df)
    assert status == "success"
    assert res.result == 250.0
    assert "calculated as Revenue - Cost" in text


def test_8_zero_matching_year_never_returns_total():
    df = pd.DataFrame({"Revenue": [100.0, 200.0, 300.0], "Year": [2022, 2023, 2024]})
    status, text, _, res = _answer("What is revenue in 2035?", df)
    assert status == "no_data"
    assert text.startswith("I couldn't find any records for 2035 in this dataset.")
    assert "Revenue is available" in text
    assert "2022 to 2024" in text
    assert res.rows_after_filter == 0


def test_year_without_temporal_field_is_not_answered_with_overall_total():
    df = pd.DataFrame({"Revenue": [100.0, 200.0], "Region": ["E", "W"]})
    status, text, _, _ = _answer("What was revenue in 2024?", df)
    assert status == "not_available"
    assert text == ("I can calculate total revenue, but I can't isolate 2024 because this dataset "
                    "doesn't contain a date or year field.")


def test_date_column_year_filter_includes_last_day(superstore_df):
    status, text, _, res = _answer("What is the total profit in 2024?", superstore_df)
    assert status == "success"
    # 2024-12-31 15:30 must be included by the inclusive year range.
    assert res.rows_after_filter == 3
    assert res.result == pytest.approx(286397.02)
    assert "in 2024" in text


def test_selling_price_times_quantity_revenue():
    df = pd.DataFrame({"Selling Price": [10.0, 20.0], "Quantity": [3, 2]})
    status, text, resp, res = _answer("What is the total revenue?", df)
    assert status == "success"
    assert res.result == 70.0
    assert "Selling Price × Quantity" in text


def test_customer_count_uses_distinct_ids(superstore_df):
    status, text, resp, res = _answer("How many customers are there?", superstore_df)
    assert status == "success"
    assert resp.all_queries[0].operation == "count_distinct"
    assert res.result == 3
    assert text.startswith("There are 3 unique customers")


# ==============================================================================
# Ambiguity & synonyms
# ==============================================================================

def test_ambiguous_sales_asks_for_clarification():
    df = pd.DataFrame({"Gross Sales": [1.0], "Net Sales": [1.0], "Revenue": [1.0], "Year": [2024]})
    status, text, resp, _ = _answer("What were sales in 2024?", df)
    assert status == "clarification"
    assert text == "I found Gross Sales, Net Sales, and Revenue. Which one should I use for 'sales'?"
    assert "What were Net Sales in 2024?" in resp.details["options"]


def test_ambiguous_even_if_planner_picked_one_column():
    df = pd.DataFrame({"Gross Sales": [1.0], "Net Sales": [1.0], "Year": [2024]})
    spec = QuerySpec(operation="sum", column="Net Sales")
    resp = apply_semantic_layer(LLMResponse(type="data_query", query=spec, queries=[spec]),
                                "What were sales in 2024?", df)
    assert resp.type == "clarification"


def test_explicit_column_choice_is_respected():
    df = pd.DataFrame({"Gross Sales": [1.0], "Net Sales": [2.0], "Year": [2024]})
    spec = QuerySpec(operation="sum", column="Net Sales")
    resp = apply_semantic_layer(LLMResponse(type="data_query", query=spec, queries=[spec]),
                                "What were Net Sales in 2024?", df)
    assert resp.type == "data_query"
    assert resp.all_queries[0].column == "Net Sales"


def test_revenue_uses_sales_column_and_says_so():
    df = pd.DataFrame({"Sales": [10.0, 20.0], "Region": ["E", "W"]})
    status, text, _, res = _answer("What is the total revenue?", df)
    assert status == "success"
    assert res.result == 30.0
    assert "using the Sales field" in text


def test_unit_cost_is_not_cost():
    df = pd.DataFrame({"Unit Cost": [2.0, 3.0], "Quantity": [10, 5]})
    res = resolve_concept("cost", df)
    assert res.status == "derived"
    assert res.derived.formula == "Unit Cost × Quantity"


def test_detect_concepts_ignores_literal_columns():
    assert detect_concepts("total profit by sales channel", ["profit", "sales_channel"]) == []
    assert detect_concepts("revenue in 2024", ["Cost", "Year"]) == ["revenue"]


def test_year_extraction():
    assert extract_years("revenue in 2024.") == [2024]
    assert extract_years("top 2000 products") == []
    assert temporal_columns(pd.DataFrame({"Year": [2023, 2024], "Qty": [1, 2]})) == (["Year"], [])


# ==============================================================================
# TEST 9: follow-up context
# ==============================================================================

def test_9_follow_up_chain(superstore_df):
    prev = QuerySpec(operation="sum", column="profit").to_dict()

    canada = resolve_analytical_follow_up("What about Canada?", prev, superstore_df)
    assert canada.operation == "sum" and canada.column == "profit"
    assert [(f.column, f.value) for f in canada.filters] == [("country_region", "Canada")]

    germany_df = superstore_df.assign(country_region=["Germany", "Germany", "Canada", "United States", "Canada"])
    germany = resolve_analytical_follow_up("What about Germany?", canada.to_dict(), germany_df)
    assert [(f.column, f.value) for f in germany.filters] == [("country_region", "Germany")]

    by_region = resolve_analytical_follow_up("Break that down by region.", germany.to_dict(), germany_df)
    assert by_region.group_by == ["region"]
    assert [(f.column, f.value) for f in by_region.filters] == [("country_region", "Germany")]

    avg = resolve_analytical_follow_up("What is the average instead?", by_region.to_dict(), germany_df)
    assert avg.operation == "average"
    assert avg.group_by == ["region"] and avg.column == "profit"
    assert [(f.column, f.value) for f in avg.filters] == [("country_region", "Germany")]


def test_9b_break_down_by_country_keeps_filters(superstore_df):
    prev = QuerySpec(operation="sum", column="profit",
                     filters=[FilterSpec(column="order_date", operator="between", value=["2024-01-01", "2024-12-31"])]).to_dict()
    spec = resolve_analytical_follow_up("Break this down by country", prev, superstore_df)
    assert spec.group_by == ["country_region"]
    assert spec.filters[0].column == "order_date"


def test_follow_up_preserves_derived_metric():
    df = pd.DataFrame({"Cost": [60.0, 120.0, 150.0], "Profit": [40.0, 80.0, 150.0],
                       "Year": [2023, 2024, 2024], "Region": ["E", "W", "E"]})
    _, _, resp, _ = _answer("What is the revenue for 2024?", df)
    prev = resp.all_queries[0].to_dict()
    spec = resolve_analytical_follow_up("What about 2023?", prev, df)
    assert spec.derived_metric.formula == "Cost + Profit"
    assert [(f.column, f.value) for f in spec.filters] == [("Year", 2023)]
    assert execute_query(spec, df).result == 100.0


def test_non_follow_up_returns_none(superstore_df):
    prev = QuerySpec(operation="sum", column="profit").to_dict()
    assert resolve_analytical_follow_up("What about Narnia?", prev, superstore_df) is None
    grade_prev = QuerySpec(operation="conditional_count", columns=["a"]).to_dict()
    assert resolve_analytical_follow_up("What about Canada?", grade_prev, superstore_df) is None


# ==============================================================================
# Summary verification
# ==============================================================================

def test_llm_summary_with_invented_number_is_rejected():
    facts = {"value": "$5,899.79", "records": "2"}
    draft = "Total profit for Canada is $5,899.79 across 2 records."
    assert verify_answer("Canada's total profit is $5,899.79 across 2 records.", facts, draft)
    assert not verify_answer("Canada's total profit is $5,900 across 2 records.", facts, draft)
    assert not verify_answer("Total profit for Canada is $5,899.79, likely due to strong sales.", facts, draft)


def test_llm_summary_falls_back_to_template_when_unverified():
    class FakeClient:
        def is_available(self):
            return True

        def generate_json(self, *args, **kwargs):
            return {"answer": "Profit is roughly $6,000."}

    df = pd.DataFrame({"country_region": ["Canada", "Canada"], "profit": [5000.0, 899.79]})
    spec = QuerySpec(operation="sum", column="profit")
    res = execute_query(spec, df)
    text, source = generate_answer("What is the total profit?", [spec], res, use_llm=True, client=FakeClient())
    assert source == "template"
    assert text == "Total profit is $5,899.79 across 2 records."


# ==============================================================================
# End-to-end through the API
# ==============================================================================

@pytest.fixture
def api(tmp_path, monkeypatch):
    storage_chats = tmp_path / "storage" / "chats"
    storage_chats.mkdir(parents=True, exist_ok=True)
    import chat
    import chat.json_repository as jr
    import routes.upload as ru
    import storage.dataset_manager as dm
    from chat.json_repository import JsonChatRepository
    from chat.service import ChatService
    from main import app

    monkeypatch.setattr(jr, "STORAGE_CHATS_DIR", storage_chats)
    monkeypatch.setattr(ru, "STORAGE_CHATS_DIR", storage_chats)
    monkeypatch.setattr(dm, "CHATS_DIR", storage_chats)
    dm.DATASET_REGISTRY.clear()
    monkeypatch.setattr(chat, "_chat_service_instance", ChatService(repository=JsonChatRepository(storage_dir=storage_chats)))
    return TestClient(app)


def _chat_with_csv(client, csv_text):
    chat_id = client.post("/chats", json={"title": "t"}).json()["id"]
    up = client.post(f"/chats/{chat_id}/files",
                     files={"file": ("data.csv", io.BytesIO(csv_text.encode()), "text/csv")})
    assert up.status_code == 200
    return chat_id


def _ask(client, chat_id, question):
    r = client.post(f"/chats/{chat_id}/messages", json={"question": question})
    assert r.status_code == 200
    return r.json()


def test_api_derived_not_available_and_follow_ups(api):
    chat_id = _chat_with_csv(api, "Cost,Profit,Year,Country\n60,40,2023,Canada\n120,80,2024,Canada\n150,150,2024,Germany\n")

    d = _ask(api, chat_id, "What is the revenue for 2024?")
    assert d["status"] == "success"
    assert d["text"] == "Total revenue in 2024 is $500.00 across 2 records, calculated as Cost + Profit."
    assert d["derived_metric"]["formula"] == "Cost + Profit"
    assert d["rows_before_filter"] == 3 and d["rows_after_filter"] == 2

    d = _ask(api, chat_id, "What about Canada?")
    assert d["status"] == "success"
    assert d["result"] == 200.0
    assert d["text"].startswith("Total revenue for Canada in 2024 is $200.00")

    d = _ask(api, chat_id, "What about Germany?")
    assert d["result"] == 300.0

    d = _ask(api, chat_id, "What is revenue in 2035?")
    assert d["status"] == "no_data"
    assert d["text"].startswith("I couldn't find any records for 2035 in this dataset.")

    d = _ask(api, chat_id, "What is the total quantity?")
    assert d["status"] == "not_available"


def test_api_grouped_answer_and_breakdown_follow_up(api):
    chat_id = _chat_with_csv(api, "country_region,region,profit\nUnited States,West,200000\n"
                                  "United States,East,86397.02\nCanada,East,5899.79\n")
    d = _ask(api, chat_id, "What is the total profit?")
    assert d["text"] == "Total profit is $292,296.81 across 3 records."

    d = _ask(api, chat_id, "Break this down by country")
    assert d["status"] == "success"
    assert d["group_by"] == ["country_region"]
    assert d["text"].startswith("Total profit is $292,296.81.")
    assert d["table"]["rows"][0][0] == "United States"
