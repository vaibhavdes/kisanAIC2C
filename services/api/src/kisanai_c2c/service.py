from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import requests
from jsonschema import Draft202012Validator, FormatChecker

from .engine import RecommendationEngine, top_options
from .knowledge import bundled_packs, crop_catalog, crop_name, normalize_crop, practice_catalog, subdivision_code
from .media import MediaStore, get_media_store
from .models import (
    ActionUpdate,
    Actor,
    Advisory,
    AdvisoryAction,
    AdvisoryRequest,
    CropRecommendationResult,
    Diagnosis,
    DiagnosisRequest,
    EvidenceSnapshot,
    ExchangeImport,
    ExchangeReview,
    ExpertCase,
    ExpertReview,
    Farm,
    FarmCreate,
    LandProfile,
    MediaRecord,
    PackRef,
    Practice,
    PracticeCreate,
    PracticeReview,
    Role,
    SoilExtraction,
    SoilTest,
    SoilTestCreate,
    SoilValues,
)
from .operations import operational_indicators
from .providers.gemini import GeminiProvider
from .providers.land import LandProfileProvider, LandProfileUnavailable
from .providers.satellite import SatelliteProvider, SatelliteUnavailable
from .providers.weather import WeatherProvider
from .settings import PROJECT_ROOT, Settings, get_settings
from .soil import effective_soil, rate_values
from .store import DocumentStore, get_store

POLICY_VERSION = "kisanai-engine-2.0.0"
MIN_GROUP_SIZE = 5  # k-anonymity threshold for anything shared outside the node


