import pandas as pd
import json
import os
import tempfile
from geo import run_geo_analysis
from geo.entity_discovery import discover_geo_profile
from geo.hierarchy_discovery import discover_hierarchy
from geo.metric_synthesis import resolve_metric
from geo.geo_resolver import GeoBoundaryProvider, GeoResolver
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


def test_hierarchy_parent_links_and_duplicate_child_names_are_contextual():
    df=pd.DataFrame({"Country":["India","India","USA","USA"],"Province":["Georgia","Tamil Nadu","Georgia","California"],"Municipality":["Tbilisi","Chennai","Atlanta","Los Angeles"],"Quantity":[1,2,3,4],"Price":[10,10,10,10]})
    hierarchy=discover_hierarchy(df)
    assert [x["column"] for x in hierarchy] == ["Country","Province","Municipality"]
    assert hierarchy[1]["parent_column"] == "Country"
    result=run_geo_analysis(df,{"analysis_type":"geographic_analysis","geography":{"column":"Province","level":"admin1"},"geographic_dimension":"Province","metric":{"column":"Revenue","type":"derived","aggregation":"sum"},"filters":[{"column":"Country","operator":"=","value":"India"}]})
    assert result["success"]
    assert {row["location"] for row in result["results"]} == {"India — Georgia","India — Tamil Nadu"}
    assert all(row["parents"] == {"Country":"India"} for row in result["results"])


def test_comparison_across_parents_keeps_names_and_ranks_scoped():
    df=pd.DataFrame({"Country":["India","USA","India","USA"],"Province":["Georgia","Georgia","Tamil Nadu","California"],"Sales":[100,90,50,70]})
    result=run_geo_analysis(df,{"analysis_type":"geographic_analysis","geographic_dimension":"Province","metric":{"column":"Sales","aggregation":"sum"}})
    georgias=[row for row in result["results"] if row["entity"]=="Georgia"]
    assert {row["location"] for row in georgias} == {"India — Georgia","USA — Georgia"}
    assert all(row["rank"]==1 for row in georgias)
    assert {row["share"] for row in georgias} == {round(100/150,6),round(90/160,6)}


def test_geography_parent_becomes_validated_filter():
    df=pd.DataFrame({"Country":["India","USA","USA"],"Province":["Tamil Nadu","California","Texas"],"Sales":[1,2,3]})
    result=run_geo_analysis(df,{"analysis_type":"geographic_analysis","geography":{"level":"admin1","column":"Province","parent":{"column":"Country","value":"USA"}},"geographic_dimension":"Province","metric":{"column":"Sales","aggregation":"sum"}})
    assert result["success"]
    assert {row["location"] for row in result["results"]} == {"USA — California","USA — Texas"}
    assert result["evidence"]["filters"] == [{"column":"Country","operator":"=","value":"USA"}]


def test_country_only_hierarchy_has_no_invented_child_level():
    df=pd.DataFrame({"Country":["India","USA"],"Sales":[3,4]})
    hierarchy=discover_hierarchy(df)
    assert [item["column"] for item in hierarchy] == ["Country"]
    result=run_geo_analysis(df,{"analysis_type":"geographic_analysis","geographic_dimension":"Country","metric":{"column":"Sales","aggregation":"sum"}})
    assert result["success"] and result["map"]["type"] == "choropleth"
    assert all(row["child_count"] == 0 for row in result["results"])


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


def test_admin_boundary_join_uses_parent_context_and_real_feature():
    feature=lambda name,country: {"type":"Feature","properties":{"NAME_1":name,"NAME_0":country},"geometry":{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,0]]]}}
    with tempfile.NamedTemporaryFile(mode="w",suffix=".geojson",encoding="utf-8",delete=False) as f:
        json.dump({"type":"FeatureCollection","features":[feature("Georgia","India"),feature("Georgia","United States of America"),feature("Tamil Nadu","India")]},f)
        path=f.name
    prior=os.environ.get("QUERYLENS_ADMIN_BOUNDARIES_GEOJSON")
    try:
        os.environ["QUERYLENS_ADMIN_BOUNDARIES_GEOJSON"]=path
        resolved, boundaries, missing=GeoResolver().resolve_admin_boundaries(["Georgia"],"administrative_area_level_1",{"Country":"India"})
        assert missing == 0 and len(boundaries) == 1
        assert resolved["Georgia"]["parent_name"] == "India"
        us=GeoBoundaryProvider().resolve_boundary(entity_type="state",name="Georgia",parent_country="USA")
        assert us and us["properties"]["NAME_0"] == "United States of America"
        india=GeoBoundaryProvider().resolve_boundary(entity_type="state",name="Tamil Nadu State",parent_name="India")
        assert india and india["properties"]["querylens_name"] == "Tamil Nadu State"
    finally:
        if prior is None: os.environ.pop("QUERYLENS_ADMIN_BOUNDARIES_GEOJSON",None)
        else: os.environ["QUERYLENS_ADMIN_BOUNDARIES_GEOJSON"]=prior
        os.unlink(path)


def test_bundled_real_admin1_boundaries_resolve_india_and_us():
    df=pd.DataFrame({
        "Country":["India","India","India","USA","USA"],
        "State":["Maharashtra","Tamil Nadu","Karnataka","California","Texas"],
        "Quantity":[34,20,25,40,30],
    })
    for country, states in (("India",{"Maharashtra","Tamil Nadu","Karnataka"}),("USA",{"California","Texas"})):
        outcome=run_geo_analysis(df,{"analysis_type":"geographic_analysis","geography":{"column":"State","parent":{"column":"Country","value":country}},"geographic_dimension":"State","metric":{"column":"Quantity","aggregation":"sum"}})
        assert outcome["success"] and outcome["map"]["boundary_status"]=="available"
        assert {feature["properties"]["querylens_name"] for feature in outcome["map"]["boundaries"]["features"]} == states
        assert all(feature["geometry"]["type"] in ("Polygon","MultiPolygon") for feature in outcome["map"]["boundaries"]["features"])


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
