import pytest
from kisanai_c2c.domain import POLICY_VERSION, normalize_crop, rainfall_total, build_options
from kisanai_c2c.models import Farm, Location

def test_policy_version():
    assert POLICY_VERSION == "c2c-regenerative-1.0.0"

def test_normalize_crop():
    assert normalize_crop("Bajra") == "pearl_millet"
    assert normalize_crop("jowar") == "sorghum"
    assert normalize_crop("paddy") == "rice"
    assert normalize_crop("tur") == "pigeon_pea"

def test_crop_plan_requires_season():
    farm = Farm(
        name="Test", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=2, area_ha=2.0, location=Location(latitude=18, longitude=73),
        water_access="rainfed", current_crop=None,
        owner_subject="farmer", node_id="node"
    )
    with pytest.raises(ValueError, match="Season is required for crop planning"):
        build_options(farm, None, goal="crop_plan", season=None, rainfall_7d_mm=None)

def test_rainfed_black_soil_eligible_kharif():
    farm = Farm(
        name="Test", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=2, area_ha=2.0, location=Location(latitude=18, longitude=73),
        water_access="rainfed", soil_type="black", current_crop=None,
        owner_subject="farmer", node_id="node"
    )
    options = build_options(farm, None, goal="crop_plan", season="kharif", rainfall_7d_mm=100.0)
    eligible = [opt.crop for opt in options if opt.eligible]
    assert "pearl_millet" in eligible
    assert "pigeon_pea" in eligible
    
def test_rice_requires_water_access():
    farm = Farm(
        name="Test", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=2, area_ha=2.0, location=Location(latitude=18, longitude=73),
        water_access="rainfed", soil_type="black", current_crop=None,
        owner_subject="farmer", node_id="node"
    )
    options = build_options(farm, None, goal="crop_plan", season="kharif", rainfall_7d_mm=50.0)
    rice_option = next(opt for opt in options if opt.crop == "rice")
    assert not rice_option.eligible
    assert "Water access is below the crop's configured minimum" in rice_option.rejection_reasons

def test_repeating_previous_crop_rotation_rejection():
    farm = Farm(
        name="Test", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=2, area_ha=2.0, location=Location(latitude=18, longitude=73),
        water_access="irrigated", soil_type="black", current_crop=None,
        previous_crop="cotton", owner_subject="farmer", node_id="node"
    )
    options = build_options(farm, None, goal="crop_plan", season="kharif", rainfall_7d_mm=100.0)
    cotton_option = next(opt for opt in options if opt.crop == "cotton")
    assert not cotton_option.eligible
    assert "Repeating the previous crop weakens rotation diversity; expert review required" in cotton_option.rejection_reasons

def test_rainfall_total():
    assert rainfall_total([]) is None
    evidence = [
        {"kind": "satellite_observation"},
        {
            "kind": "weather_forecast",
            "values": [
                {"name": "rainfall_2023-01-01", "value": 10},
                {"name": "rainfall_2023-01-02", "value": 20.5},
                {"name": "temperature", "value": 30}
            ]
        }
    ]
    assert rainfall_total(evidence) == 30.5


def test_new_maharashtra_crops_and_aliases():
    assert normalize_crop("soyabean") == "soybean"
    assert normalize_crop("gahu") == "wheat"
    assert normalize_crop("kanda") == "onion"
    assert normalize_crop("oos") == "sugarcane"
    assert normalize_crop("harbara") == "chickpea"
    
    farm = Farm(
        name="MH Test Farm", state_code="MH", state_name="Maharashtra", district="Yavatmal",
        area_value=3, area_ha=1.2, location=Location(latitude=20.38, longitude=78.12),
        water_access="rainfed", soil_type="black", current_crop=None,
        previous_crop="cotton", owner_subject="farmer", node_id="india-node-mh"
    )
    options = build_options(farm, None, goal="crop_plan", season="kharif", rainfall_7d_mm=45.0)
    eligible = [opt.crop for opt in options if opt.eligible]
    # Soybean is an ideal legume rotation after cotton in rainfed black soil
    assert "soybean" in eligible


