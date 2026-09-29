from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from kisanai_c2c.auth import current_actor
from kisanai_c2c.models import (
    ActionUpdate, Actor, AdvisoryAction, AdvisoryRequest, ExchangeReview, FarmCreate, Location, PracticeReview, Role,
    SoilTestCreate, SoilValues,
)
from kisanai_c2c.providers.gemini import PlanResult
from kisanai_c2c.providers.land import LandProfileProvider
from kisanai_c2c.service import MIN_GROUP_SIZE, AppService
from tests.conftest import VIDARBHA, MemoryMediaStore, MemoryStore, land_profile, make_settings


def _payload(**overrides) -> FarmCreate:
    base = dict(name="Shivar", state_code="MH", state_name="Maharashtra", district="Yavatmal", area_value=2,
                location=Location(latitude=20.43, longitude=78.51), water_access="rainfed", soil_type="black", previous_crop="soybean")
    base.update(overrides)
    return FarmCreate(**base)


@pytest.fixture(autouse=True)
def offline_land(monkeypatch):
    monkeypatch.setattr(LandProfileProvider, "fetch", lambda self, farm: land_profile(farm, VIDARBHA))


# --- identity and privacy ------------------------------------------------------------------------

def test_farms_are_private_to_the_device(service: AppService, farmer: Actor, other_farmer: Actor):
    farm = service.create_farm(farmer, _payload())
    assert [f.id for f in service.farms(farmer)] == [farm.id]
    assert service.farms(other_farmer) == []
    with pytest.raises(LookupError):
        service.farm(other_farmer, farm.id)
    with pytest.raises(LookupError):
        service.delete_farm(other_farmer, farm.id)


def test_unknown_farm_id_is_not_recreated(service: AppService, farmer: Actor):
    service.create_farm(farmer, _payload())
    with pytest.raises(LookupError):
        service.farm(farmer, "farm_does_not_exist")


def test_expert_role_requires_access_code():
    settings = make_settings(expert_access_token="secret-code")
    actor = current_actor("dev-abcdef12", None, "expert", None, settings)
    assert Role.expert not in actor.roles  # the role header alone is ignored
    actor = current_actor("dev-abcdef12", "secret-code", None, None, settings)
    assert Role.expert in actor.roles
    with pytest.raises(HTTPException):
        current_actor("dev-abcdef12", "wrong", None, None, settings)
    with pytest.raises(HTTPException):
        current_actor("not-a-device", None, None, None, settings)


# --- soil ------------------------------------------------------------------------------------------

def test_soil_test_requires_values_and_is_rated(service: AppService, farmer: Actor):
    farm = service.create_farm(farmer, _payload())
    with pytest.raises(ValueError):
        service.save_soil_test(farmer, farm.id, SoilTestCreate(values=SoilValues()))
    saved = service.save_soil_test(farmer, farm.id, SoilTestCreate(values=SoilValues(ph=7.9, organic_carbon_percent=0.38, nitrogen_kg_ha=190)))
    assert {r.parameter: r.rating for r in saved.ratings} == {"ph": "alkaline", "organic_carbon_percent": "low", "nitrogen_kg_ha": "low"}
    assert service.latest_soil(farm.id).id == saved.id


def test_pdf_soil_cards_are_accepted(service: AppService, farmer: Actor):
    record = service.save_media(farmer, b"%PDF-1.4 test", "application/pdf", "soil_card")
    assert record.content_type == "application/pdf"


# --- recommendations and plans -----------------------------------------------------------------------

def test_recommendations_use_the_state_pack_and_land_profile(service: AppService, farmer: Actor):
    farm = service.create_farm(farmer, _payload())
    result = service.crop_recommendations(farmer, farm.id, locale="mr-IN")
    assert result.knowledge_mode == "regional_pack" and result.pack.subdivision_code == "IN-MH"
    assert result.sow_now or result.upcoming
    assert result.sow_now[0].crop_name != result.sow_now[0].crop  # localized
    assert any(s.id == "climate" and s.status == "estimated" for s in result.data_sources)
    assert service.store.get("land_profiles", farm.id) is not None


