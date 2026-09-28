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
    actor = current_actor(None, "dev-abcdef12", None, "expert", None, settings)
    assert Role.expert not in actor.roles  # the role header alone is ignored
    actor = current_actor(None, "dev-abcdef12", "secret-code", None, None, settings)
    assert Role.expert in actor.roles
    with pytest.raises(HTTPException):
        current_actor(None, "dev-abcdef12", "wrong", None, None, settings)
    with pytest.raises(HTTPException):
        current_actor(None, "not-a-device", None, None, None, settings)


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
    bundle = node_a.export_practice(expert, "practice_bbf_drainage")
    assert bundle["practice_code"] == "broad-bed-furrow" and "field_evidence" not in bundle

    node_b = AppService(store=MemoryStore(), media_store=MemoryMediaStore(), settings=make_settings(node_id="node-pb", node_subdivisions="IN-PB"))
    expert_b = Actor(subject="dev-expert-pb00001", node_id="node-pb", roles={Role.expert})
    record = node_b.import_bundle(expert_b, bundle)
    assert record.bundle_type == "practice" and record.compatibility_findings == []
    with pytest.raises(RuntimeError):
        node_b.import_bundle(expert_b, bundle)
    node_b.review_import(expert_b, record.id, ExchangeReview(approve=True, note="Checked for Punjab black-soil pockets"))
    assert any(p.created_by == "imported:node-mh" for p in node_b.practices(expert_b))


def test_state_pack_exchange_switches_a_farm_from_global_baseline_to_regional_pack():
    pb_node = AppService(store=MemoryStore(), media_store=MemoryMediaStore(), settings=make_settings(node_id="node-pb", node_subdivisions="IN-PB"))
    mh_node = AppService(store=MemoryStore(), media_store=MemoryMediaStore(), settings=make_settings(node_id="node-mh", node_subdivisions="IN-MH"))
    farmer = Actor(subject="dev-farmer-pb0001", node_id="node-mh", roles={Role.farmer})
    mh_expert = Actor(subject="dev-expert-mh0001", node_id="node-mh", roles={Role.expert})
    farm = mh_node.create_farm(farmer, _payload(state_code="PB", state_name="Punjab", district="Ludhiana", water_access="irrigated", previous_crop="rice"))

    assert mh_node.crop_recommendations(farmer, farm.id).knowledge_mode == "global_baseline"
    with pytest.raises(LookupError):
        mh_node.export_pack("pack_in_punjab")  # a node only publishes packs for regions it serves

    record = mh_node.import_bundle(mh_expert, pb_node.export_pack("pack_in_punjab"))
    assert record.bundle_type == "agronomy_pack" and record.compatibility_findings == []
    assert mh_node.crop_recommendations(farmer, farm.id).knowledge_mode == "global_baseline"  # not active until reviewed

    mh_node.review_import(mh_expert, record.id, ExchangeReview(approve=True, note="Reviewed PAU calendar"))
    result = mh_node.crop_recommendations(farmer, farm.id)
    assert result.knowledge_mode == "regional_pack"
    assert result.pack.origin == "imported" and result.pack.origin_node == "node-pb"


def test_invalid_pack_is_rejected(service: AppService, expert: Actor):
    with pytest.raises(ValueError):
        service.import_bundle(expert, {"pack_id": "pack_in_bad", "schema_version": "1.0.0"})


def test_node_manifest_publishes_no_personal_data(service: AppService, farmer: Actor):
    service.create_farm(farmer, _payload())
    service.seed_default_practices_if_empty()
    manifest = service.node_manifest()
    assert {p["subdivision_code"] for p in manifest["packs"]} == {"IN-MH", "IN-UP"}
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
    punjab = AppService(MemoryStore(), MemoryMediaStore(), make_settings(node_id="node-pb", node_subdivisions="IN-PB"))
    punjab.seed_default_practices_if_empty()
    codes = {p["practice_code"] for p in punjab.store.list("practices", filters={"node_id": "node-pb"}, limit=10)}
    assert codes == {"residue-retention"}


def test_soil_health_card_ph_classes():
    from kisanai_c2c.soil import ph_rating
    assert [ph_rating(v) for v in (5.5, 6.2, 6.8, 8.0, 9.0)] == ["acidic", "slightly_acidic", "neutral", "alkaline", "strongly_alkaline"]
