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


def test_operational_forecast_indicators():
    from kisanai_c2c.domain import operational_forecast_indicators
    evidence = [
        {
            "kind": "weather_forecast",
            "values": [
                {"name": "rainfall_day_1", "value": 12.0},
                {"name": "rainfall_day_2", "value": 18.0},
                {"name": "rainfall_day_3", "value": 5.0},
                {"name": "current_wind_speed", "value": 11.0},
                {"name": "rainfall_today", "value": 0.0},
            ]
        },
        {
            "kind": "satellite_observation",
            "values": [
                {"name": "water_stress", "value": "low"}
            ]
        }
    ]
    indicators = operational_forecast_indicators(evidence, soil_type="black")
    assert indicators["rain_7d_total_mm"] == 35.0
    assert indicators["sowing_readiness"] == "optimal"
    assert indicators["spray_window"] == "safe"


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