def _forecast(days, *, start="2026-10-01", past=None):
    """Weather snapshot in the stored Open-Meteo shape. days: list of (rain, prob, wind, tmax, tmin, et0)."""
    from datetime import date, timedelta
    values = [{"name": "forecast_start_date", "value": start}]
    first = date.fromisoformat(start)
    for offset, rain in enumerate(past or []):
        day = (first - timedelta(days=len(past) - offset)).isoformat()
        values.append({"name": f"rainfall_{day}", "value": rain})
    for offset, (rain, prob, wind, tmax, tmin, et0) in enumerate(days):
        day = (first + timedelta(days=offset)).isoformat()
        values += [
            {"name": f"rainfall_{day}", "value": rain}, {"name": f"rain_probability_{day}", "value": prob},
            {"name": f"wind_max_{day}", "value": wind}, {"name": f"temp_max_{day}", "value": tmax},
            {"name": f"temp_min_{day}", "value": tmin}, {"name": f"et0_{day}", "value": et0},
        ]
    return {"kind": "weather_forecast", "provider": "open_meteo", "fetched_at": "2026-10-01T06:00:00Z", "values": values}


def test_operational_forecast_indicators():
    from kisanai_c2c.domain import operational_forecast_indicators
    week = [(0.0, 5, 9.0, 32.0, 22.0, 4.5)] * 7
    evidence = [_forecast(week, past=[0, 0, 0, 0, 0, 0, 0]), {"kind": "satellite_observation", "values": [{"name": "water_stress", "value": "low"}]}]
    ops = operational_forecast_indicators(evidence, soil_type="black", water_access="rainfed", season="rabi")
    assert ops["has_forecast"] and len(ops["daily"]) == 7
    assert ops["rain_7d_total_mm"] == 0.0
    assert ops["past_7d_rain_mm"] == 0.0
    assert ops["spraying"]["status"] == "safe"
    assert len(ops["spraying"]["best_days"]) == 3
    assert ops["sowing"]["status"] == "ready"  # rabi sowing on stored moisture, mild days
    # 7 x 4.5 mm ET0 x 0.8 = 25.2 mm demand and no rain -> deficit, but no irrigation source.
    assert ops["irrigation"]["status"] == "conserve"
    assert ops["drainage"]["status"] == "low"
    assert ops["temperature"]["status"] == "normal"


def test_operational_heavy_rain_wind_and_heat():
    from kisanai_c2c.domain import operational_forecast_indicators
    week = [(70.0, 90, 30.0, 41.0, 26.0, 3.0)] + [(5.0, 40, 12.0, 33.0, 24.0, 3.0)] * 6
    ops = operational_forecast_indicators([_forecast(week)], soil_type="black", water_access="irrigated", season="kharif", locale="mr-IN")
    assert ops["spraying"]["status"] == "avoid"
    assert ops["drainage"]["status"] == "high"
    assert ops["irrigation"]["status"] == "not_needed"
    assert ops["temperature"]["status"] == "high"
    assert "मिमी" in ops["drainage"]["summary"]


def test_kharif_sowing_uses_past_rain():
    from kisanai_c2c.domain import operational_forecast_indicators
    week = [(5.0, 40, 10.0, 31.0, 23.0, 3.0)] * 7
    wet = operational_forecast_indicators([_forecast(week, past=[15] * 7)], season="kharif")
    dry = operational_forecast_indicators([_forecast(week, past=[0] * 7)], season="kharif")
    assert wet["sowing"]["status"] == "ready"  # 105 + 15 mm
    assert dry["sowing"]["status"] == "wait"   # 15 mm


def test_operational_without_forecast():
    from kisanai_c2c.domain import operational_forecast_indicators
    ops = operational_forecast_indicators([])
    assert ops["has_forecast"] is False
    assert ops["sowing"]["status"] == "unknown"


def test_rainfall_total_uses_only_forecast_days_of_newest_snapshot():
    old = _forecast([(50.0, 90, 5.0, 30.0, 20.0, 3.0)] * 7)
    old["fetched_at"] = "2026-09-20T06:00:00Z"
    new = _forecast([(1.0, 10, 5.0, 30.0, 20.0, 3.0)] * 7, past=[40] * 7)
    assert rainfall_total([old, new]) == 7.0


