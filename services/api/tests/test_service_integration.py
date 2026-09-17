import pytest
from typing import Any
from datetime import UTC, datetime

from kisanai_c2c.service import AppService
from kisanai_c2c.models import Actor, FarmCreate, Location, SoilTestCreate, SoilValues, PracticeCreate, Role

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

    def save(self, content: bytes, content_type: str) -> tuple[str, str]:
        uri = f"memory://{len(self.media)}"
        self.media[uri] = content
        return uri, uri

    def read(self, storage_uri: str) -> bytes:
        return self.media[storage_uri]

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

def test_practice_requires_review_before_export(service: AppService, expert: Actor):
    payload = PracticeCreate(
        title="Test Practice", summary="This is a test practice for the system.",
        crops=["wheat"], seasons=["rabi"], water_contexts=["irrigated"],
        steps=["Step 1", "Step 2"], contraindications=["None"], source_urls=["https://example.com"],
        license="CC0-1.0"
    )
    practice = service.create_practice(expert, payload)
    
    with pytest.raises(ValueError, match="Only reviewed practices can be exported"):
        service.export_practice(expert, practice.id)

def test_bundle_import_deduplication(service: AppService, expert: Actor):
    from kisanai_c2c.models import PracticeCreate, PracticeReview
    payload = PracticeCreate(
        title="Mulching", summary="Improves moisture retention",
        crops=["sorghum"], seasons=["kharif"], water_contexts=["rainfed"],
        steps=["Step 1"], contraindications=["Waterlogging"], source_urls=["https://example.com"],
        license="CC0-1.0"
    )
    practice = service.create_practice(expert, payload)
    service.review_practice(expert, practice.id, PracticeReview(approve=True, note="Approved for dryland"))
    bundle = service.export_practice(expert, practice.id)

    service.import_bundle(expert, bundle)

    with pytest.raises(RuntimeError, match="This bundle has already been imported"):
        service.import_bundle(expert, bundle)

def test_seed_default_practices(service: AppService):
    expert = Actor(subject="expert1", node_id=service.settings.node_id, roles={Role.expert})
    service.seed_default_practices_if_empty()
    practices = service.practices(expert)
    assert len(practices) >= 3
    reviewed = [p for p in practices if p.review_status == "reviewed"]
    assert len(reviewed) >= 3
    # Exporting a seeded practice should succeed because it is pre-reviewed
    bundle = service.export_practice(expert, reviewed[0].id)
    assert bundle["title"] == reviewed[0].title
    assert "steps" in bundle

def test_seed_default_farm(service: AppService):
    farm = service.seed_default_farm_if_empty()
    assert farm.id == "farm_default_mh"
    assert farm.location.latitude == 20.4283
    assert farm.location.longitude == 78.5082
    assert farm.location.source == "device"
    assert farm.location.confirmed is True

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

    # Test 3: If an unknown farm_id is requested by active session actor, it self-heals
    session_farm_id = "farm_session_cold_start_abc123"
    recovered = service.farm(farmer, session_farm_id)
    assert recovered.id == session_farm_id
    assert recovered.owner_subject == farmer.subject


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
    assert farm.creator_ip == creator_ip
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





