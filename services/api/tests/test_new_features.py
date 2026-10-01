from kisanai_c2c.models import Farm, Location, SoilTest, SoilValues
from kisanai_c2c.weather_ops import available_water, disease_hours_by_day, hourly_series, spray_windows


def _hour(time, wind=5.0, prob=0, rain=0.0, temp=26.0, humidity=60):
    return {"time": time, "wind": wind, "rain_prob": prob, "rain": rain, "temp": temp, "humidity": humidity}


def test_hourly_series_does_not_confuse_rain_and_rain_prob():
    snapshot = {"values": [
        {"name": "hourly_rain_2026-10-01T06:00", "value": 0.2},
        {"name": "hourly_rain_prob_2026-10-01T06:00", "value": 40},
        {"name": "hourly_soil_moisture_root_2026-10-01T06:00", "value": 0.33},
    ]}
    assert hourly_series(snapshot) == [{"time": "2026-10-01T06:00", "rain": 0.2, "rain_prob": 40, "soil_moisture_root": 0.33}]


def test_spray_windows_need_daylight_calm_and_dry_hours_after():
    hours = [_hour(f"2026-10-01T{h:02d}:00") for h in range(4, 20)]
    hours[6]["wind"] = 20.0  # 10:00 too windy -> splits the morning
    hours[12]["rain"] = 1.0  # 16:00 rain -> 14:00 and 15:00 are not rain-fast
    windows = spray_windows(hours)
    assert windows[0] == {"date": "2026-10-01", "start": "06:00", "end": "10:00"}
    assert windows[1] == {"date": "2026-10-01", "start": "11:00", "end": "14:00"}


def test_disease_hours_count_humid_mild_hours_only():
    hours = [_hour(f"2026-10-01T{h:02d}:00", humidity=95) for h in range(12)] + [_hour("2026-10-01T13:00", humidity=95, temp=35)]
    assert disease_hours_by_day(hours) == {"2026-10-01": 12}


def test_available_water_uses_soil_type_limits():
    assert available_water(0.33, "black") == 0.5
    assert available_water(0.10, "black") == 0.0
    assert available_water(None, "black") is None


def _farm(**overrides):
    values = dict(name="F", state_code="MH", state_name="Maharashtra", district="Yavatmal", area_value=1, area_unit="hectare",
                  area_ha=1.0, location=Location(latitude=20.4, longitude=78.1), water_access="rainfed", soil_type="black",
                  owner_subject="a", node_id="n")
    return Farm(**(values | overrides))


def test_fertilizer_plan_uses_soil_test_ratings_and_products():
    from kisanai_c2c.fertilizer import fertilizer_plan
    soil = SoilTest(farm_id="x", owner_subject="a", node_id="n", confirmed=True, source="manual",
                    values=SoilValues(nitrogen_kg_ha=600, phosphorus_kg_ha=8, potassium_kg_ha=200))
    plan = fertilizer_plan(_farm(), soil, "maize", "kharif")
    assert plan["adjusted_dose_kg_ha"] == {"n": 90.0, "p2o5": 75.0, "k2o": 40.0}  # high N -25 %, low P +25 %
    assert plan["soil"]["nitrogen_kg_ha"] == {"value": 600, "source": "soil_test", "rating": "high"}
    total = plan["products_total"]
    assert round(total["dap_kg"]) == 163 and round(total["mop_kg"]) == 67
    assert len(plan["applications"]) == 2  # cereal: nitrogen split


def test_fertilizer_plan_falls_back_to_labelled_district_baseline():
    from kisanai_c2c.fertilizer import fertilizer_plan
    plan = fertilizer_plan(_farm(), None, "soybean", "kharif")
    assert plan["soil_source"] == "district_baseline"
    assert plan["soil"]["nitrogen_kg_ha"]["source"] == "district_baseline"
    assert plan["legume"] and len(plan["applications"]) == 1


def test_satellite_zones_are_measured_areas():
    from kisanai_c2c.providers.satellite import SatelliteProvider
    stats = {
        "area": {"groups": [{"zone": 2, "sum": 3000.0}, {"zone": 3, "sum": 1046.8564224}]},
        "mean": {"groups": [{"zone": 2, "mean": 0.41}, {"zone": 3, "mean": 0.55}]},
    }
    zones = SatelliteProvider._zones("NDVI", stats)
    assert [z.label for z in zones] == ["Moderate crop cover", "Healthy crop"]
    assert zones[0].area_acres == 0.74 and zones[1].area_acres == 0.26
    assert zones[0].percentage == 74.1


def test_satellite_plain_explanation_matches_measured_areas():
    from kisanai_c2c.models import SatelliteZone
    from kisanai_c2c.satellite_explain import explain_map, simple_label
    zones = [
        SatelliteZone(id=2, color="#fdae61", label="", min_val=0.2, max_val=0.35, median_val=0.27, area_acres=1.5, percentage=30.0),
        SatelliteZone(id=4, color="#a6d96a", label="", min_val=0.5, max_val=0.65, median_val=0.57, area_acres=3.5, percentage=70.0),
    ]
    text = explain_map("NDVI", zones, "27 Sep 2026", True, "en-IN")
    assert "70% of the area (3.5 acres) has good green crop" in text
    assert "30% (1.5 acres) has weak crop" in text
    assert "125 m" not in text
    assert "मिमी" not in explain_map("NDMI", zones, None, False, "mr-IN") and "125" in explain_map("NDMI", zones, None, False, "mr-IN")
    assert simple_label("NDVI", 1, "hi-IN") == "कमज़ोर फसल"


def test_water_stress_follows_leaf_water_not_ndwi():
    from kisanai_c2c.providers.satellite import SatelliteProvider
    stress = SatelliteProvider._water_stress
    assert stress(0.48, -0.45, 0.13) == "low"       # green crop, moist leaves, typical negative NDWI
    assert stress(0.40, -0.40, -0.02) == "medium"
    assert stress(0.47, -0.40, 0.09) == "low"         # NDMI 0.09 is the "some water" zone
    assert stress(0.35, -0.30, -0.20) == "high"
    assert stress(0.10, -0.10, -0.20) == "unknown"   # bare soil


def test_satellite_status_breaks_match_map_zones():
    from kisanai_c2c.providers.satellite import SatelliteProvider as S
    assert [S._vegetation_status(v) for v in (0.3, 0.47, 0.55)] == ["poor", "moderate", "healthy"]
    assert [S._moisture_status(v) for v in (-0.2, 0.0, 0.09, 0.4)] == ["very_dry", "dry", "adequate", "moist"]


def test_recommended_dose_picks_season_and_irrigation():
    from kisanai_c2c.fertilizer import DOSE_SOURCES, RECOMMENDED_DOSE, recommended_dose
    assert recommended_dose("sorghum", "rabi", "rainfed") == (50, 25, 0)
    assert recommended_dose("sorghum", "rabi", "irrigated") == (80, 40, 40)
    assert recommended_dose("cotton", "kharif", "rainfed") == (80, 40, 40)
    assert recommended_dose("cotton", "kharif", "irrigated") == (100, 50, 50)
    assert set(DOSE_SOURCES) == set(RECOMMENDED_DOSE)


def test_firestore_encoding_round_trips_nested_lists():
    from kisanai_c2c.store import _from_firestore, _to_firestore
    farm = {"boundary_coordinates": [[20.41, 78.13], [20.42, 78.14]], "tags": ["a"], "nested": {"m": [[1, [2]]]}}
    encoded = _to_firestore(farm)
    assert all(not isinstance(item, list) for item in encoded["boundary_coordinates"])
    assert _from_firestore(encoded) == farm