def test_current_season():
    from datetime import date
    from kisanai_c2c.domain import current_season
    assert current_season(date(2026, 7, 1)) == "kharif"
    assert current_season(date(2026, 10, 1)) == "rabi"
    assert current_season(date(2027, 1, 15)) == "rabi"
    assert current_season(date(2027, 4, 1)) == "summer"


def test_rainfed_cotton_is_eligible_in_kharif_but_wheat_needs_irrigation():
    from kisanai_c2c.domain import generate_crop_recommendations
    farm = Farm(
        name="Rainfed Farm", state_code="MH", state_name="Maharashtra", district="Yavatmal",
        area_value=2, area_ha=0.8, location=Location(latitude=20.38, longitude=78.12),
        water_access="rainfed", soil_type="black", previous_crop="soybean", owner_subject="farmer", node_id="n",
    )
    kharif = generate_crop_recommendations(farm, None, season="kharif", evidence=[], locale="en-IN")
    assert "cotton" in [r.crop for r in kharif.recommendations]
    rabi = generate_crop_recommendations(farm, None, season="rabi", evidence=[_forecast([(0.0, 5, 8.0, 31.0, 20.0, 4.0)] * 7)])
    rabi_crops = [r.crop for r in rabi.recommendations]
    assert "chickpea" in rabi_crops and "sorghum" in rabi_crops
    assert "wheat" not in rabi_crops
    # A dry week is normal for rabi sowing and must not lower the weather score.
    chickpea = next(r for r in rabi.recommendations if r.crop == "chickpea")
    assert next(d for d in chickpea.dimensions if d.name == "weather_forecast").score == 1.0


def test_hot_forecast_lowers_wheat_score():
    from kisanai_c2c.domain import generate_crop_recommendations
    farm = Farm(
        name="Irrigated Farm", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=2, area_ha=0.8, location=Location(latitude=18.5, longitude=73.8),
        water_access="irrigated", soil_type="black", owner_subject="farmer", node_id="n",
    )
    cool = generate_crop_recommendations(farm, None, season="rabi", evidence=[_forecast([(0.0, 5, 8.0, 29.0, 14.0, 4.0)] * 7)])
    hot = generate_crop_recommendations(farm, None, season="rabi", evidence=[_forecast([(0.0, 5, 8.0, 35.0, 22.0, 5.0)] * 7)])
    score = lambda res: next(r.rank_score for r in res.recommendations if r.crop == "wheat")
    assert score(hot) < score(cool)
    weather = next(f for f in next(r for r in hot.recommendations if r.crop == "wheat").factors if f.factor_id == "weather")
    assert weather.status in {"compatible", "constrained"} and weather.remedy


def test_generate_crop_recommendations_factors():
    from kisanai_c2c.domain import generate_crop_recommendations
    farm = Farm(
        name="Vidarbha Farm", state_code="MH", state_name="Maharashtra", district="Yavatmal",
        area_value=2, area_ha=0.8, location=Location(latitude=20.38, longitude=78.12),
        water_access="rainfed", soil_type="black", current_crop=None,
        previous_crop="cotton", owner_subject="farmer", node_id="india-node-mh"
    )
    res_mr = generate_crop_recommendations(farm, None, season="kharif", evidence=[], locale="mr-IN")
    assert res_mr.district == "Yavatmal"
    assert len(res_mr.recommendations) > 0
    top_crops = [r.crop for r in res_mr.recommendations]
    assert "pigeon_pea" in top_crops or "soybean" in top_crops
    pigeon_pea_opt = next(r for r in res_mr.recommendations if r.crop == "pigeon_pea")
    assert len(pigeon_pea_opt.factors) == 7
    season_factor = next(f for f in pigeon_pea_opt.factors if f.factor_id == "season")
    assert "हंगाम" in season_factor.factor_name
    assert season_factor.status in {"optimal", "compatible", "pass"}