def test_advisory_passes_engine_options_to_gemini(service: AppService, farmer: Actor, monkeypatch):
    farm = service.create_farm(farmer, _payload())
    captured = {}

    def fake_plan(**kwargs):
        captured.update(kwargs)
        return PlanResult(summary="Sow chickpea after the next soaking rain.", uncertainty_reasons=[], model_used="test-model",
                          actions=[AdvisoryAction(practice_id="field-scouting", instruction="Scout weekly", timing="this week", why="IPM")])

    monkeypatch.setattr(service.gemini, "create_plan", fake_plan)
    advisory = service.create_advisory(farmer, farm.id, AdvisoryRequest(goal="crop_plan", locale="hi-IN"))
    assert advisory.options and captured["options"][0]["crop"] == advisory.options[0].crop
    assert "field-scouting" in captured["allowed_practices"]
    assert advisory.model == "test-model"
    updated = service.update_action(farmer, advisory.actions[0].id, ActionUpdate(status="completed", outcome="worked"))
    assert updated.outcome == "worked" and updated.completed_at is not None


# --- practices, packs and the cross-node exchange ----------------------------------------------------

def test_seeded_practices_export_and_import_between_nodes(expert: Actor):
    node_a = AppService(store=MemoryStore(), media_store=MemoryMediaStore(), settings=make_settings(node_id="node-mh"))
    node_a.seed_default_practices_if_empty()
    with pytest.raises(ValueError):
        node_a.export_practice(expert, "practice_bbf_drainage")  # knowledge-base drafts need local review first
    for practice_id in ("practice_bbf_drainage", "practice_soy_inoculation"):
        node_a.review_practice(expert, practice_id, PracticeReview(approve=True, note="Checked"))
    assert "practice_bbf_drainage" in [p["bundle_id"] for p in node_a.node_manifest()["practices"]]
    bbf = node_a.export_practice(expert, "practice_bbf_drainage")
    assert bbf["practice_code"] == "broad-bed-furrow" and "field_evidence" not in bbf

    node_b = AppService(store=MemoryStore(), media_store=MemoryMediaStore(), settings=make_settings(node_id="node-br-pr", node_country_code="BR", node_subdivisions="BR-PR"))
    expert_b = Actor(subject="dev-expert-br00001", node_id="node-br-pr", roles={Role.expert})
    flagged = node_b.import_bundle(expert_b, bbf)
    assert flagged.compatibility_findings  # an Indian black-soil practice is not auto-approvable in Brazil
    with pytest.raises(ValueError):
        node_b.review_import(expert_b, flagged.id, ExchangeReview(approve=True, note="Try"))

    inoculation = node_a.export_practice(expert, "practice_soy_inoculation")
    record = node_b.import_bundle(expert_b, inoculation)
    assert record.bundle_type == "practice" and record.compatibility_findings == []
    with pytest.raises(RuntimeError):
        node_b.import_bundle(expert_b, inoculation)
    node_b.review_import(expert_b, record.id, ExchangeReview(approve=True, note="Checked for Paraná conditions"))
    assert any(p.created_by == "imported:node-mh" for p in node_b.practices(expert_b))


