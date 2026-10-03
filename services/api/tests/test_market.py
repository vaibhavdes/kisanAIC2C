from datetime import date

import pytest

from kisanai_c2c import market as m
from kisanai_c2c.models import Actor, CropPlanCreate, FarmCreate, Location, Role, SimulationRequest
from kisanai_c2c.providers.market_live import MarketLive
from kisanai_c2c.service import AppService

from .test_service_integration import MemoryMediaStore, MemoryStore


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(MarketLive, "recent", lambda self, district, crop, days=45: None)
    monkeypatch.setattr("kisanai_c2c.providers.geo.taluka_for", lambda lat, lon, store=None: None)


@pytest.fixture
def service():
    return AppService(store=MemoryStore(), media_store=MemoryMediaStore())


@pytest.fixture
def farmer():
    return Actor(subject="farmer1", node_id="node1", roles={Role.farmer})


def make_farm(service, farmer, district="Pune", taluka="Baramati"):
    return service.create_farm(farmer, FarmCreate(
        name="Test field", state_code="MH", state_name="Maharashtra", district=district, taluka=taluka,
        area_value=2, area_unit="hectare", location=Location(latitude=18.15, longitude=74.58),
        water_access="supplemental_irrigation", soil_type="black",
    ))


def test_harvest_window_crosses_year():
    assert m.harvest_months("cotton", "kharif", 2025) == [(2025, 11), (2025, 12), (2026, 1)]
    assert m.harvest_months("chickpea", "rabi", 2025) == [(2026, 2), (2026, 3), (2026, 4)]


def test_next_sowing_year():
    assert m.next_sowing_year("rabi", "wheat", date(2026, 10, 3)) == 2026
    assert m.next_sowing_year("kharif", "soybean", date(2026, 10, 3)) == 2027


def test_past_prices_are_completed_seasons_only():
    past = m.past_harvest_prices("Pune", "soybean", "kharif", 3, date(2026, 10, 3))
    assert past and all(p["sow_year"] <= 2025 for p in past)
    assert past[0]["price"] > 1000


def test_crowding_raises_supply_and_lowers_price():
    plans = [{"crop": "onion", "taluka": "Baramati"} for _ in range(20)] + [{"crop": "wheat", "taluka": "Baramati"} for _ in range(5)]
    crowd = m.crowding("Pune", "onion", "rabi", plans, "Baramati")
    assert crowd["level"] == "high" and crowd["taluka_same_crop"] == 20
    calm = m.price_forecast("Pune", "onion", "rabi", 3, 0.0)
    crowded = m.price_forecast("Pune", "onion", "rabi", 3, crowd["supply_shift"])
    assert crowded["expected"] < calm["expected"]


def test_simulation_is_reproducible_and_ordered():
    price = m.price_forecast("Ahilyanagar", "soybean", "kharif", 3, 0.0)
    yld = m.yield_model("Ahilyanagar", "soybean", "kharif", "rainfed", 1.0, None)
    a = m.Assumptions(area_ha=2.0)
    first, second = m.simulate(price, yld, m.cost_per_ha("soybean"), a), m.simulate(price, yld, m.cost_per_ha("soybean"), a)
    assert first == second
    p = first["profit_rs"]
    assert p["p10"] <= p["p50"] <= p["p90"]
    assert 0 <= first["loss_probability"] <= 1


def test_msp_floor_never_pays_below_msp():
    price = m.price_forecast("Pune", "chickpea", "rabi", 3, 0.0)
    yld = m.yield_model("Pune", "chickpea", "rabi", "irrigated", 1.0, None)
    result = m.simulate(price, yld, m.cost_per_ha("chickpea"), m.Assumptions(area_ha=1, use_msp_floor=True))
    assert result["price_rs_qtl"]["p10"] >= price["msp"]


def test_cotton_yield_is_kapas():
    lint = m.apy()[("pune", "cotton", "kharif")]
    model = m.yield_model("Pune", "cotton", "kharif", "supplemental_irrigation", None, None)
    import statistics
    assert model["district_kg_ha"] > 2 * statistics.median(v[1] for v in lint.values())


def test_recommendations_include_economics_in_market_district(service, farmer):
    farm = make_farm(service, farmer)
    result = service.crop_recommendations(farmer, farm.id, season="rabi")
    assert result.market_covered
    priced = [o for o in result.recommendations if o.economics]
    assert priced and all(any(f.factor_id == "market" for f in o.factors) for o in priced)
    scores = [o.rank_score for o in result.recommendations]
    assert scores == sorted(scores, reverse=True)


def test_no_economics_outside_market_districts(service, farmer):
    farm = make_farm(service, farmer, district="Yavatmal", taluka=None)
    result = service.crop_recommendations(farmer, farm.id, season="kharif")
    assert not result.market_covered
    assert all(o.economics is None for o in result.recommendations)
    assert service.market_outlook(farmer, farm.id, "soybean", "kharif")["reason"] == "not_covered"


def test_crop_plans_feed_regional_mix(service, farmer):
    farm = make_farm(service, farmer)
    service.save_crop_plan(farmer, farm.id, CropPlanCreate(crop="harbara", season="rabi"))
    mix = service.regional_mix(farmer, farm.id, "rabi")
    assert mix["district_counts"] == {"chickpea": 1}
    assert mix["taluka_counts"] == {}  # hidden below three farms
    assert mix["my_plan"]["crop"] == "chickpea"


def test_simulate_endpoint_overrides(service, farmer):
    farm = make_farm(service, farmer)
    out = service.market_simulate(farmer, farm.id, SimulationRequest(crop="wheat", season="rabi", price_override=3000, cost_per_ha_override=40000, area_ha=1))
    sim = out["simulation"]
    assert sim["price_rs_qtl"]["p50"] == 3000 and sim["cost_rs"] == 40000


def test_clean_taluka_maps_pune_city_edge_to_haveli():
    from kisanai_c2c.providers.geo import clean_taluka
    assert clean_taluka("Pune City Subdistrict") == "Haveli"
    assert clean_taluka("Baramati Taluka") == "Baramati"


def test_http_cache_serves_cached_and_stale(monkeypatch):
    from kisanai_c2c.providers import http_cache
    calls = []

    class Resp:
        status_code = 200
        headers = {}
        def raise_for_status(self): pass
        def json(self): return {"ok": len(calls)}

    def fake(method, url, **kw):
        calls.append(url)
        return Resp()
    monkeypatch.setattr(http_cache.requests, "request", fake)
    store = MemoryStore()
    url = "https://example.test/a"
    first = http_cache.fetch_json(url, params={"q": 1}, store=store, ttl=60)
    second = http_cache.fetch_json(url, params={"q": 1}, store=store, ttl=60)
    assert first == second and len(calls) == 1
    http_cache._memory.clear()
    assert http_cache.fetch_json(url, params={"q": 1}, store=store, ttl=60) == first and len(calls) == 1  # from the store


def test_tomato_and_potato_are_ranked():
    from kisanai_c2c.domain import CROP_POLICIES, normalize_crop
    assert {"tomato", "potato"} <= {p.crop for p in CROP_POLICIES}
    assert normalize_crop("batata") == "potato"
