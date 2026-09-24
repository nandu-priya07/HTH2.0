import pandas as pd
from geo import run_geo_analysis
from geo.entity_discovery import discover_geo_profile
from geo.hierarchy_discovery import discover_hierarchy
from geo.metric_synthesis import resolve_metric
from geo.geo_resolver import GeoResolver
from analyst.models import LLMResponse, QuerySpec
from analyst.query_processor import _geo_query_from_grouped_plan, _fallback_geo_query


def test_geo_ranking_and_profit_synthesis():
    df=pd.DataFrame({"Country":["US","US","US"],"Province":["CA","CA","NY"],"Municipality":["A","B","C"],"Revenue":[100,70,40],"Cost":[20,90,20]})
    result=run_geo_analysis(df,{"analysis_type":"geographic_analysis","intent":"ranking","geographic_dimension":"Municipality","metric":{"column":"profit","type":"derived","aggregation":"sum"},"comparison":{"direction":"highest"}})
    assert result["success"] and result["result"]["locations"][0]["Municipality"] == "A"
    assert result["evidence"]["metric"]["formula"] == "Revenue - Cost"


def test_schema_agnostic_hierarchy():
    df=pd.DataFrame({"Country":["US","US","CA"],"Province":["CA","NY","ON"],"Municipality":["A","B","C"],"Sales":[1,2,3]})
    profile=discover_geo_profile(df)
    hierarchy=discover_hierarchy(df,profile)
    assert [x["column"] for x in hierarchy] == ["Country","Province","Municipality"]


def test_anomaly_baseline_is_data_driven_and_unresolved_places_stay_ranked():
    df=pd.DataFrame({"city":["a","b","c","d","e"],"sales":[100,101,99,98,-1000]})
    result=run_geo_analysis(df,{"analysis_type":"geographic_analysis","intent":"anomaly","geographic_dimension":"city","metric":{"column":"sales","aggregation":"sum"}})
    assert result["result"]["anomaly"]["method"] == "robust_z_score"
    assert result["geo"]["map_data"] == []
    assert len(result["geo"]["locations"]) == 5


def test_missing_geography_is_graceful():
    result=run_geo_analysis(pd.DataFrame({"sales":[1,2]}),{"analysis_type":"geographic_analysis","geographic_dimension":"city","metric":{"column":"sales"}})
    assert not result["success"] and "No geographic fields" in result["error"]


def test_existing_metric_preferred_to_synthesis():
    df=pd.DataFrame({"profit":[1],"revenue":[2],"cost":[1]})
    assert resolve_metric(df,"profit")["derived"] is False


def test_revenue_quantity_times_price_by_real_country_values():
    df=pd.DataFrame({"Invoice":[1,1,2,3],"Quantity":[2,4,1,10],"Price":[5,5,9,2],"Country":["United Kingdom","United Kingdom","France","Germany"]})
    result=run_geo_analysis(df,{"analysis_type":"geographic_analysis","intent":"ranking","geographic_dimension":"Country","metric":{"column":"Revenue","type":"derived","aggregation":"sum"},"comparison":{"direction":"highest"}})
    assert result["metric_detail"]["formula"] == "Quantity * Price"
    assert result["results"][0]["location"] == "United Kingdom"
    assert result["results"][0]["value"] == 30
    assert {r["location"] for r in result["results"]} == set(df["Country"])
    assert result["results"][0]["transactions"] == 1
    assert result["map"]["type"] == "choropleth"


def test_metric_inventory_supports_safe_revenue_and_order_count():
    df=pd.DataFrame({"quantity":[1],"price":[3],"invoice":[10]})
    assert resolve_metric(df,"Revenue")["formula"] == "quantity * price"
    assert resolve_metric(df,"Orders")["formula"] == "COUNT DISTINCT(invoice)"


def test_high_low_limit_and_selected_location_are_data_driven():
    df=pd.DataFrame({"country":["A","A","B","C"],"quantity":[1,1,4,2],"price":[3,2,5,7]})
    result=run_geo_analysis(df,{"analysis_type":"geographic_analysis","geographic_dimension":"country","metric":{"column":"revenue","type":"derived","aggregation":"sum"},"comparison":{"direction":"lowest"},"limit":1,"selected_location":"B"})
    assert result["results"][0]["location"] == "A"
    assert result["results"][1]["location"] == "B"
    assert result["results"][1]["rank"] == 3


def test_continent_filter_uses_bundled_geographic_metadata():
    df=pd.DataFrame({"country":["United Kingdom","Germany","Canada"],"sales":[5,3,10]})
    spec={"analysis_type":"geographic_analysis","geographic_dimension":"country","metric":{"column":"sales","aggregation":"sum"},"filters":[{"column":"country","operator":"continent","value":"Europe"}]}
    result=run_geo_analysis(df,spec)
    assert {r["location"] for r in result["results"]} == {"United Kingdom","Germany"}


def test_country_geometry_resolution_never_invents_dataset_locations():
    resolved, missing=GeoResolver().resolve_geometry_names(["United Kingdom","Germany","NOT A COUNTRY"])
    assert "United Kingdom" in resolved and "Germany" in resolved
    assert "NOT A COUNTRY" not in resolved and missing == 1


def test_llm_grouped_plan_normalizes_to_derived_geo_metric():
    df=pd.DataFrame({"country":["A"],"quantity":[1],"price":[2]})
    response=LLMResponse(type="data_query",query=QuerySpec(operation="sum",column="price",group_by=["country"],limit=1))
    spec=_geo_query_from_grouped_plan(response,"Show revenue by country",df)
    assert spec["geographic_dimension"] == "country"
    assert spec["metric"]["column"] == "revenue"
    assert spec["limit"] is None


def test_followup_fallback_retains_geo_metric_and_applies_continent():
    df=pd.DataFrame({"country":["United Kingdom","Germany","Canada"],"quantity":[1,2,3],"price":[4,5,6]})
    context={"previous_result":{"query_spec":{"analysis_type":"geographic_analysis","intent":"ranking","geographic_dimension":"country","metric":{"column":"Revenue","aggregation":"sum"},"filters":[]}}}
    spec=_fallback_geo_query("Only European countries",df,context)
    assert spec["metric"]["column"] == "Revenue"
    assert spec["geographic_dimension"] == "country"
    assert spec["filters"] == [{"column":"country","operator":"continent","value":"Europe"}]