def test_cross_country_pack_exchange_switches_a_farm_from_global_baseline_to_regional_pack():
    br_node = AppService(store=MemoryStore(), media_store=MemoryMediaStore(), settings=make_settings(node_id="node-br-pr", node_country_code="BR", node_subdivisions="BR-PR"))
    mh_node = AppService(store=MemoryStore(), media_store=MemoryMediaStore(), settings=make_settings(node_id="node-mh", node_subdivisions="IN-MH"))
    farmer = Actor(subject="dev-farmer-br0001", node_id="node-mh", roles={Role.farmer})
    mh_expert = Actor(subject="dev-expert-mh0001", node_id="node-mh", roles={Role.expert})
    farm = mh_node.create_farm(farmer, _payload(country_code="BR", state_code="PR", state_name="Paraná", district="Cascavel",
                                                location=Location(latitude=-24.9, longitude=-53.4), previous_crop="wheat"))

    assert mh_node.crop_recommendations(farmer, farm.id).knowledge_mode == "global_baseline"
    with pytest.raises(LookupError):
        mh_node.export_pack("pack_br_parana")  # a node only publishes packs for regions it serves

    record = mh_node.import_bundle(mh_expert, br_node.export_pack("pack_br_parana"))
    assert record.bundle_type == "agronomy_pack" and record.compatibility_findings == []
    assert mh_node.crop_recommendations(farmer, farm.id).knowledge_mode == "global_baseline"  # not active until reviewed

    mh_node.review_import(mh_expert, record.id, ExchangeReview(approve=True, note="Reviewed CONAB calendar"))
    result = mh_node.crop_recommendations(farmer, farm.id)
    assert result.knowledge_mode == "regional_pack"
    assert result.pack.origin == "imported" and result.pack.origin_node == "node-br-pr"


def test_invalid_pack_is_rejected(service: AppService, expert: Actor):
    with pytest.raises(ValueError):
        service.import_bundle(expert, {"pack_id": "pack_in_bad", "schema_version": "1.0.0"})


def test_node_manifest_publishes_no_personal_data(service: AppService, farmer: Actor):
    service.create_farm(farmer, _payload())
    service.seed_default_practices_if_empty()
    manifest = service.node_manifest()
    assert {p["subdivision_code"] for p in manifest["packs"]} == {"IN-MH"}
    text = str(manifest)
    assert "Shivar" not in text and "20.43" not in text and farmer.subject not in text


# --- outcomes, signals and dashboard -------------------------------------------------------------------

def _advisory_with_outcomes(service: AppService, actor: Actor, farm_id: str, outcomes: list[str]) -> None:
    from kisanai_c2c.models import Advisory
    actions = [AdvisoryAction(practice_id="broad-bed-furrow", instruction="Make BBF", timing="before sowing", why="drainage",
                              status="completed", outcome=o) for o in outcomes]
    advisory = Advisory(farm_id=farm_id, owner_subject=actor.subject, node_id=actor.node_id, goal="crop_plan", locale="en-IN",
                        summary="s", options=[], actions=actions, evidence_ids=[], model_provider="t", model="t", prompt_version="t", policy_version="t")
    service.store.put("advisories", advisory.id, advisory.model_dump(mode="json"))


def test_field_evidence_is_shared_only_above_group_threshold(service: AppService, farmer: Actor, expert: Actor):
    service.seed_default_practices_if_empty()
    service.review_practice(expert, "practice_bbf_drainage", PracticeReview(approve=True, note="Checked"))
    farm = service.create_farm(farmer, _payload())
    _advisory_with_outcomes(service, farmer, farm.id, ["worked"] * (MIN_GROUP_SIZE - 1))
    assert "field_evidence" not in service.export_practice(expert, "practice_bbf_drainage")
    _advisory_with_outcomes(service, farmer, farm.id, ["partly"])
    evidence = service.export_practice(expert, "practice_bbf_drainage")["field_evidence"]
    assert evidence["outcomes_reported"] == MIN_GROUP_SIZE and evidence["worked"] == MIN_GROUP_SIZE - 1


def test_shared_signals_suppress_small_groups_and_dashboard_counts(service: AppService, farmer: Actor, expert: Actor):
    now = datetime.now(UTC).isoformat()
    for i in range(MIN_GROUP_SIZE + 1):
        service.store.put("diagnoses", f"d{i}", {"id": f"d{i}", "node_id": "node-mh", "district": "Yavatmal", "subdivision_code": "IN-MH",
                                                 "crop": "cotton", "category": "pest", "suspected_condition": "Pink bollworm", "created_at": now})
    service.store.put("diagnoses", "lone", {"id": "lone", "node_id": "node-mh", "district": "Akola", "subdivision_code": "IN-MH",
                                            "crop": "soybean", "category": "disease", "created_at": now})
    signals = service.shared_signals()["signals"]
    assert signals == [{"subdivision_code": "IN-MH", "district": "Yavatmal", "crop": "cotton", "category": "pest", "reports": MIN_GROUP_SIZE + 1}]
    dashboard = service.dashboard(expert)
    assert dashboard["totals"]["diagnoses_30d"] == MIN_GROUP_SIZE + 2
    assert dashboard["top_conditions"][0] == {"condition": "pink bollworm", "reports": MIN_GROUP_SIZE + 1}


