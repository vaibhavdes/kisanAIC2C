import pytest
from typing import Any

from kisanai_c2c.service import AppService
from kisanai_c2c.models import Actor, FarmCreate, Location, SoilTestCreate, SoilValues, Role

class MemoryStore:
    def __init__(self):
        self.data: dict[str, dict[str, dict[str, Any]]] = {}

    def put(self, collection: str, document_id: str, value: dict[str, Any]) -> dict[str, Any]:
        if collection not in self.data:
            self.data[collection] = {}
        self.data[collection][document_id] = value
        return value

    def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        return self.data.get(collection, {}).get(document_id)

    def list(self, collection: str, *, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        items = list(self.data.get(collection, {}).values())
        if filters:
            items = [item for item in items if all(item.get(k) == v for k, v in filters.items())]
        return items[:limit]

    def delete(self, collection: str, document_id: str) -> bool:
        if collection in self.data and document_id in self.data[collection]:
            del self.data[collection][document_id]
            return True
        return False

class MemoryMediaStore:
    def __init__(self):
        self.media: dict[str, bytes] = {}
        self.count = 0

    def save(self, content: bytes, content_type: str, folder: str = "uploads") -> tuple[str, str]:
        self.count += 1
        uri = f"memory://{folder}/{self.count}"
        self.media[uri] = content
        return uri, uri

    def read(self, storage_uri: str) -> bytes:
        return self.media[storage_uri]

    def delete(self, storage_uri: str) -> None:
        self.media.pop(storage_uri, None)

@pytest.fixture
def service():
    return AppService(store=MemoryStore(), media_store=MemoryMediaStore())

@pytest.fixture
def farmer():
    return Actor(subject="farmer1", node_id="node1", roles={Role.farmer})

@pytest.fixture
def other_farmer():
    return Actor(subject="farmer2", node_id="node1", roles={Role.farmer})
    
@pytest.fixture
def expert():
    return Actor(subject="expert1", node_id="node1", roles={Role.expert})

def test_create_and_list_farm(service: AppService, farmer: Actor):
    payload = FarmCreate(
        name="My Farm", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=5, location=Location(latitude=18, longitude=73),
        water_access="rainfed"
    )
    farm = service.create_farm(farmer, payload)
    assert farm.name == "My Farm"
    assert farm.owner_subject == farmer.subject

    farms = service.farms(farmer)
    assert len(farms) == 1
    assert farms[0].id == farm.id

def test_farm_ownership_enforced(service: AppService, farmer: Actor, other_farmer: Actor):
    payload = FarmCreate(
        name="My Farm", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=5, location=Location(latitude=18, longitude=73),
        water_access="rainfed"
    )
    farm = service.create_farm(farmer, payload)
    
    with pytest.raises(PermissionError, match="Farm access denied"):
        service.farm(other_farmer, farm.id)

def test_unconfirmed_soil_test_rejected(service: AppService, farmer: Actor):
    payload = FarmCreate(
        name="My Farm", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=5, location=Location(latitude=18, longitude=73),
        water_access="rainfed"
    )
    farm = service.create_farm(farmer, payload)
    
    soil_payload = SoilTestCreate(
        values=SoilValues(ph=7.0),
        confirmed=False
    )
    with pytest.raises(ValueError, match="Only farmer-confirmed soil values can be saved"):
        service.save_soil_test(farmer, farm.id, soil_payload)

def test_farm_self_healing_and_id_preservation(service: AppService, farmer: Actor):
    # Test 1: Payload with custom id preserves that exact ID
    custom_id = "farm_9d07ee79316f4cf3a320dfaa50834fbe"
    payload = FarmCreate(
        id=custom_id,
        name="Custom Saved Farm", state_code="MH", state_name="Maharashtra", district="Yavatmal",
        area_value=3, location=Location(latitude=20.4, longitude=78.5),
        water_access="supplemental_irrigation"
    )
    farm = service.create_farm(farmer, payload)
    assert farm.id == custom_id

    # Test 2: Looking up this farm succeeds
    fetched = service.farm(farmer, custom_id)
    assert fetched.id == custom_id
    assert fetched.district == "Yavatmal"

    # Test 3: An unknown farm id is not found; it must never be filled with another farm's data.
    with pytest.raises(LookupError):
        service.farm(farmer, "farm_session_cold_start_abc123")


def test_store_filters_apply_before_limit(service: AppService, farmer: Actor):
    for index in range(5):
        service.store.put("soil_tests", f"soil_{index}", {"id": f"soil_{index}", "farm_id": "farm_a" if index == 0 else "farm_b", "created_at": f"2026-01-0{index + 1}T00:00:00Z"})
    rows = service.store.list("soil_tests", filters={"farm_id": "farm_a"}, limit=1)
    assert [row["id"] for row in rows] == ["soil_0"]


def test_lookup_pincode_success():
    from kisanai_c2c.main import lookup_pincode
    # Offline or online, lookup_pincode must return valid coordinates, district, and post_offices list
    res = lookup_pincode("412207")
    assert res["pincode"] == "412207"
    assert "district" in res
    assert "latitude" in res and res["latitude"] is not None
    assert "longitude" in res and res["longitude"] is not None
    assert "post_offices" in res
    assert len(res["post_offices"]) >= 1
    assert "name" in res["post_offices"][0]


def test_lookup_pincode_invalid_format():
    import pytest
    from fastapi import HTTPException
    from kisanai_c2c.main import lookup_pincode

    with pytest.raises(HTTPException) as excinfo:
        lookup_pincode("123")
    assert excinfo.value.status_code == 400

    with pytest.raises(HTTPException) as excinfo:
        lookup_pincode("41220A")
    assert excinfo.value.status_code == 400


def test_farm_chat_and_cleanup(service: AppService, farmer: Actor):
    from kisanai_c2c.main import farm_chat, end_farm_chat, _CHAT_SESSIONS
    from kisanai_c2c.models import FarmChatRequest, FarmCreate, Location

    farm = service.create_farm(farmer, FarmCreate(
        name="Chat Test Farm", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=2, location=Location(latitude=18.5, longitude=73.8),
        water_access="rainfed", soil_type="black"
    ))

    # Send first question in Marathi
    req = FarmChatRequest(message="उद्या पाऊस येईल का आणि फवारणी करू का?", locale="mr-IN")
    res = farm_chat(farm.id, req, actor=farmer, svc=service)
    assert res.session_id is not None
    assert len(res.response) > 0
    assert res.expires_in_seconds == 300
    assert res.session_id in _CHAT_SESSIONS

    # Send follow-up in same session
    req2 = FarmChatRequest(message="खताचे प्रमाण किती द्यावे?", locale="mr-IN", session_id=res.session_id)
    res2 = farm_chat(farm.id, req2, actor=farmer, svc=service)
    assert res2.session_id == res.session_id
    assert len(_CHAT_SESSIONS[res.session_id]["history"]) == 4

    # End chat and verify immediate purge
    clean_res = end_farm_chat(farm.id, res.session_id)
    assert clean_res["cleaned_up"] is True
    assert res.session_id not in _CHAT_SESSIONS


def test_location_source_normalization():
    from kisanai_c2c.models import Location
    # Normal values
    loc1 = Location(latitude=18.5, longitude=73.8, source="device")
    assert loc1.source == "device"

    # polygon_plot gracefully normalizes to farmer
    loc2 = Location(latitude=18.5, longitude=73.8, source="polygon_plot")
    assert loc2.source == "farmer"

    # unknown strings gracefully normalize to farmer
    loc3 = Location(latitude=18.5, longitude=73.8, source="random_source")
    assert loc3.source == "farmer"


def test_create_advisory_contract(service: AppService, farmer: Actor):
    from kisanai_c2c.models import AdvisoryRequest, FarmCreate, Location, EvidenceSnapshot, EvidenceValue

    farm = service.create_farm(farmer, FarmCreate(
        name="Advisory Test Farm", state_code="MH", state_name="Maharashtra", district="Yavatmal",
        area_value=3, location=Location(latitude=20.38, longitude=78.12),
        water_access="rainfed", soil_type="black"
    ))

    # Pre-seed offline evidence snapshot so no external HTTP calls are triggered
    snap = EvidenceSnapshot(
        farm_id=farm.id,
        node_id=farmer.node_id,
        provider="imd",
        kind="weather_forecast",
        mode="cached",
        spatial_scope="district",
        source_reference="IMD Pune District Bulletin",
        values=[EvidenceValue(name="rainfall_7d_total_mm", value=35.0, unit="mm")],
    )
    service.store.put("evidence", snap.id, snap.model_dump(mode="json"))

    adv = service.create_advisory(farmer, farm.id, AdvisoryRequest(
        goal="crop_plan", season="kharif", locale="en-IN", budget_level="low", labor_access="family"
    ))
    assert adv.id.startswith("advisory_")
    assert adv.farm_id == farm.id
    assert len(adv.options) > 0
    assert len(adv.actions) > 0
    assert adv.prompt_version is not None
    assert adv.policy_version is not None
    assert isinstance(adv.evidence_ids, list)


def test_reverse_geocode_endpoint():
    from kisanai_c2c.main import reverse_geocode
    res = reverse_geocode(latitude=18.5204, longitude=73.8567)
    assert res["district"] == "Pune"
    assert res["state_name"] == "Maharashtra"
    assert res["state_code"] == "MH"


def test_ip_geocode_private_address_is_not_invented():
    from fastapi import HTTPException
    from starlette.requests import Request
    from kisanai_c2c.main import ip_geocode
    scope = {"type": "http", "headers": [(b"x-forwarded-for", b"127.0.0.1")]}
    with pytest.raises(HTTPException) as error:
        ip_geocode(Request(scope))
    assert error.value.status_code == 404


def test_latest_soil_and_partial_values(service, farmer):
    farm = service.create_farm(farmer, FarmCreate(
        name="Soil Test Farm",
        state_code="MH",
        state_name="Maharashtra",
        district="Pune",
        water_access="rainfed",
        soil_type="black",
        area_value=2.0,
        area_unit="acre",
        location=Location(latitude=18.5204, longitude=73.8567),
    ))
    
    # Check no soil initially
    assert service.latest_soil(farm.id) is None

    # Submit partial soil test (only pH and N provided; P, K, OC are None)
    soil = service.save_soil_test(farmer, farm.id, SoilTestCreate(
        values=SoilValues(ph=6.8, nitrogen_kg_ha=220.0),
        source="manual",
        confirmed=True,
    ))
    assert soil.values.ph == 6.8
    assert soil.values.nitrogen_kg_ha == 220.0
    assert soil.values.organic_carbon_percent is None
    assert soil.values.phosphorus_kg_ha is None

    # Retrieve via latest_soil
    fetched = service.latest_soil(farm.id)
    assert fetched is not None
    assert fetched.id == soil.id
    assert fetched.values.ph == 6.8


def test_ip_linked_farm_ownership_and_deletion(service: AppService, farmer: Actor):
    payload = FarmCreate(
        name="IP Test Farm", state_code="MH", state_name="Maharashtra", district="Solapur",
        area_value=3, location=Location(latitude=17.65, longitude=75.9),
        water_access="rainfed"
    )
    creator_ip = "192.168.1.10"
    other_ip = "203.0.113.50"

    # 1. Create farm with creator_ip
    farm = service.create_farm(farmer, payload, client_ip=creator_ip)
    assert farm.creator_ip is None  # never sent to the browser
    assert service.store.get("farms", farm.id)["creator_ip"] == creator_ip
    assert farm.is_mine is True

    # 2. List farms as the creator IP -> is_mine should be True
    creator_farms = service.farms(farmer, client_ip=creator_ip)
    matched_creator = next(f for f in creator_farms if f.id == farm.id)
    assert matched_creator.is_mine is True

    # 3. List farms as other IP -> farm should still be visible ("visible to everyone like currently"), but is_mine False
    other_farms = service.farms(farmer, client_ip=other_ip)
    matched_other = next(f for f in other_farms if f.id == farm.id)
    assert matched_other.is_mine is False

    # 4. Attempt to delete by non-creator IP -> raises PermissionError
    with pytest.raises(PermissionError, match="Only the creator of this farm can delete it"):
        service.delete_farm(farmer, farm.id, client_ip=other_ip)

    # 5. Creator deletes farm -> succeeds
    deleted = service.delete_farm(farmer, farm.id, client_ip=creator_ip)
    assert deleted is True

    # 6. Verify farm is gone
    remaining = service.farms(farmer, client_ip=creator_ip)
    assert not any(f.id == farm.id for f in remaining)


def test_soil_date_flexible_parsing(service: AppService, farmer: Actor):
    from datetime import date
    from kisanai_c2c.models import SoilExtraction, SoilValues, SoilTestCreate

    # 1. Indian format DD-MM-YYYY (the exact issue reported: '25-06-2015')
    ext_dash = SoilExtraction(
        values=SoilValues(ph=7.4, nitrogen_kg_ha=240.0),
        sample_date="25-06-2015",
        source="gemini_api",
        model="gemini-2.5-flash",
    )
    assert ext_dash.sample_date == date(2015, 6, 25)

    # 2. Indian slash format DD/MM/YYYY
    ext_slash = SoilExtraction(
        values=SoilValues(ph=7.4),
        sample_date="25/06/2015",
        source="gemini_api",
        model="gemini-2.5-flash",
    )
    assert ext_slash.sample_date == date(2015, 6, 25)

    # 3. Standard ISO format YYYY-MM-DD
    ext_iso = SoilExtraction(
        values=SoilValues(ph=7.4),
        sample_date="2015-06-25",
        source="gemini_api",
        model="gemini-2.5-flash",
    )
    assert ext_iso.sample_date == date(2015, 6, 25)

    # 4. Textual format
    ext_text = SoilExtraction(
        values=SoilValues(ph=7.4),
        sample_date="25 June 2015",
        source="gemini_api",
        model="gemini-2.5-flash",
    )
    assert ext_text.sample_date == date(2015, 6, 25)

    # 5. Unparseable OCR text gracefully falls back to None instead of crashing
    ext_unparseable = SoilExtraction(
        values=SoilValues(ph=7.4),
        sample_date="illegible handwritten stamp",
        source="gemini_api",
        model="gemini-2.5-flash",
    )
    assert ext_unparseable.sample_date is None

    # 6. Manual SoilTestCreate with DD-MM-YYYY
    farm = service.create_farm(farmer, FarmCreate(
        name="Date Test Farm", state_code="MH", state_name="Maharashtra", district="Pune",
        soil_type="black", water_access="rainfed", area_value=2, location=Location(latitude=18.5, longitude=73.8),
    ))
    saved_soil = service.save_soil_test(farmer, farm.id, SoilTestCreate(
        values=SoilValues(ph=7.1, nitrogen_kg_ha=260.0),
        sample_date="25-06-2015",
        source="manual",
        confirmed=True,
    ))
    assert saved_soil.sample_date == date(2015, 6, 25)
    fetched = service.latest_soil(farm.id)
    assert fetched.sample_date == date(2015, 6, 25)








def test_device_id_owns_farm_and_is_not_exposed(service: AppService, farmer: Actor):
    payload = FarmCreate(
        name="Phone Farm", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=1, location=Location(latitude=18.5, longitude=73.8), water_access="rainfed",
    )
    farm = service.create_farm(farmer, payload, client_ip="10.0.0.1", device_id="device-aaaa1111")
    # Same phone on a new network still owns the farm; another phone does not.
    mine = {f.id: f for f in service.farms(farmer, client_ip="10.9.9.9", device_id="device-aaaa1111")}
    other = {f.id: f for f in service.farms(farmer, client_ip="10.0.0.1", device_id="device-bbbb2222")}
    assert mine[farm.id].is_mine and not other[farm.id].is_mine
    assert mine[farm.id].creator_device is None and mine[farm.id].creator_ip is None
    with pytest.raises(PermissionError):
        service.delete_farm(farmer, farm.id, client_ip="10.0.0.1", device_id="device-bbbb2222")
    service.store.put("soil_tests", "soil_x", {"id": "soil_x", "farm_id": farm.id})
    assert service.delete_farm(farmer, farm.id, client_ip="10.9.9.9", device_id="device-aaaa1111")
    assert service.store.get("soil_tests", "soil_x") is None


def test_editing_farm_location_clears_old_readings(service: AppService, farmer: Actor):
    payload = FarmCreate(
        name="Edit Farm", state_code="MH", state_name="Maharashtra", district="Pune",
        area_value=1, location=Location(latitude=18.5, longitude=73.8), water_access="rainfed",
    )
    farm = service.create_farm(farmer, payload, client_ip="10.0.0.1", device_id="device-cccc3333")
    service.store.put("evidence", "ev1", {"id": "ev1", "farm_id": farm.id})
    renamed = service.update_farm(farmer, farm.id, payload.model_copy(update={"name": "Renamed"}), 1, device_id="device-cccc3333")
    assert renamed.name == "Renamed" and service.store.get("evidence", "ev1") is not None
    moved = payload.model_copy(update={"boundary_coordinates": [[18.5, 73.8], [18.501, 73.8], [18.501, 73.801]]})
    service.update_farm(farmer, farm.id, moved, 2, device_id="device-cccc3333")
    assert service.store.get("evidence", "ev1") is None


def _live_map(farm_id: str):
    from kisanai_c2c.models import SatelliteMapResult
    return SatelliteMapResult(farm_id=farm_id, index="NDVI", meaning="m", map_url="https://ee/thumb", start_date="2026-09-01",
                              end_date="2026-10-01", source="earth_engine_sentinel_2", legend={}, data_mode="live", scene_date="28 Sep 2026")


def test_satellite_map_is_stored_reused_and_removed_with_the_farm(service: AppService, farmer: Actor, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from kisanai_c2c.providers.satellite import SatelliteProvider
    calls = []
    monkeypatch.setattr(SatelliteProvider, "satellite_map", lambda self, farm, index="NDVI", days=30: calls.append(farm.id) or _live_map(farm.id))
    monkeypatch.setattr(SatelliteProvider, "download_image", staticmethod(lambda url: b"PNG" * 50))
    payload = FarmCreate(name="Sat Farm", state_code="MH", state_name="Maharashtra", district="Yavatmal",
                         area_value=2, location=Location(latitude=20.1, longitude=78.3), water_access="rainfed")
    farm = service.create_farm(farmer, payload)

    first = service.satellite_map(farmer, farm.id)
    assert first.map_url is None  # the expiring Earth Engine link is never stored or sent
    assert service.satellite_image(farmer, farm.id) == b"PNG" * 50
    service.satellite_map(farmer, farm.id)
    assert len(calls) == 1  # map, image and repeat visit: one Earth Engine query

    doc = service.store.get("satellite_maps", f"{farm.id}_NDVI_30")
    doc["fetched_at"] = (datetime.now(UTC) - timedelta(days=1, minutes=1)).isoformat()
    old_image = doc["image_uri"]
    service.satellite_map(farmer, farm.id)
    assert len(calls) == 2 and old_image not in service.media_store.media  # expired after a day, old PNG replaced

    service.delete_farm(farmer, farm.id)
    assert service.store.list("satellite_maps", filters={"farm_id": farm.id}) == []
    assert not [uri for uri in service.media_store.media if "satellite" in uri]


def test_failed_satellite_map_is_not_stored(service: AppService, farmer: Actor, monkeypatch):
    from kisanai_c2c.providers.satellite import SatelliteProvider
    missing = _live_map("x").model_copy(update={"data_mode": "missing", "map_url": None})
    monkeypatch.setattr(SatelliteProvider, "satellite_map", lambda self, farm, index="NDVI", days=30: missing)
    payload = FarmCreate(name="Cloudy", state_code="MH", state_name="Maharashtra", district="Pune",
                         area_value=1, location=Location(latitude=18.5, longitude=73.8), water_access="rainfed")
    farm = service.create_farm(farmer, payload)
    assert service.satellite_map(farmer, farm.id).data_mode == "missing"
    assert service.store.get("satellite_maps", f"{farm.id}_NDVI_30") is None


def test_refresh_keeps_one_reading_per_source_and_keeps_good_one_on_failure(service: AppService, farmer: Actor):
    from kisanai_c2c.models import EvidenceSnapshot
    payload = FarmCreate(name="Ev", state_code="MH", state_name="Maharashtra", district="Pune",
                         area_value=1, location=Location(latitude=18.5, longitude=73.8), water_access="rainfed")
    farm = service.create_farm(farmer, payload)

    def snap(mode="live", kind="weather_forecast"):
        return EvidenceSnapshot(farm_id=farm.id, node_id=farm.node_id, provider="open_meteo", kind=kind, mode=mode,
                                spatial_scope="point", source_reference="x")

    for _ in range(5):
        service._store_evidence(farm.id, [snap(), snap(kind="weather_history")])
    assert len(service.store.list("evidence", filters={"farm_id": farm.id})) == 2
    good = service.store.list("evidence", filters={"farm_id": farm.id, "kind": "weather_forecast"})[0]["id"]
    service._store_evidence(farm.id, [snap(mode="missing")])
    assert service.store.get("evidence", good) is not None


def test_failed_satellite_reading_is_retried_after_hours_not_days(service: AppService, farmer: Actor, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from kisanai_c2c.models import EvidenceSnapshot
    payload = FarmCreate(name="Retry", state_code="MH", state_name="Maharashtra", district="Pune",
                         area_value=1, location=Location(latitude=18.5, longitude=73.8), water_access="rainfed")
    farm = service.create_farm(farmer, payload)
    old = datetime.now(UTC) - timedelta(hours=7)
    for kind, provider, mode in (("weather_forecast", "open_meteo", "live"), ("satellite_observation", "earth_engine_sentinel_2", "missing")):
        snap = EvidenceSnapshot(farm_id=farm.id, node_id=farm.node_id, provider=provider, kind=kind, mode=mode,
                                spatial_scope="point", source_reference="x", fetched_at=old)
        service.store.put("evidence", snap.id, snap.model_dump(mode="json"))
    asked = []
    monkeypatch.setattr(service, "refresh_evidence", lambda actor, farm_id, include_satellite=True: asked.append(include_satellite) or [])
    service.current_evidence(farmer, farm.id)
    assert asked == [True]  # a failed reading 7 h ago is retried; a good one would wait 5 days
