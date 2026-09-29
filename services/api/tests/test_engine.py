from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta

from jsonschema import Draft202012Validator, FormatChecker

from kisanai_c2c.engine import RecommendationEngine, cycle_month_weights, trapezoid
from kisanai_c2c.knowledge import bundled_packs, crop_catalog, crop_name, normalize_crop, window_dates
from kisanai_c2c.models import PackRef, SoilEstimate, SoilTest, SoilValues
from kisanai_c2c.operations import operational_indicators
from kisanai_c2c.settings import PROJECT_ROOT
from kisanai_c2c.soil import rate_values
from tests.conftest import PARANA, VIDARBHA, land_profile, make_farm

TODAY = date(2026, 9, 28)


def _engine(farm, pack_code: str | None = "IN-MH", rows=VIDARBHA, soil_test=None, soil_estimate=None, evidence=None, pack=None):
    pack = pack or (bundled_packs().get(pack_code) if pack_code else None)
    ref = PackRef(pack_id=pack["pack_id"], pack_version=pack["pack_version"], name=pack["region"]["name"],
                  subdivision_code=pack_code, review_status=pack["review"]["status"], origin="bundled") if pack else None
    return RecommendationEngine(farm, pack=pack, pack_ref=ref, land=land_profile(farm, rows, soil_estimate), soil_test=soil_test,
                                evidence=evidence or [], today=TODAY).run()


# --- knowledge ---------------------------------------------------------------------------

def test_normalize_crop_handles_local_names():
    assert normalize_crop("Bajra") == "pearl_millet"
    assert normalize_crop("tur") == "pigeon_pea"
    assert normalize_crop("Harbara") == "chickpea"
    assert normalize_crop("gehu") == "wheat"
    assert normalize_crop("kanda") == "onion"
    assert normalize_crop("moong") == "green_gram"
    assert normalize_crop("हरभरा") == "chickpea"
    assert normalize_crop("Mandioca") == "cassava"


def test_crop_names_are_localized():
    assert crop_name("chickpea", "mr-IN") == "हरभरा"
    assert crop_name("wheat", "kn-IN") == "ಗೋಧಿ"
    assert crop_name("soybean", "pt-BR") == "Soja"


def test_catalog_has_ecocrop_parameters_for_every_crop():
    for crop in crop_catalog().values():
        eco = crop["ecocrop"]
        assert eco["tmin"] is not None and eco["tmax"] is not None, crop["id"]
        assert eco["phmin"] is not None and eco["phmax"] is not None, crop["id"]
        assert crop["cycle_days"] > 0