def _schema(name: str) -> dict[str, Any]:
    return json.loads((PROJECT_ROOT / "contracts" / name).read_text())


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class AppService:
    def __init__(
        self,
        store: DocumentStore | None = None,
        media_store: MediaStore | None = None,
        settings: Settings | None = None,
    ):
        self.store = store or get_store()
        self.media_store = media_store or get_media_store()
        self.settings = settings or get_settings()
        self.gemini = GeminiProvider(self.settings)

    # ------------------------------------------------------------------ farms
    def create_farm(self, actor: Actor, payload: FarmCreate) -> Farm:
        area_ha = payload.area_value if payload.area_unit == "hectare" else payload.area_value * 0.40468564224
        farm = Farm(
            **payload.model_dump(exclude={"id"}),
            id=f"farm_{uuid4().hex}",
            area_ha=round(area_ha, 4),
            owner_subject=actor.subject,
            node_id=actor.node_id,
            is_mine=True,
        )
        self.store.put("farms", farm.id, farm.model_dump(mode="json"))
        return farm

    def farms(self, actor: Actor) -> list[Farm]:
        items = self.store.list("farms", filters={"node_id": actor.node_id, "owner_subject": actor.subject})
        farms = [Farm.model_validate(item) for item in items]
        for farm in farms:
            farm.is_mine = True
        return farms

    def farm(self, actor: Actor, farm_id: str, *, expert_allowed: bool = False) -> Farm:
        value = self.store.get("farms", farm_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Farm not found")
        is_owner = value.get("owner_subject") == actor.subject
        if not is_owner and not (expert_allowed and Role.expert in actor.roles):
            raise LookupError("Farm not found")
        farm = Farm.model_validate(value)
        farm.is_mine = is_owner
        return farm

    def update_farm(self, actor: Actor, farm_id: str, payload: FarmCreate, expected_version: int) -> Farm:
        current = self.farm(actor, farm_id)
        if current.version != expected_version:
            raise RuntimeError("Farm was changed elsewhere; reload and try again")
        area_ha = payload.area_value if payload.area_unit == "hectare" else payload.area_value * 0.40468564224
        updated = current.model_copy(update={
            **payload.model_dump(exclude={"id"}),
            "area_ha": round(area_ha, 4),
            "version": current.version + 1,
            "updated_at": datetime.now(UTC),
        })
        self.store.put("farms", farm_id, updated.model_dump(mode="json"))
        moved = (abs(current.location.latitude - updated.location.latitude) > 1e-4
                 or abs(current.location.longitude - updated.location.longitude) > 1e-4
                 or current.boundary_coordinates != updated.boundary_coordinates)
        if moved:
            self.store.delete("land_profiles", farm_id)
            self._prune_evidence(farm_id, keep_ids=set())
        return updated

    def delete_farm(self, actor: Actor, farm_id: str) -> bool:
        self.farm(actor, farm_id)
        self.store.delete("land_profiles", farm_id)
        self._prune_evidence(farm_id, keep_ids=set())
        return self.store.delete("farms", farm_id)

    # ------------------------------------------------------------------ media & soil
    def save_media(self, actor: Actor, content: bytes, content_type: str, purpose: str) -> MediaRecord:
        if len(content) > self.settings.media_max_bytes:
            raise ValueError("File is larger than the 8 MB limit")
        storage_uri, _ = self.media_store.save(content, content_type)
        record = MediaRecord(owner_subject=actor.subject, node_id=actor.node_id, storage_uri=storage_uri,
                             content_type=content_type, size_bytes=len(content), purpose=purpose)
        self.store.put("media", record.id, record.model_dump(mode="json"))
        return record

    def media(self, actor: Actor, media_id: str, *, expert_allowed: bool = False) -> MediaRecord:
        value = self.store.get("media", media_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Media not found")
        if value.get("owner_subject") != actor.subject and not (expert_allowed and Role.expert in actor.roles):
            raise LookupError("Media not found")
        return MediaRecord.model_validate(value)

    def extract_soil(self, actor: Actor, farm_id: str, media_id: str, locale: str) -> SoilExtraction:
        self.farm(actor, farm_id)
        media = self.media(actor, media_id)
        if media.purpose != "soil_card":
            raise ValueError("Upload the file as a soil card")
        result = self.gemini.extract_soil_card(image=self.media_store.read(media.storage_uri), mime_type=media.content_type, locale=locale)
        values = SoilValues(**{key: getattr(result, key) for key in SoilValues.model_fields})
        extraction = SoilExtraction(
            values=values,
            sample_date=result.sample_date,
            lab_name=result.lab_name,
            raw_text=result.raw_text,
            card_recommendations=result.card_recommendations,
            plain_explanation=result.plain_explanation,
            uncertain_fields=result.uncertain_fields,
            ratings=rate_values(values),
            source=self.gemini.provider_name,
            model=self.settings.gemini_model,
        )
        record = extraction.model_dump(mode="json") | {"id": f"extract_{media_id}", "farm_id": farm_id,
                                                         "owner_subject": actor.subject, "node_id": actor.node_id}
        self.store.put("soil_extractions", record["id"], record)
        return extraction

    def save_soil_test(self, actor: Actor, farm_id: str, payload: SoilTestCreate) -> SoilTest:
        self.farm(actor, farm_id)
        if not payload.confirmed:
            raise ValueError("Only values you have checked can be saved")
        if all(value is None for value in payload.values.model_dump().values()):
            raise ValueError("Enter at least one soil value")
        record = SoilTest(**payload.model_dump(), farm_id=farm_id, owner_subject=actor.subject, node_id=actor.node_id,
                          ratings=rate_values(payload.values))
        self.store.put("soil_tests", record.id, record.model_dump(mode="json"))
        return record

    def latest_soil(self, farm_id: str) -> SoilTest | None:
        values = self.store.list("soil_tests", filters={"farm_id": farm_id}, limit=1)
        return SoilTest.model_validate(values[0]) if values else None

    # ------------------------------------------------------------------ land profile & evidence
    def land_profile(self, farm: Farm, *, refresh: bool = False) -> LandProfile | None:
        cached = None if refresh else self.store.get("land_profiles", farm.id)
        if cached:
            profile = LandProfile.model_validate(cached)
            same_place = abs(profile.latitude - farm.location.latitude) < 1e-4 and abs(profile.longitude - farm.location.longitude) < 1e-4
            if same_place:
                return profile
        try:
            profile = LandProfileProvider(self.settings).fetch(farm)
        except LandProfileUnavailable:
            return None
        self.store.put("land_profiles", farm.id, profile.model_dump(mode="json") | {"id": farm.id})
        return profile

    def refresh_evidence(self, actor: Actor, farm_id: str) -> list[EvidenceSnapshot]:
        farm = self.farm(actor, farm_id)
        with ThreadPoolExecutor(max_workers=3) as pool:
            weather_future = pool.submit(WeatherProvider(self.settings).fetch, farm)
            satellite_future = pool.submit(SatelliteProvider(self.settings).fetch, farm)
            land_future = pool.submit(self.land_profile, farm)
            snapshots = weather_future.result()
            try:
                snapshots.append(satellite_future.result())
            except SatelliteUnavailable as exc:
                snapshots.append(EvidenceSnapshot(
                    farm_id=farm.id, node_id=farm.node_id, provider="earth_engine_sentinel_2", kind="satellite_observation",
                    mode="missing", spatial_scope="farm", quality_flags=[str(exc)], source_reference="COPERNICUS/S2_SR_HARMONIZED",
                ))
            land_future.result()
        for snapshot in snapshots:
            self.store.put("evidence", snapshot.id, snapshot.model_dump(mode="json"))
        self._prune_evidence(farm_id, keep_ids={snapshot.id for snapshot in snapshots})
        return snapshots

    def _prune_evidence(self, farm_id: str, keep_ids: set[str]) -> None:
        for item in self.store.list("evidence", filters={"farm_id": farm_id}, limit=200):
            if item.get("id") not in keep_ids:
                self.store.delete("evidence", item["id"])

    def evidence(self, actor: Actor, farm_id: str) -> list[EvidenceSnapshot]:
        self.farm(actor, farm_id, expert_allowed=True)
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for item in self.store.list("evidence", filters={"farm_id": farm_id}, limit=50):
            key = (item.get("provider", ""), item.get("kind", ""))
            if key not in latest or str(item.get("fetched_at")) > str(latest[key].get("fetched_at")):
                latest[key] = item
        return [EvidenceSnapshot.model_validate(item) for item in latest.values()]

    def _evidence_or_refresh(self, actor: Actor, farm: Farm) -> list[dict[str, Any]]:
        evidence = self.evidence(actor, farm.id)
        has_forecast = any(item.kind == "weather_forecast" and item.data for item in evidence)
        if not has_forecast:
            try:
                evidence = self.refresh_evidence(actor, farm.id)
            except Exception:  # noqa: BLE001 - recommendations still run on climate and soil data
                pass
        return [item.model_dump(mode="json") for item in evidence]

    def operational(self, actor: Actor, farm_id: str) -> dict[str, Any]:
        farm = self.farm(actor, farm_id)
        evidence = self._evidence_or_refresh(actor, farm)
        land = self.store.get("land_profiles", farm.id)
        soil = effective_soil(farm.soil_type, self.latest_soil(farm.id), LandProfile.model_validate(land).soil if land else None)
        return operational_indicators(evidence, texture=soil["texture"], water_access=farm.water_access,
                                      crop_status=farm.crop_status, current_crop=farm.current_crop)

    # ------------------------------------------------------------------ packs
    def _imported_packs(self) -> list[dict[str, Any]]:
        return self.store.list("packs", filters={"node_id": self.settings.node_id, "status": "active"}, limit=100)

    def pack_for(self, farm: Farm) -> tuple[dict[str, Any] | None, PackRef | None]:
        code = subdivision_code(farm.country_code, farm.state_code)
        if not code:
            return None, None
        imported = [item for item in self._imported_packs() if item.get("subdivision_code") == code]
        bundled = bundled_packs().get(code)
        # A node only uses bundled packs for the regions it serves; other regions need an approved import.
        if bundled and code not in self.settings.node_subdivision_list and self.settings.node_subdivision_list:
            bundled = None
        best_import = max(imported, key=lambda item: item["pack"]["pack_version"]) if imported else None
        if best_import and (not bundled or best_import["pack"]["pack_version"] >= bundled["pack_version"]):
            pack = best_import["pack"]
            return pack, PackRef(pack_id=pack["pack_id"], pack_version=pack["pack_version"], name=pack["region"]["name"],
                                 subdivision_code=code, review_status="reviewed",
                                 origin="imported", origin_node=(pack.get("origin") or {}).get("node_id"))
        if bundled:
            return bundled, PackRef(pack_id=bundled["pack_id"], pack_version=bundled["pack_version"], name=bundled["region"]["name"],
                                    subdivision_code=code, review_status=bundled["review"]["status"], origin="bundled")
        return None, None

    def list_packs(self) -> list[dict[str, Any]]:
        out = []
        for code, pack in bundled_packs().items():
            if code not in self.settings.node_subdivision_list:
                continue
            out.append({"pack_id": pack["pack_id"], "pack_version": pack["pack_version"], "subdivision_code": code,
                        "name": pack["region"]["name"], "crops": len(pack["crops"]), "districts": len(pack.get("districts", [])),
                        "review_status": pack["review"]["status"], "origin": "own", "published": True})
        for item in self._imported_packs():
            pack = item["pack"]
            out.append({"pack_id": pack["pack_id"], "pack_version": pack["pack_version"], "subdivision_code": item["subdivision_code"],
                        "name": pack["region"]["name"], "crops": len(pack["crops"]), "districts": len(pack.get("districts", [])),
                        "review_status": "reviewed", "origin": "imported", "origin_node": (pack.get("origin") or {}).get("node_id"),
                        "approved_by": item.get("approved_by"), "published": False})
        return out

    def export_pack(self, pack_id: str) -> dict[str, Any]:
        for code, pack in bundled_packs().items():
            if pack["pack_id"] == pack_id and code in self.settings.node_subdivision_list:
                return pack | {"origin": {"node_id": self.settings.node_id, "organization_label": self.settings.node_label,
                                          "exported_at": datetime.now(UTC).isoformat()}}
        raise LookupError("This node does not publish that pack")

    # ------------------------------------------------------------------ recommendations & advisory
    def crop_recommendations(self, actor: Actor, farm_id: str, locale: str = "en-IN") -> CropRecommendationResult:
        farm = self.farm(actor, farm_id)
        evidence = self._evidence_or_refresh(actor, farm)
        pack, pack_ref = self.pack_for(farm)
        engine = RecommendationEngine(farm, pack=pack, pack_ref=pack_ref, land=self.land_profile(farm),
                                      soil_test=self.latest_soil(farm.id), evidence=evidence, locale=locale)
        return engine.run()

    def create_advisory(self, actor: Actor, farm_id: str, payload: AdvisoryRequest) -> Advisory:
        farm = self.farm(actor, farm_id)
        if payload.goal == "manage_current_crop" and not farm.current_crop:
            raise ValueError("Add the crop you have planted to get crop-care advice")
        recommendations = self.crop_recommendations(actor, farm_id, locale=payload.locale)
        operations = self.operational(actor, farm_id)
        evidence = [item.model_dump(mode="json") for item in self.evidence(actor, farm_id)]
        options = top_options(recommendations, 3) if payload.goal == "crop_plan" else []
        pack = self.pack_for(farm)[0] or {}
        practice_ids = sorted({p.id for option in options for p in option.practices}
                              | set(pack.get("priority_practices", [])[:4])
                              | {"field-scouting", "residue-retention"})
        soil = self.latest_soil(farm.id)
        result = self.gemini.create_plan(
            locale=payload.locale,
            goal=payload.goal,
            farm=farm.model_dump(mode="json", exclude={"owner_subject", "node_id", "is_mine", "boundary_coordinates"}),
            soil=soil.model_dump(mode="json", include={"values", "ratings", "sample_date", "card_recommendations"}) if soil else None,
            options=[option.model_dump(mode="json", include={"crop", "crop_name", "suitability", "regenerative_score", "sowing",
                                                            "water_need_mm", "irrigation_gap_mm", "factors", "practices"}) for option in options],
            operations={key: operations.get(key) for key in ("sowing", "spray", "irrigation", "drainage", "disease_risks", "temperature_extremes", "imd")},
            context=recommendations.context,
            allowed_practices={pid: practice_catalog()[pid]["names"]["en"] for pid in practice_ids if pid in practice_catalog()},
            evidence_ids=[item["id"] for item in evidence],
            farmer_question=payload.farmer_question,
        )
        advisory = Advisory(
            farm_id=farm.id,
            owner_subject=actor.subject,
            node_id=actor.node_id,
            goal=payload.goal,
            locale=payload.locale,
            summary=result.summary,
            options=options,
            actions=result.actions,
            evidence_ids=[item["id"] for item in evidence],
            uncertainty_reasons=result.uncertainty_reasons,
            model_provider=self.gemini.provider_name,
            model=result.model_used or self.settings.gemini_model,
            prompt_version=self.gemini.prompt_version,
            policy_version=POLICY_VERSION,
        )
        self.store.put("advisories", advisory.id, advisory.model_dump(mode="json"))
        return advisory

    def advisories(self, actor: Actor, farm_id: str) -> list[Advisory]:
        self.farm(actor, farm_id)
        return [Advisory.model_validate(item) for item in self.store.list("advisories", filters={"farm_id": farm_id}, limit=20)]

    def update_action(self, actor: Actor, action_id: str, payload: ActionUpdate) -> AdvisoryAction:
        for advisory_data in self.store.list("advisories", filters={"owner_subject": actor.subject, "node_id": actor.node_id}, limit=100):
            advisory = Advisory.model_validate(advisory_data)
            for idx, action in enumerate(advisory.actions):
                if action.id == action_id:
                    updated = action.model_copy(update={
                        "status": payload.status,
                        "outcome": payload.outcome if payload.status == "completed" else None,
                        "observation": payload.observation,
                        "completed_at": datetime.now(UTC) if payload.status == "completed" else None,
                    })
                    advisory.actions[idx] = updated
                    self.store.put("advisories", advisory.id, advisory.model_dump(mode="json"))
                    return updated
        raise LookupError("Action not found")

    def chat_context(self, actor: Actor, farm: Farm, locale: str) -> dict[str, Any]:
        context: dict[str, Any] = {}
        try:
            recs = self.crop_recommendations(actor, farm.id, locale=locale)
            context["recommended_now"] = [f"{o.crop_name} (fit {round(o.suitability * 100)}%)" for o in recs.sow_now[:4]]
            context["recommended_soon"] = [f"{o.crop_name} from {o.sowing.start}" for o in recs.upcoming[:4] if o.sowing]
            context["farm_context"] = recs.context
        except Exception:  # noqa: BLE001
            pass
        try:
            ops = self.operational(actor, farm.id)
            if ops.get("available"):
                context["operations"] = {key: (ops[key] or {}).get("message") for key in ("sowing", "spray", "irrigation", "drainage")}
                context["disease_risks"] = [f"{r['id']}: {r['status']}" for r in ops.get("disease_risks", [])]
        except Exception:  # noqa: BLE001
            pass
        soil = self.latest_soil(farm.id)
        if soil:
            context["soil_test_ratings"] = {rating.parameter: rating.rating for rating in soil.ratings}
        return context

    # ------------------------------------------------------------------ diagnosis & expert cases
    def diagnose(self, actor: Actor, farm_id: str | None, payload: DiagnosisRequest) -> tuple[Diagnosis, ExpertCase | None]:
        farm = self.farm(actor, farm_id) if farm_id and farm_id != "standalone" else None
        media = self.media(actor, payload.media_id)
        if media.purpose != "crop_diagnosis":
            raise ValueError("Upload the photo as a crop diagnosis image")
        crop = payload.crop if payload.crop and payload.crop != "auto-detect" else (farm.current_crop if farm and farm.current_crop else "auto-detect")
        weather_context = None
        if farm:
            try:
                ops = self.operational(actor, farm.id)
                if ops.get("available"):
                    weather_context = {"current": ops.get("current"), "rain_7d_mm": ops.get("rain_7d_mm"),
                                       "disease_risks": [{k: r[k] for k in ("id", "status")} for r in ops.get("disease_risks", [])]}
            except Exception:  # noqa: BLE001
                weather_context = None
        result = self.gemini.diagnose(
            image=self.media_store.read(media.storage_uri), mime_type=media.content_type, crop=crop,
            stage=payload.crop_stage, symptoms=payload.symptoms, locale=payload.locale, weather_context=weather_context,
        )
        diagnosis = Diagnosis(
            farm_id=farm.id if farm else "standalone",
            owner_subject=actor.subject,
            node_id=actor.node_id,
            media_id=media.id,
            crop=normalize_crop(crop) if crop != "auto-detect" else "auto-detect",
            district=farm.district if farm else None,
            subdivision_code=subdivision_code(farm.country_code, farm.state_code) if farm else None,
            weather_context=weather_context,
            model_provider=self.gemini.provider_name,
            model=result.model_used or self.settings.gemini_model,
            **result.model_dump(exclude={"model_used"}),
        )
        self.store.put("diagnoses", diagnosis.id, diagnosis.model_dump(mode="json"))
        case = None
        if diagnosis.needs_expert_review:
            case = ExpertCase(node_id=actor.node_id, owner_subject=actor.subject, farm_id=diagnosis.farm_id, diagnosis_id=diagnosis.id)
            self.store.put("expert_cases", case.id, case.model_dump(mode="json"))
        return diagnosis, case

    def expert_cases(self, actor: Actor) -> list[dict[str, Any]]:
        out = []
        for item in self.store.list("expert_cases", filters={"node_id": actor.node_id}, limit=100):
            case = ExpertCase.model_validate(item)
            diagnosis = self.store.get("diagnoses", case.diagnosis_id)
            out.append(case.model_dump(mode="json") | {"diagnosis": diagnosis,
                                                       "image_path": f"/api/v1/expert/cases/{case.id}/image" if diagnosis else None})
        return out

    def expert_case_image(self, actor: Actor, case_id: str) -> tuple[bytes, str]:
        value = self.store.get("expert_cases", case_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Expert case not found")
        diagnosis = self.store.get("diagnoses", value["diagnosis_id"])
        if not diagnosis:
            raise LookupError("Diagnosis not found")
        media = self.media(actor, diagnosis["media_id"], expert_allowed=True)
        return self.media_store.read(media.storage_uri), media.content_type

    def review_case(self, actor: Actor, case_id: str, payload: ExpertReview) -> ExpertCase:
        value = self.store.get("expert_cases", case_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Expert case not found")
        current = ExpertCase.model_validate(value)
        if current.version != payload.version:
            raise RuntimeError("This case was updated by someone else; reload and try again")
        updated = current.model_copy(update={"status": payload.status, "review_text": payload.review_text, "reviewed_by": actor.subject,
                                             "reviewed_at": datetime.now(UTC), "version": current.version + 1})
        self.store.put("expert_cases", case_id, updated.model_dump(mode="json"))
        return updated

    def farmer_cases(self, actor: Actor, farm_id: str) -> list[dict[str, Any]]:
        self.farm(actor, farm_id)
        out = []
        for item in self.store.list("expert_cases", filters={"farm_id": farm_id, "owner_subject": actor.subject}, limit=100):
            case = ExpertCase.model_validate(item)
            diagnosis = self.store.get("diagnoses", case.diagnosis_id) or {}
            out.append(case.model_dump(mode="json") | {"suspected_condition": diagnosis.get("suspected_condition"),
                                                       "crop": diagnosis.get("crop")})
        return out

    # ------------------------------------------------------------------ practices
    def create_practice(self, actor: Actor, payload: PracticeCreate) -> Practice:
        record = Practice(**payload.model_dump(), node_id=actor.node_id, created_by=actor.subject)
        self.store.put("practices", record.id, record.model_dump(mode="json"))
        return record

    def practices(self, actor: Actor) -> list[Practice]:
        return [Practice.model_validate(item) for item in self.store.list("practices", filters={"node_id": actor.node_id}, limit=100)]

    def review_practice(self, actor: Actor, practice_id: str, payload: PracticeReview) -> Practice:
        value = self.store.get("practices", practice_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Practice not found")
        current = Practice.model_validate(value)
        updated = current.model_copy(update={"review_status": "reviewed" if payload.approve else "draft", "reviewed_by": actor.subject,
                                             "reviewed_at": datetime.now(UTC) if payload.approve else None, "version": current.version + 1})
        self.store.put("practices", practice_id, updated.model_dump(mode="json"))
        return updated

    def practice_outcomes(self, node_id: str) -> dict[str, Counter]:
        outcomes: dict[str, Counter] = defaultdict(Counter)
        for advisory in self.store.list("advisories", filters={"node_id": node_id}, limit=500):
            for action in advisory.get("actions", []):
                counter = outcomes[action.get("practice_id", "")]
                if action.get("status") in ("accepted", "completed"):
                    counter["accepted"] += 1
                if action.get("status") == "declined":
                    counter["declined"] += 1
                if action.get("outcome"):
                    counter["outcomes"] += 1
                    counter[action["outcome"]] += 1
        return outcomes

    def export_practice(self, actor: Actor, practice_id: str) -> dict[str, Any]:
        value = self.store.get("practices", practice_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Practice not found")
        practice = Practice.model_validate(value)
        if practice.review_status != "reviewed" or not practice.reviewed_at:
            raise ValueError("Only reviewed practices can be exported")
        bundle: dict[str, Any] = {
            "schema_version": "1.0.0",
            "bundle_id": practice.id,
            "practice_version": practice.version,
            "vocabulary_version": "c2c-1",
            "origin": {"node_id": practice.node_id, "country_code": self.settings.node_country_code,
                       "organization_label": self.settings.node_label, "exported_at": datetime.now(UTC).isoformat()},
            "created_at": datetime.now(UTC).isoformat(),
            "data_mode": "curated",
            "license": practice.license,
            "title": practice.title,
            "summary": practice.summary,
            "practice_code": practice.practice_code,
            "applicability": {"country_codes": practice.country_codes, "state_codes": practice.state_codes, "crops": practice.crops,
                              "seasons": practice.seasons, "water_contexts": practice.water_contexts},
            "steps": [{"instruction": step} for step in practice.steps],
            "contraindications": practice.contraindications,
            "evidence": [{"citation_url": url} for url in practice.source_urls],
            "origin_review": {"status": "reviewed", "reviewer_subject": practice.reviewed_by, "reviewed_at": practice.reviewed_at.isoformat()},
        }
        if practice.practice_code:
            counts = self.practice_outcomes(actor.node_id).get(practice.practice_code, Counter())
            if counts["outcomes"] >= MIN_GROUP_SIZE:
                bundle["field_evidence"] = {"actions_accepted": counts["accepted"], "outcomes_reported": counts["outcomes"],
                                            "worked": counts["worked"], "partly": counts["partly"], "did_not_work": counts["did_not_work"],
                                            "minimum_group_size": MIN_GROUP_SIZE}
        return bundle

    # ------------------------------------------------------------------ exchange (practices and packs)
    def import_bundle(self, actor: Actor, bundle: dict[str, Any], source_url: str | None = None) -> ExchangeImport:
        bundle_type = "agronomy_pack" if "pack_id" in bundle else "practice"
        schema = _schema("agronomy-pack.schema.json" if bundle_type == "agronomy_pack" else "practice-bundle.schema.json")
        errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(bundle), key=lambda error: list(error.path))
        if errors:
            raise ValueError("Invalid bundle: " + "; ".join(f"{'/'.join(map(str, e.path)) or 'root'}: {e.message}" for e in errors[:5]))
        digest = _digest(bundle)
        if self.store.list("exchange_imports", filters={"node_id": actor.node_id, "digest": digest}, limit=1):
            raise RuntimeError("This exact bundle has already been imported")
        findings: list[str] = []
        if bundle_type == "agronomy_pack":
            catalog = crop_catalog()
            unknown = [c["crop_id"] for c in bundle["crops"] if c["crop_id"] not in catalog
                       or catalog[c["crop_id"]]["scientific_name"] != c["scientific_name"]]
            if unknown:
                findings.append(f"Crops not in this node's catalog or with a different scientific name: {', '.join(unknown)}")
            if (bundle.get("origin") or {}).get("node_id") == self.settings.node_id:
                findings.append("This pack was exported by this same node")
        elif self.settings.node_country_code not in bundle["applicability"]["country_codes"]:
            findings.append("This country is outside the practice's declared applicability")
        record = ExchangeImport(node_id=actor.node_id, imported_by=actor.subject, digest=digest, bundle_type=bundle_type,
                                source_url=source_url, bundle=bundle, compatibility_findings=findings)
        self.store.put("exchange_imports", record.id, record.model_dump(mode="json"))
        return record

    def imports(self, actor: Actor) -> list[ExchangeImport]:
        return [ExchangeImport.model_validate(item) for item in self.store.list("exchange_imports", filters={"node_id": actor.node_id}, limit=100)]

    def review_import(self, actor: Actor, import_id: str, payload: ExchangeReview) -> ExchangeImport:
        value = self.store.get("exchange_imports", import_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Import not found")
        current = ExchangeImport.model_validate(value)
        if payload.approve and current.compatibility_findings:
            raise ValueError("Resolve the compatibility findings before approving")
        updated = current.model_copy(update={"local_review_status": "approved" if payload.approve else "rejected",
                                             "local_review_note": payload.note, "local_reviewed_by": actor.subject})
        self.store.put("exchange_imports", import_id, updated.model_dump(mode="json"))
        if payload.approve and current.bundle_type == "agronomy_pack":
            pack = current.bundle
            code = pack["region"]["subdivision_code"]
            for item in self._imported_packs():
                if item.get("subdivision_code") == code:
                    self.store.put("packs", item["id"], item | {"status": "superseded"})
            doc_id = f"{pack['pack_id']}_v{pack['pack_version']}"
            self.store.put("packs", doc_id, {"id": doc_id, "node_id": actor.node_id, "subdivision_code": code, "status": "active",
                                             "pack": pack, "import_id": import_id, "approved_by": actor.subject,
                                             "created_at": datetime.now(UTC).isoformat()})
        elif payload.approve and current.bundle_type == "practice":
            bundle = current.bundle
            practice = Practice(
                title=bundle["title"], summary=bundle["summary"], country_codes=bundle["applicability"]["country_codes"],
                state_codes=bundle["applicability"]["state_codes"], crops=bundle["applicability"]["crops"],
                seasons=bundle["applicability"]["seasons"], water_contexts=bundle["applicability"]["water_contexts"],
                steps=[step["instruction"] for step in bundle["steps"]], contraindications=bundle["contraindications"],
                source_urls=[item["citation_url"] for item in bundle["evidence"]], license=bundle["license"],
                practice_code=bundle.get("practice_code"), node_id=actor.node_id,
                created_by=f"imported:{bundle['origin']['node_id']}", review_status="reviewed", reviewed_by=actor.subject,
                reviewed_at=datetime.now(UTC),
            )
            self.store.put("practices", practice.id, practice.model_dump(mode="json"))
        return updated

    # ------------------------------------------------------------------ network
    def node_manifest(self) -> dict[str, Any]:
        base = (self.settings.public_base_url or "").rstrip("/")
        published = [pack for code, pack in bundled_packs().items() if code in self.settings.node_subdivision_list]
        practices = [Practice.model_validate(item) for item in self.store.list("practices", filters={"node_id": self.settings.node_id}, limit=100)]
        return {
            "protocol": "kisanai-agrin-node/1.0",
            "node_id": self.settings.node_id,
            "label": self.settings.node_label,
            "country_code": self.settings.node_country_code,
            "subdivisions": self.settings.node_subdivision_list,
            "schemas": {"agronomy_pack": "urn:kisanai-c2c:agronomy-pack:1.0.0", "practice_bundle": "urn:kisanai-c2c:practice-bundle:1.0.0"},
            "packs": [{"pack_id": p["pack_id"], "pack_version": p["pack_version"], "subdivision_code": p["region"]["subdivision_code"],
                       "name": p["region"]["name"], "crops": len(p["crops"]), "digest": _digest(p),
                       "url": f"{base}/api/v1/network/packs/{p['pack_id']}"} for p in published],
            "practices": [{"bundle_id": p.id, "title": p.title, "url": f"{base}/api/v1/network/practices/{p.id}"}
                          for p in practices if p.review_status == "reviewed" and not p.created_by.startswith("imported:")],
            "signals_url": f"{base}/api/v1/network/signals",
            "privacy": "No farmer identity, location or field geometry is published. Aggregates are suppressed below 5 records.",
        }

    def public_practice(self, practice_id: str) -> dict[str, Any]:
        system = Actor(subject="system", node_id=self.settings.node_id, roles={Role.expert})
        return self.export_practice(system, practice_id)

    def peers(self) -> list[dict[str, Any]]:
        out = []
        for url in self.settings.peer_node_list:
            try:
                response = requests.get(f"{url}/.well-known/agrin-node", timeout=8)
                response.raise_for_status()
                out.append({"url": url, "status": "online", "manifest": response.json()})
            except Exception as exc:  # noqa: BLE001
                out.append({"url": url, "status": "unreachable", "error": str(exc)[:160]})
        return out

    def import_from_peer(self, actor: Actor, peer_url: str, kind: str, item_id: str) -> ExchangeImport:
        peer = peer_url.rstrip("/")
        if peer not in self.settings.peer_node_list:
            raise PermissionError("This node is not in the approved peer list")
        if kind not in {"packs", "practices"} or not item_id.replace("_", "").isalnum():
            raise ValueError("Invalid item")
        url = f"{peer}/api/v1/network/{kind}/{item_id}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            raise LookupError(f"Peer returned {response.status_code} for {url}")
        if len(response.content) > 1_000_000:
            raise ValueError("Bundle is too large")
        return self.import_bundle(actor, response.json(), source_url=url)

    def shared_signals(self) -> dict[str, Any]:
        """Anonymous district-level crop-health signals for peer nodes (k >= MIN_GROUP_SIZE)."""
        since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        groups: Counter = Counter()
        for item in self.store.list("diagnoses", filters={"node_id": self.settings.node_id}, limit=500):
            if str(item.get("created_at")) < since or not item.get("district"):
                continue
            groups[(item.get("subdivision_code"), item["district"], item.get("crop"), item.get("category"))] += 1
        signals = [{"subdivision_code": sub, "district": district, "crop": crop, "category": category, "reports": count}
                   for (sub, district, crop, category), count in groups.items() if count >= MIN_GROUP_SIZE]
        return {"node_id": self.settings.node_id, "window_days": 30, "minimum_group_size": MIN_GROUP_SIZE,
                "generated_at": datetime.now(UTC).isoformat(), "signals": signals}

    # ------------------------------------------------------------------ dashboard
    def dashboard(self, actor: Actor) -> dict[str, Any]:
        node = actor.node_id
        farms = self.store.list("farms", filters={"node_id": node}, limit=500)
        diagnoses = self.store.list("diagnoses", filters={"node_id": node}, limit=500)
        cases = self.store.list("expert_cases", filters={"node_id": node}, limit=500)
        since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        recent = [d for d in diagnoses if str(d.get("created_at")) >= since]
        by_district = Counter((f.get("state_name"), f.get("district")) for f in farms)
        diag_groups = Counter((d.get("district") or "unknown",
                               crop_name(d.get("crop") or "", "en-IN") if d.get("crop") not in (None, "auto-detect") else "Unspecified",
                               d.get("category") or "unclear") for d in recent)
        conditions = Counter((d.get("condition_en") or d.get("suspected_condition") or "unclear").strip().lower() for d in recent if d.get("category") not in (None, "healthy"))
        practice_rows = []
        for pid, counts in self.practice_outcomes(node).items():
            if not pid:
                continue
            practice_rows.append({"practice_id": pid, "name": practice_catalog().get(pid, {}).get("names", {}).get("en", pid),
                                  "accepted": counts["accepted"], "declined": counts["declined"], "outcomes": counts["outcomes"],
                                  "worked": counts["worked"], "partly": counts["partly"], "did_not_work": counts["did_not_work"]})
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "node_id": node,
            "totals": {"farms": len(farms), "diagnoses_30d": len(recent), "open_cases": sum(1 for c in cases if c.get("status") != "resolved"),
                       "resolved_cases": sum(1 for c in cases if c.get("status") == "resolved"),
                       "soil_tests": len(self.store.list("soil_tests", filters={"node_id": node}, limit=500))},
            "farms_by_district": [{"state": s, "district": d, "farms": n} for (s, d), n in by_district.most_common(30)],
            "diagnoses_by_district": [{"district": d, "crop": c, "category": cat, "reports": n} for (d, c, cat), n in diag_groups.most_common(30)],
            "top_conditions": [{"condition": c, "reports": n} for c, n in conditions.most_common(10)],
            "practice_adoption": sorted(practice_rows, key=lambda row: row["accepted"], reverse=True),
            "shared_signals_preview": self.shared_signals()["signals"],
            "minimum_group_size": MIN_GROUP_SIZE,
        }

    # ------------------------------------------------------------------ catalog
    def crop_catalog_view(self, locale: str, country_code: str | None, state_code: str | None) -> dict[str, Any]:
        code = subdivision_code(country_code, state_code)
        pack = bundled_packs().get(code or "")
        regional = {entry["crop_id"] for entry in pack["crops"]} if pack else set()
        crops = [{"id": cid, "name": crop_name(cid, locale), "names": crop["names"], "scientific_name": crop["scientific_name"],
                  "group": crop["group"], "regional": cid in regional}
                 for cid, crop in crop_catalog().items()]
        crops.sort(key=lambda c: (not c["regional"], c["group"], c["name"]))
        return {"subdivision_code": code, "has_regional_pack": bool(pack), "crops": crops}

    # ------------------------------------------------------------------ seed data
    def seed_default_practices_if_empty(self) -> None:
        """Seed reviewed regenerative practices relevant to this node's states so its library is not empty."""
        if self.store.list("practices", filters={"node_id": self.settings.node_id}, limit=1):
            return
        now = datetime.now(UTC)
        defaults = [
            dict(id="practice_bbf_drainage", practice_code="broad-bed-furrow",
                 title="Broad Bed and Furrow (BBF) on black soils",
                 summary="Raised beds about 1.2-1.5 m wide separated by furrows drain excess water in wet spells and conserve moisture in dry spells on heavy Vertisols.",
                 state_codes=["MH", "TG", "KA", "MP"], crops=["soybean", "cotton", "pigeon_pea", "chickpea"], seasons=["kharif", "rabi"],
                 water_contexts=["rainfed", "supplemental_irrigation"],
                 steps=["Form beds with a BBF planter or ridger before sowing, with furrows along a gentle slope.",
                        "Sow 2-4 crop rows on each bed; keep furrows unplanted.",
                        "Keep furrow outlets open so excess rain drains to a grassed waterway or farm pond."],
                 contraindications=["Needs contour bunding on slopes steeper than about 1.5%.", "Of little benefit on light sandy soils."],
                 source_urls=["https://www.icrisat.org/"], reviewed_by="seed:icrisat-published-guidance"),
            dict(id="practice_cotton_tur_intercrop", practice_code="intercropping-pulses",
                 title="Cotton with pigeon pea strip intercropping",
                 summary="Rows of pigeon pea between cotton strips add biological nitrogen, diversify income and break pest build-up in rainfed cotton.",
                 state_codes=["MH", "TG", "GJ", "KA"], crops=["cotton", "pigeon_pea"], seasons=["kharif"],
                 water_contexts=["rainfed", "supplemental_irrigation"],
                 steps=["Sow cotton and pigeon pea together at monsoon onset in a 6:1 or 8:2 row ratio.",
                        "Keep recommended spacing for each crop so pigeon pea does not shade cotton.",
                        "Harvest cotton in pickings; harvest pigeon pea after cotton."],
                 contraindications=["Avoid indeterminate climbing pulse varieties that smother cotton."],
                 source_urls=["https://cicr.org.in/"], reviewed_by="seed:icar-cicr-published-guidance"),
            dict(id="practice_residue_mulching", practice_code="residue-retention",
                 title="Crop residue mulching instead of burning",
                 summary="Keeping chopped residue on the soil surface cuts evaporation, protects soil from rain impact and feeds soil life; burning destroys organic matter and pollutes the air.",
                 state_codes=["MH", "PB", "HR", "UP", "MP", "KA"], crops=["sorghum", "pearl_millet", "chickpea", "wheat", "maize", "rice"],
                 seasons=["kharif", "rabi"], water_contexts=["rainfed", "supplemental_irrigation", "irrigated"],
                 steps=["Chop and spread the previous crop's residue evenly.", "Sow the next crop with a zero-till or Happy Seeder drill through the residue.",
                        "Do not burn residue."],
                 contraindications=["Very thick wet mulch on poorly drained soil can encourage seedling rot."],
                 source_urls=["https://www.fao.org/conservation-agriculture/en/"], reviewed_by="seed:fao-conservation-agriculture"),
        ]
        served = {code.split("-", 1)[-1] for code in self.settings.node_subdivision_list}
        for item in defaults:
            if served and not served & set(item["state_codes"]):
                continue
            practice = Practice(**item, country_codes=["IN"], license="CC-BY-4.0", node_id=self.settings.node_id, created_by="system-seed",
                                review_status="reviewed", reviewed_at=now)
            self.store.put("practices", practice.id, practice.model_dump(mode="json"))