def test_practice_review_toggle(service: AppService, expert: Actor):
    service.seed_default_practices_if_empty()
    practice = service.review_practice(expert, "practice_residue_mulching", PracticeReview(approve=False, note="Needs local trial"))
    assert practice.review_status == "draft"
    with pytest.raises(ValueError):
        service.export_practice(expert, "practice_residue_mulching")


def test_seeded_practices_match_the_node_states():
    parana = AppService(MemoryStore(), MemoryMediaStore(), make_settings(node_id="node-br-pr", node_country_code="BR", node_subdivisions="BR-PR"))
    parana.seed_default_practices_if_empty()
    ids = {p["id"] for p in parana.store.list("practices", filters={"node_id": "node-br-pr"}, limit=10)}
    assert ids == {"practice_no_till_straw", "practice_soy_inoculation"}  # no Indian black-soil BBF in Brazil


def test_soil_health_card_ph_classes():
    from kisanai_c2c.soil import ph_rating
    assert [ph_rating(v) for v in (5.5, 6.2, 6.8, 8.0, 9.0)] == ["acidic", "slightly_acidic", "neutral", "alkaline", "strongly_alkaline"]


def test_production_needs_durable_storage_and_an_expert_code():
    durable = dict(app_env="production", store_provider="firestore", media_provider="gcs", media_bucket="b",
                   google_cloud_project="p", imd_enabled=False)
    with pytest.raises(ValueError, match="EXPERT_ACCESS_TOKEN"):
        make_settings(**durable)
    with pytest.raises(ValueError, match="firestore"):
        make_settings(app_env="production", expert_access_token="code", google_cloud_project="p")
    settings = make_settings(**durable, expert_access_token="code")
    farmer = current_actor("dev-abcdef12", None, "expert", None, settings)
    assert Role.expert not in farmer.roles
    assert Role.expert in current_actor("dev-abcdef12", "code", None, None, settings).roles


def test_peer_signals_come_only_from_allowlisted_peers_and_respect_k(monkeypatch):
    import kisanai_c2c.service as service_module

    calls = []

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"node_id": "node-br-pr", "window_days": 30, "signals": [
                {"subdivision_code": "BR-PR", "district": "Cascavel", "crop": "soybean", "category": "disease", "reports": 7},
                {"subdivision_code": "BR-PR", "district": "Toledo", "crop": "maize", "category": "pest", "reports": 2}]}

    monkeypatch.setattr(service_module.requests, "get", lambda url, timeout: calls.append(url) or Reply())
    svc = AppService(MemoryStore(), MemoryMediaStore(), make_settings(peer_nodes="https://br.example"))
    signals = svc.peer_signals()
    assert calls == ["https://br.example/api/v1/network/signals"]
    assert [(s["district"], s["reports"]) for s in signals] == [("Cascavel", 7)]


def test_node_languages_are_machine_translated_once_and_cached():
    svc = AppService(MemoryStore(), MemoryMediaStore(), make_settings(node_id="node-br-pr", node_country_code="BR",
                                                                       node_subdivisions="BR-PR", node_languages="pt-BR,en-IN"))
    calls = []
    svc.translator.translate = lambda texts, locale: calls.append(len(texts)) or [f"[{locale}] {t}" for t in texts]
    first = svc.ui_strings("pt-BR")
    assert first["machine_translated"] and first["strings"]["go_home"] == "[pt-BR] Home"
    svc.ui_strings("pt-BR")
    assert len(calls) == 1  # second request served from the store
    with pytest.raises(LookupError):
        svc.ui_strings("fr-FR")  # only languages the node offers

    from kisanai_c2c.knowledge import practice_name
    svc.localize_names("pt-BR")
    assert practice_name("legume-rotation", "pt-BR").startswith("[pt-BR]")  # no hand-written Portuguese practice names
    assert crop_name_pt("soybean") == "Soja"  # catalog names win over machine translation