def test_bundled_packs_match_contract_and_catalog():
    schema = json.loads((PROJECT_ROOT / "contracts" / "agronomy-pack.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    catalog = crop_catalog()
    assert {"IN-MH", "BR-PR"} <= set(bundled_packs())
    for pack in bundled_packs().values():
        assert not list(validator.iter_errors(pack))
        for entry in pack["crops"]:
            assert catalog[entry["crop_id"]]["scientific_name"] == entry["scientific_name"]


def test_window_dates_wrap_across_new_year():
    start, end = window_dates({"start": "11-15", "end": "01-15"}, date(2026, 12, 20))
    assert start == date(2026, 11, 15) and end == date(2027, 1, 15)
    start, _ = window_dates({"start": "06-15", "end": "07-15"}, TODAY)
    assert start == date(2027, 6, 15)


def test_trapezoid_and_cycle_weights():
    assert trapezoid(20, 10, 15, 25, 30) == 1.0
    assert trapezoid(12.5, 10, 15, 25, 30) == 0.5
    assert trapezoid(31, 10, 15, 25, 30) == 0.0
    weights = dict(cycle_month_weights(date(2026, 10, 1), 61))
    assert round(weights[10], 2) == 1.0 and round(weights[11], 2) == 1.0


# --- engine: regional pack ------------------------------------------------------------------

def test_rainfed_vidarbha_late_september_recommends_rabi_on_residual_moisture():
    result = _engine(make_farm())
    assert result.knowledge_mode == "regional_pack"
    now = [o.crop for o in result.sow_now]
    assert "chickpea" in now and "sorghum" in now
    assert "soybean" not in now  # kharif window closed and it was last season's crop
    wheat = next(o for o in result.not_suitable if o.crop == "wheat")
    assert wheat.rejection_codes == ["needs_irrigation"]


def test_repeat_crop_is_never_recommended():
    result = _engine(make_farm(previous_crop="chickpea"))
    chickpea = next(o for o in result.sow_now + result.upcoming + result.not_suitable if o.crop == "chickpea")
    assert not chickpea.eligible and "repeat_crop" in chickpea.rejection_codes


def test_every_factor_declares_its_data_source():
    result = _engine(make_farm())
    for option in result.sow_now:
        assert {f.id for f in option.factors} >= {"sowing_window", "temperature", "water"}
        assert all(f.source for f in option.factors)
        assert 0 <= option.regenerative_score <= 1


def test_estimated_ph_informs_but_measured_ph_can_reject():
    estimate = SoilEstimate(ph=5.0, texture_class="heavy", source="test")
    result = _engine(make_farm(), soil_estimate=estimate)
    assert any(o.crop == "chickpea" for o in result.sow_now)  # estimate alone never rejects
    measured = SoilTest(values=SoilValues(ph=4.4), farm_id="f", owner_subject="o", node_id="n")
    result = _engine(make_farm(), soil_test=measured)
    chickpea = next(o for o in result.not_suitable if o.crop == "chickpea")
    assert "soil_ph" in chickpea.rejection_codes


def test_groundwater_stress_penalises_water_hungry_crops():
    stressed = copy.deepcopy(bundled_packs()["IN-MH"])
    stressed["groundwater"] = {"category": "over_exploited", "scope": "state"}
    farm = make_farm(water_access="irrigated", previous_crop="soybean")
    result = _engine(farm, pack=stressed)
    options = {o.crop: o for o in result.sow_now + result.upcoming + result.not_suitable}
    sugarcane = options["sugarcane"]
    assert any(f.id == "groundwater" and f.status in ("limiting", "blocking") for f in sugarcane.factors)
    assert options["chickpea"].regenerative_score > sugarcane.regenerative_score


def test_parana_pack_follows_the_soybean_sanitary_break():
    farm = make_farm(country_code="BR", state_code="PR", state_name="Paraná", district="Cascavel",
                     location={"latitude": -24.9, "longitude": -53.4}, soil_type="unknown", previous_crop="wheat")
    result = _engine(farm, pack_code="BR-PR", rows=PARANA)
    assert result.knowledge_mode == "regional_pack" and result.context["season_now"] == "safra"
    soybean = next(o for o in result.sow_now if o.crop == "soybean")
    assert soybean.sowing.start >= date(2026, 9, 20)  # statewide legal start after the vazio sanitário
    assert "wheat" not in [o.crop for o in result.sow_now]  # a winter crop, not sown in spring


# --- engine: global baseline (no regional pack) -------------------------------------------------

def test_foreign_location_uses_global_baseline_with_climate_windows():
    farm = make_farm(country_code="BR", state_code="PR", state_name="Parana", district="Cascavel",
                     location={"latitude": -24.9, "longitude": -53.4}, soil_type="unknown", previous_crop="maize")
    result = _engine(farm, pack_code=None, rows=PARANA)
    assert result.knowledge_mode == "global_baseline"
    assert result.notes and "global baseline" in result.notes[0]
    crops = [o.crop for o in result.sow_now]
    assert "soybean" in crops
    assert not any(crop_catalog()[c]["group"] == "green_manure" for c in crops)


# --- soil ------------------------------------------------------------------------------------

def test_soil_health_card_ratings():
    ratings = {r.parameter: r.rating for r in rate_values(SoilValues(ph=8.2, ec_ds_m=0.3, organic_carbon_percent=0.42,
                                                                       nitrogen_kg_ha=210, phosphorus_kg_ha=18, potassium_kg_ha=320,
                                                                       zinc_ppm=0.4, sulphur_ppm=14))}
    assert ratings == {"ph": "alkaline", "ec_ds_m": "normal", "organic_carbon_percent": "low", "nitrogen_kg_ha": "low",
                       "phosphorus_kg_ha": "medium", "potassium_kg_ha": "high", "zinc_ppm": "deficient", "sulphur_ppm": "sufficient"}


# --- field operations ---------------------------------------------------------------------------

def _forecast(daily_rain, hourly_builder):
    start = datetime(2026, 9, 28, 6, 0)
    days = [(start.date() + timedelta(days=i)).isoformat() for i in range(7)]
    hourly = [hourly_builder(start + timedelta(hours=h)) for h in range(168)]
    return [{
        "id": "ev1", "kind": "weather_forecast", "provider": "open_meteo", "mode": "live", "fetched_at": "2026-09-28T00:30:00Z", "values": [],
        "data": {"timezone": "Asia/Kolkata", "current": {"time": start.isoformat()},
                 "daily": [{"date": d, "precipitation_sum": daily_rain[i], "precipitation_probability_max": 80 if daily_rain[i] else 5,
                            "temperature_2m_max": 31, "temperature_2m_min": 21, "et0_fao_evapotranspiration": 4.5,
                            "wind_speed_10m_max": 10, "relative_humidity_2m_mean": 70} for i, d in enumerate(days)],
                 "hourly": hourly},
    }]


def test_spray_window_and_dry_sowing_warning():
    def calm_dry(moment):
        return {"time": moment.isoformat(), "temperature_2m": 27, "relative_humidity_2m": 60, "precipitation": 0,
                "precipitation_probability": 5, "wind_speed_10m": 6, "soil_moisture_3_to_9cm": 0.12}
    ops = operational_indicators(_forecast([0] * 7, calm_dry), texture="heavy", water_access="rainfed", crop_status="planning", current_crop=None)
    assert ops["spray"]["status"] == "good" and ops["spray"]["window"]["start"].startswith("2026-09-28")
    assert ops["sowing"]["status"] == "wait"
    assert ops["irrigation"]["status"] == "deficit"
    assert ops["drainage"]["status"] == "normal"


def test_heavy_rain_blocks_spraying_and_flags_drainage_and_blight():
    def wet(moment):
        return {"time": moment.isoformat(), "temperature_2m": 18, "relative_humidity_2m": 95, "precipitation": 2,
                "precipitation_probability": 90, "wind_speed_10m": 20, "soil_moisture_3_to_9cm": 0.40}
    ops = operational_indicators(_forecast([40, 45, 30, 5, 0, 0, 0], wet), texture="heavy", water_access="irrigated",
                                 crop_status="planted", current_crop="potato")
    assert ops["spray"]["status"] == "avoid"
    assert ops["drainage"]["status"] == "high"
    risks = {r["id"]: r["status"] for r in ops["disease_risks"]}
    assert risks["late_blight"] == "high" and risks["fungal_leaf"] == "high"
    assert ops["sowing"]["status"] == "not_applicable"


def test_operations_without_forecast_are_explicitly_unavailable():
    assert operational_indicators([], texture=None, water_access="rainfed", crop_status="planning", current_crop=None) == {
        "available": False, "message": "No forecast has been fetched yet for this farm."}


def test_nutrient_ratings_only_where_the_country_scheme_is_known():
    values = SoilValues(ph=5.4, nitrogen_kg_ha=150, phosphorus_kg_ha=8)
    assert {r.parameter for r in rate_values(values, "IN")} == {"ph", "nitrogen_kg_ha", "phosphorus_kg_ha"}
    assert {r.parameter for r in rate_values(values, "BR")} == {"ph"}  # Brazilian labs use other units and tables


def test_field_sub_basin_groundwater_overrides_the_state_category():
    farm = make_farm(water_access="irrigated", previous_crop="soybean")
    land = land_profile(farm, VIDARBHA)
    land.water_risk = {"groundwater_category": "over_exploited", "groundwater_decline_cm_per_year": 12.9, "water_stress_category": 4}
    result = RecommendationEngine(farm, pack=bundled_packs()["IN-MH"], pack_ref=None, land=land, soil_test=None, evidence=[], today=TODAY).run()
    assert result.context["groundwater_category"] == "over_exploited" and result.context["groundwater_scope"] == "basin"
    sugarcane = next(o for o in result.sow_now + result.upcoming + result.not_suitable if o.crop == "sugarcane")
    assert any(f.id == "groundwater" and f.source == "estimated" for f in sugarcane.factors)