def crop_name_pt(crop_id: str) -> str:
    from kisanai_c2c.knowledge import crop_name
    return crop_name(crop_id, "pt-BR")


def test_deleting_a_farm_erases_its_records_and_photos(service: AppService, farmer: Actor):
    farm = service.create_farm(farmer, _payload())
    media = service.save_media(farmer, b"\x89PNG leaf", "image/png", "crop_diagnosis")
    service.store.put("diagnoses", "d1", {"id": "d1", "farm_id": farm.id, "owner_subject": farmer.subject, "media_id": media.id})
    service.store.put("expert_cases", "c1", {"id": "c1", "farm_id": farm.id, "owner_subject": farmer.subject, "diagnosis_id": "d1"})
    service.save_soil_test(farmer, farm.id, SoilTestCreate(values=SoilValues(ph=6.8)))
    service.delete_farm(farmer, farm.id)
    for collection in ("farms", "diagnoses", "expert_cases", "soil_tests", "media"):
        assert service.store.list(collection, filters={}, limit=10) == [], collection
    assert service.media_store.media == {}  # the photo file itself is gone


def test_google_geocoding_maps_to_state_and_district():
    from kisanai_c2c.providers.maps import place_from_google

    def comp(kind, name, short=None):
        return {"types": [kind, "political"], "long_name": name, "short_name": short or name}

    india = place_from_google({"formatted_address": "Yavatmal, Maharashtra 445001, India", "geometry": {"location": {"lat": 20.39, "lng": 78.13}},
                               "address_components": [comp("locality", "Yavatmal"), comp("administrative_area_level_3", "Yavatmal"),
                                                      comp("administrative_area_level_2", "Amravati Division"),
                                                      comp("administrative_area_level_1", "Maharashtra", "MH"), comp("country", "India", "IN")]})
    assert (india["state_code"], india["district"]) == ("MH", "Yavatmal")  # division (level 2) is not the district
    brazil = place_from_google({"formatted_address": "Pato Branco - PR, Brazil", "geometry": {"location": {"lat": -26.23, "lng": -52.67}},
                                "address_components": [comp("administrative_area_level_2", "Pato Branco"),
                                                       comp("administrative_area_level_1", "Paraná", "PR"), comp("country", "Brazil", "BR")]})
    assert (brazil["country_code"], brazil["state_code"], brazil["district"]) == ("BR", "PR", "Pato Branco")


def test_public_network_directory_lists_this_node_and_peers(monkeypatch):
    import kisanai_c2c.service as service_module

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"node_id": "brazil-node-pr", "label": "Brazil - Paraná node", "country_code": "BR", "subdivisions": ["BR-PR"],
                    "languages": ["pt-BR"], "app_url": "https://br.example"}

    monkeypatch.setattr(service_module.requests, "get", lambda url, timeout: Reply())
    service_module._NETWORK_CACHE.clear()
    svc = AppService(MemoryStore(), MemoryMediaStore(), make_settings(peer_nodes="https://br.example", public_base_url="https://mh.example"))
    nodes = svc.network_nodes()["nodes"]
    assert [(n["current"], n["country_code"], n["url"]) for n in nodes] == [(True, "IN", "https://mh.example"), (False, "BR", "https://br.example")]
    assert "packs" not in nodes[1] and nodes[1]["languages"] == ["pt-BR"]


def test_imd_errors_never_carry_credentials():
    from kisanai_c2c.providers.weather import WeatherProvider

    provider = WeatherProvider(make_settings(imd_api_key="secret-key-123", imd_password="pw-456"))
    text = provider._redact("401 for url https://api.imd.gov.in/api/v1/x?api_key=secret-key-123 password pw-456")
    assert "secret-key-123" not in text and "pw-456" not in text and "api_key=<redacted>" in text
