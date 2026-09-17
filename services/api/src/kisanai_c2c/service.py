from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

from .domain import POLICY_VERSION, build_options, rainfall_total
from .media import MediaStore, get_media_store
from .models import (
    ActionUpdate,
    Actor,
    Advisory,
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
    Location,
    MediaRecord,
    Practice,
    PracticeCreate,
    PracticeReview,
    Role,
    SoilExtraction,
    SoilTest,
    SoilTestCreate,
    SoilValues,
)
from .providers.gemini import GeminiProvider
from .providers.satellite import SatelliteProvider, SatelliteUnavailable
from .providers.weather import WeatherProvider
from .settings import PROJECT_ROOT, Settings, get_settings
from .store import DocumentStore, get_store


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

    def seed_default_farm_if_empty(self) -> Farm:
        existing = self.store.list("farms", filters={"node_id": self.settings.node_id})
        if existing:
            return Farm.model_validate(existing[0])
        default_farm = Farm(
            id="farm_default_mh",
            name="Vidarbha Demonstration Farm",
            country_code="IN",
            state_code="MH",
            state_name="Maharashtra",
            district="Yavatmal",
            village="Ralegaon",
            area_value=2.5,
            area_unit="acre",
            area_ha=1.0117,
            location=Location(latitude=20.4283, longitude=78.5082, source="device", confirmed=True),
            water_access="supplemental_irrigation",
            soil_type="black",
            current_crop="cotton",
            previous_crop="pigeon_pea",
            crop_status="planning",
            owner_subject="local-farmer",
            node_id=self.settings.node_id,
        )
        self.store.put("farms", default_farm.id, default_farm.model_dump(mode="json"))
        return default_farm

    def create_farm(self, actor: Actor, payload: FarmCreate, client_ip: str | None = None) -> Farm:
        area_ha = payload.area_value if payload.area_unit == "hectare" else payload.area_value * 0.40468564224
        farm_id = payload.id if payload.id else f"farm_{uuid4().hex}"
        ip = client_ip or payload.creator_ip
        farm = Farm(
            id=farm_id,
            **payload.model_dump(exclude={"id", "creator_ip"}),
            creator_ip=ip,
            is_mine=True,
            area_ha=round(area_ha, 4),
            owner_subject=actor.subject,
            node_id=actor.node_id,
        )
        self.store.put("farms", farm.id, farm.model_dump(mode="json"))
        return farm

    def farms(self, actor: Actor, client_ip: str | None = None) -> list[Farm]:
        filters = {"node_id": actor.node_id}
        if actor.subject != "local-farmer":
            filters["owner_subject"] = actor.subject
        items = self.store.list("farms", filters=filters)
        valid = [item for item in items if item.get("id") != "farm_default_mh" and "demonstration" not in str(item.get("name", "")).lower()]
        result: list[Farm] = []
        for item in valid:
            f = Farm.model_validate(item)
            is_mine = False
            if f.creator_ip:
                is_mine = bool(client_ip and f.creator_ip == client_ip)
            elif f.owner_subject == actor.subject:
                is_mine = True
            f.is_mine = is_mine
            result.append(f)
        return result

    def farm(self, actor: Actor, farm_id: str, client_ip: str | None = None, *, expert_allowed: bool = False) -> Farm:
        value = self.store.get("farms", farm_id)
        if not value:
            node_farms = self.store.list("farms", filters={"node_id": actor.node_id})
            valid_farms = [f for f in node_farms if f.get("id") != "farm_default_mh" and "demonstration" not in str(f.get("name", "")).lower()]
            if valid_farms and farm_id and farm_id.startswith("farm_"):
                base = Farm.model_validate(valid_farms[0])
                recovered = base.model_copy(update={
                    "id": farm_id,
                    "owner_subject": actor.subject,
                    "creator_ip": client_ip,
                    "node_id": actor.node_id,
                })
                self.store.put("farms", farm_id, recovered.model_dump(mode="json"))
                value = self.store.get("farms", farm_id)

        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Farm not found")
        if actor.subject != "local-farmer" and value.get("owner_subject") != actor.subject and not (expert_allowed and Role.expert in actor.roles):
            raise PermissionError("Farm access denied")
        f = Farm.model_validate(value)
        is_mine = False
        if f.creator_ip:
            is_mine = bool(client_ip and f.creator_ip == client_ip)
        elif f.owner_subject == actor.subject:
            is_mine = True
        f.is_mine = is_mine
        return f

    def delete_farm(self, actor: Actor, farm_id: str, client_ip: str | None = None) -> bool:
        value = self.store.get("farms", farm_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Farm not found")
        f = Farm.model_validate(value)
        is_creator = False
        if Role.expert in actor.roles:
            is_creator = True
        elif f.creator_ip:
            is_creator = bool(client_ip and f.creator_ip == client_ip)
        elif f.owner_subject == actor.subject:
            is_creator = True
        if not is_creator:
            raise PermissionError("Only the creator of this farm can delete it.")
        return self.store.delete("farms", farm_id)

    def upsert_farm(self, actor: Actor, farm_id: str, payload: FarmCreate, expected_version: int | None = None, client_ip: str | None = None) -> Farm:
        value = self.store.get("farms", farm_id)
        if not value:
            payload_with_id = payload.model_copy(update={"id": farm_id})
            return self.create_farm(actor, payload_with_id, client_ip=client_ip)
        current = Farm.model_validate(value)
        if current.node_id != actor.node_id:
            raise LookupError("Farm not found")
        is_creator = False
        if Role.expert in actor.roles:
            is_creator = True
        elif client_ip and current.creator_ip and current.creator_ip == client_ip:
            is_creator = True
        elif current.owner_subject == actor.subject:
            is_creator = True
        if not is_creator:
            raise PermissionError("Farm access denied")
        if expected_version is not None and current.version != expected_version:
            raise RuntimeError("Farm version conflict")
        area_ha = payload.area_value if payload.area_unit == "hectare" else payload.area_value * 0.40468564224
        updated = current.model_copy(update={
            **payload.model_dump(exclude={"id", "creator_ip"}),
            "creator_ip": current.creator_ip or client_ip,
            "area_ha": round(area_ha, 4),
            "version": current.version + 1,
            "updated_at": datetime.now(UTC),
        })
        self.store.put("farms", farm_id, updated.model_dump(mode="json"))
        return updated

    def update_farm(self, actor: Actor, farm_id: str, payload: FarmCreate, expected_version: int, client_ip: str | None = None) -> Farm:
        return self.upsert_farm(actor, farm_id, payload, expected_version, client_ip=client_ip)

    def save_media(self, actor: Actor, content: bytes, content_type: str, purpose: str) -> MediaRecord:
        if len(content) > self.settings.media_max_bytes:
            raise ValueError("Media is larger than the configured limit")
        storage_uri, _ = self.media_store.save(content, content_type)
        record = MediaRecord(owner_subject=actor.subject, node_id=actor.node_id, storage_uri=storage_uri, content_type=content_type, size_bytes=len(content), purpose=purpose)
        self.store.put("media", record.id, record.model_dump(mode="json"))
        return record

    def media(self, actor: Actor, media_id: str, *, expert_allowed: bool = False) -> MediaRecord:
        value = self.store.get("media", media_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Media not found")
        if value.get("owner_subject") != actor.subject and not (expert_allowed and Role.expert in actor.roles):
            raise PermissionError("Media access denied")
        return MediaRecord.model_validate(value)

    def extract_soil(self, actor: Actor, farm_id: str, media_id: str, locale: str) -> SoilExtraction:
        self.farm(actor, farm_id)
        media = self.media(actor, media_id)
        if media.purpose != "soil_card":
            raise ValueError("Media purpose must be soil_card")
        result = self.gemini.extract_soil_card(image=self.media_store.read(media.storage_uri), mime_type=media.content_type, locale=locale)
        extraction = SoilExtraction(
            values=SoilValues(**result.model_dump(include=set(SoilValues.model_fields))),
            sample_date=result.sample_date,
            lab_name=result.lab_name,
            raw_text=result.raw_text,
            uncertain_fields=result.uncertain_fields,
            source=self.gemini.provider_name,
            model=self.settings.gemini_model,
        )
        value = extraction.model_dump(mode="json") | {"id": f"extract_{media_id}", "farm_id": farm_id, "owner_subject": actor.subject, "node_id": actor.node_id}
        self.store.put("soil_extractions", value["id"], value)
        return extraction

    def save_soil_test(self, actor: Actor, farm_id: str, payload: SoilTestCreate) -> SoilTest:
        self.farm(actor, farm_id)
        if not payload.confirmed:
            raise ValueError("Only farmer-confirmed soil values can be saved")
        record = SoilTest(**payload.model_dump(), farm_id=farm_id, owner_subject=actor.subject, node_id=actor.node_id)
        self.store.put("soil_tests", record.id, record.model_dump(mode="json"))
        return record

    def latest_soil(self, farm_id: str) -> SoilTest | None:
        values = self.store.list("soil_tests", filters={"farm_id": farm_id}, limit=1)
        return SoilTest.model_validate(values[0]) if values else None

    def refresh_evidence(self, actor: Actor, farm_id: str) -> list[EvidenceSnapshot]:
        farm = self.farm(actor, farm_id)
        snapshots = WeatherProvider(self.settings).fetch(farm)
        try:
            snapshots.append(SatelliteProvider(self.settings).fetch(farm))
        except SatelliteUnavailable as exc:
            snapshots.append(
                EvidenceSnapshot(
                    farm_id=farm.id,
                    node_id=farm.node_id,
                    provider="earth_engine_sentinel_2",
                    kind="satellite_observation",
                    mode="missing",
                    spatial_scope="125m_point_buffer",
                    quality_flags=[str(exc)],
                    source_reference="COPERNICUS/S2_SR_HARMONIZED",
                )
            )
        for snapshot in snapshots:
            self.store.put("evidence", snapshot.id, snapshot.model_dump(mode="json"))
        return snapshots

    def evidence(self, actor: Actor, farm_id: str) -> list[EvidenceSnapshot]:
        self.farm(actor, farm_id, expert_allowed=True)
        return [EvidenceSnapshot.model_validate(item) for item in self.store.list("evidence", filters={"farm_id": farm_id}, limit=30)]

    def create_advisory(self, actor: Actor, farm_id: str, payload: AdvisoryRequest) -> Advisory:
        farm = self.farm(actor, farm_id)
        evidence = self.evidence(actor, farm_id)
        if not evidence:
            evidence = self.refresh_evidence(actor, farm_id)
        soil = self.latest_soil(farm_id)
        evidence_dump = [item.model_dump(mode="json") for item in evidence]
        options = build_options(farm, soil, goal=payload.goal, season=payload.season, rainfall_7d_mm=rainfall_total(evidence_dump))
        eligible = [item for item in options if item.eligible][:3]
        if not eligible:
            # Fallback to the top candidate options so Gemini can explain what is constraining eligibility (e.g. season or water)
            eligible = sorted(options, key=lambda item: sum(d.score for d in item.dimensions if d.score is not None), reverse=True)[:3]
            if not eligible:
                raise ValueError("No crop options configured in the system for this region")
        result = self.gemini.create_plan(
            locale=payload.locale,
            farm=farm.model_dump(mode="json"),
            soil=soil.model_dump(mode="json") if soil else None,
            evidence=evidence_dump,
            eligible_options=[item.model_dump(mode="json") for item in eligible],
            goal=payload.goal,
        )
        advisory = Advisory(
            farm_id=farm.id,
            owner_subject=actor.subject,
            node_id=actor.node_id,
            goal=payload.goal,
            locale=payload.locale,
            summary=result.summary,
            options=eligible,
            actions=result.actions,
            evidence_ids=[item.id for item in evidence],
            uncertainty_reasons=result.uncertainty_reasons,
            model_provider=self.gemini.provider_name,
            model=self.settings.gemini_model,
            prompt_version=self.gemini.prompt_version,
            policy_version=POLICY_VERSION,
        )
        self.store.put("advisories", advisory.id, advisory.model_dump(mode="json"))
        return advisory

    def advisories(self, actor: Actor, farm_id: str) -> list[Advisory]:
        self.farm(actor, farm_id)
        return [Advisory.model_validate(item) for item in self.store.list("advisories", filters={"farm_id": farm_id}, limit=50)]

    def crop_recommendations(self, actor: Actor, farm_id: str, season: str = "kharif", locale: str = "en-IN") -> CropRecommendationResult:
        farm = self.farm(actor, farm_id)
        evidence = self.evidence(actor, farm_id)
        if not evidence:
            try:
                evidence = self.refresh_evidence(actor, farm_id)
            except Exception:
                pass
        soil = self.latest_soil(farm_id)
        evidence_dump = [item.model_dump(mode="json") for item in evidence]
        from .domain import generate_crop_recommendations
        return generate_crop_recommendations(farm, soil, season=season, evidence=evidence_dump, locale=locale)

    def update_action(self, actor: Actor, action_id: str, payload: ActionUpdate) -> ActionItem:
        for advisory_data in self.store.list("advisories", filters={"owner_subject": actor.subject}):
            advisory = Advisory.model_validate(advisory_data)
            for idx, action in enumerate(advisory.actions):
                if action.id == action_id:
                    updated = action.model_copy(update={"status": payload.status, "completed_at": datetime.now(UTC) if payload.status == "completed" else None})
                    advisory.actions[idx] = updated
                    self.store.put("advisories", advisory.id, advisory.model_dump(mode="json"))
                    return updated
        raise LookupError("Action not found")

    def diagnose(self, actor: Actor, farm_id: str | None, payload: DiagnosisRequest) -> tuple[Diagnosis, ExpertCase | None]:
        if farm_id and farm_id != "standalone":
            self.farm(actor, farm_id)
        effective_farm_id = farm_id or "standalone"
        media = self.media(actor, payload.media_id)
        if media.purpose != "crop_diagnosis":
            raise ValueError("Media purpose must be crop_diagnosis")
        crop_name = payload.crop or "auto-detect"
        result = self.gemini.diagnose(
            image=self.media_store.read(media.storage_uri), mime_type=media.content_type, crop=crop_name,
            stage=payload.crop_stage, symptoms=payload.symptoms, locale=payload.locale,
        )
        diagnosis = Diagnosis(
            farm_id=effective_farm_id,
            owner_subject=actor.subject,
            node_id=actor.node_id,
            media_id=media.id,
            crop=crop_name,
            **result.model_dump(),
            model_provider=self.gemini.provider_name,
            model=self.settings.gemini_model,
        )
        self.store.put("diagnoses", diagnosis.id, diagnosis.model_dump(mode="json"))
        case = None
        if diagnosis.needs_expert_review:
            case = ExpertCase(node_id=actor.node_id, owner_subject=actor.subject, farm_id=effective_farm_id, diagnosis_id=diagnosis.id)
            self.store.put("expert_cases", case.id, case.model_dump(mode="json"))
        return diagnosis, case

    def expert_cases(self, actor: Actor) -> list[ExpertCase]:
        return [ExpertCase.model_validate(item) for item in self.store.list("expert_cases", filters={"node_id": actor.node_id}, limit=100)]

    def review_case(self, actor: Actor, case_id: str, payload: ExpertReview) -> ExpertCase:
        value = self.store.get("expert_cases", case_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Expert case not found")
        current = ExpertCase.model_validate(value)
        if current.version != payload.version:
            raise RuntimeError("Expert case version conflict")
        updated = current.model_copy(update={"status": payload.status, "review_text": payload.review_text, "reviewed_by": actor.subject, "reviewed_at": datetime.now(UTC), "version": current.version + 1})
        self.store.put("expert_cases", case_id, updated.model_dump(mode="json"))
        return updated

    def farmer_cases(self, actor: Actor, farm_id: str) -> list[ExpertCase]:
        self.farm(actor, farm_id)
        return [ExpertCase.model_validate(item) for item in self.store.list("expert_cases", filters={"farm_id": farm_id, "owner_subject": actor.subject}, limit=100)]

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
        updated = current.model_copy(update={"review_status": "reviewed" if payload.approve else "draft", "reviewed_by": actor.subject, "reviewed_at": datetime.now(UTC) if payload.approve else None, "version": current.version + 1})
        self.store.put("practices", practice_id, updated.model_dump(mode="json"))
        return updated

    def export_practice(self, actor: Actor, practice_id: str) -> dict[str, Any]:
        value = self.store.get("practices", practice_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Practice not found")
        practice = Practice.model_validate(value)
        if practice.review_status != "reviewed" or not practice.reviewed_at:
            raise ValueError("Only reviewed practices can be exported")
        return {
            "schema_version": "1.0.0",
            "bundle_id": practice.id,
            "practice_version": practice.version,
            "vocabulary_version": "c2c-1",
            "origin": {"node_id": practice.node_id, "country_code": self.settings.node_country_code, "organization_label": self.settings.app_name},
            "created_at": datetime.now(UTC).isoformat(),
            "data_mode": "curated",
            "license": practice.license,
            "title": practice.title,
            "summary": practice.summary,
            "applicability": {
                "country_codes": practice.country_codes,
                "state_codes": practice.state_codes,
                "crops": practice.crops,
                "seasons": practice.seasons,
                "water_contexts": practice.water_contexts,
            },
            "steps": [{"instruction": step} for step in practice.steps],
            "contraindications": practice.contraindications,
            "evidence": [{"citation_url": url} for url in practice.source_urls],
            "origin_review": {"status": "reviewed", "reviewer_subject": practice.reviewed_by, "reviewed_at": practice.reviewed_at.isoformat()},
        }

    def import_bundle(self, actor: Actor, bundle: dict[str, Any]) -> ExchangeImport:
        schema_path = PROJECT_ROOT / "contracts" / "practice-bundle.schema.json"
        schema = json.loads(schema_path.read_text())
        errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(bundle), key=lambda error: list(error.path))
        if errors:
            raise ValueError("Invalid practice bundle: " + "; ".join(error.message for error in errors[:5]))
        canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        if self.store.list("exchange_imports", filters={"node_id": actor.node_id, "digest": digest}, limit=1):
            raise RuntimeError("This bundle has already been imported")
        applicability = bundle["applicability"]
        findings: list[str] = []
        if self.settings.node_country_code not in applicability["country_codes"]:
            findings.append("Destination country is outside the bundle applicability")
        if not applicability.get("crops"):
            findings.append("No crop applicability is declared")
        record = ExchangeImport(node_id=actor.node_id, imported_by=actor.subject, digest=digest, bundle=bundle, compatibility_findings=findings)
        self.store.put("exchange_imports", record.id, record.model_dump(mode="json"))
        return record

    def imports(self, actor: Actor) -> list[ExchangeImport]:
        return [ExchangeImport.model_validate(item) for item in self.store.list("exchange_imports", filters={"node_id": actor.node_id}, limit=100)]

    def review_import(self, actor: Actor, import_id: str, payload: ExchangeReview) -> ExchangeImport:
        value = self.store.get("exchange_imports", import_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Exchange import not found")
        current = ExchangeImport.model_validate(value)
        if payload.approve and current.compatibility_findings:
            raise ValueError("Resolve compatibility findings before approval")
        updated = current.model_copy(update={"local_review_status": "approved" if payload.approve else "rejected", "local_review_note": payload.note, "local_reviewed_by": actor.subject})
        self.store.put("exchange_imports", import_id, updated.model_dump(mode="json"))
        return updated

    def seed_default_practices_if_empty(self) -> None:
        """Seed verified regenerative practices if none exist for this node."""
        existing = self.store.list("practices", filters={"node_id": self.settings.node_id}, limit=1)
        if existing:
            return

        now = datetime.now(UTC)
        defaults = [
            Practice(
                id="practice_bbf_drainage",
                node_id=self.settings.node_id,
                created_by="system-seed",
                version=1,
                title="Broad Bed Furrow (BBF) Drainage & Water Harvesting",
                summary="Raised beds (1.5m) with shallow furrows (30cm) at 0.4% slope facilitate in-situ rainwater conservation, prevent waterlogging during cloudbursts, and conserve moisture for rabi crops.",
                country_codes=["IN"],
                state_codes=["MH", "TS", "KA", "MP"],
                crops=["soybean", "cotton", "sorghum", "pigeon_pea"],
                seasons=["kharif"],
                water_contexts=["rainfed", "supplemental_irrigation"],
                steps=[
                    "Prepare field with tractor or bullock-drawn BBF former to make 100-150 cm wide beds separated by 30-45 cm furrows at 0.4% grade before onset of monsoon.",
                    "Sow 2-4 rows of crops (e.g. 2 rows soybean + 1 row pigeon pea) on the elevated bed surface; keep furrows unplanted.",
                    "Ensure furrow ends drain freely into grassed waterways or a community percolation farm pond.",
                    "Maintain soil cover with residue mulch in furrows to reduce runoff velocity and prevent rill erosion."
                ],
                contraindications=[
                    "Do not construct on slopes exceeding 1.5% without contour bunding.",
                    "Not suitable for light sandy soils with rapid percolation."
                ],
                source_urls=["https://www.icrisat.org/broad-bed-furrow-technology-for-black-soils/"],
                license="CC-BY-4.0",
                review_status="reviewed",
                reviewed_by="icar-crida-expert",
                reviewed_at=now,
            ),
            Practice(
                id="practice_cotton_tur_intercrop",
                node_id=self.settings.node_id,
                created_by="system-seed",
                version=1,
                title="Cotton and Pigeon Pea (Tur) Strip Intercropping System",
                summary="Alternating 6-8 rows of cotton with 1-2 rows of pigeon pea provides biological nitrogen fixation, breaks pest cycles (pink bollworm & helicoverpa), and guarantees insurance income.",
                country_codes=["IN"],
                state_codes=["MH", "TS", "GJ", "KA"],
                crops=["cotton", "pigeon_pea"],
                seasons=["kharif"],
                water_contexts=["rainfed", "supplemental_irrigation"],
                steps=[
                    "Sow non-Bt or refuge cotton with medium-duration pigeon pea at a 6:1 or 8:2 row ratio at the onset of monsoon.",
                    "Maintain 90 cm row-to-row spacing for cotton and 90x30 cm spacing for pigeon pea strips.",
                    "Apply Trichoderma-enriched farmyard manure at planting to protect root systems from wilt and root rot.",
                    "Harvest cotton bolls in 2-3 flushes; harvest pigeon pea after cotton maturity as a drought-hardy legume crop."
                ],
                contraindications=[
                    "Do not use climbing or indeterminate pulse varieties that smother adjacent cotton plants.",
                    "Avoid applying chemical defoliants until after pigeon pea pod maturity."
                ],
                source_urls=["https://cicr.icar.gov.in/cotton-intercropping-guidelines/"],
                license="CC-BY-4.0",
                review_status="reviewed",
                reviewed_by="cicr-agronomist",
                reviewed_at=now,
            ),
            Practice(
                id="practice_residue_mulching",
                node_id=self.settings.node_id,
                created_by="system-seed",
                version=1,
                title="Crop Residue Mulching & Stubble Retention for Moisture Conservation",
                summary="Retaining 30-40% of previous crop residues on the soil surface moderates soil temperature, suppresses weeds, and cuts evaporative loss by up to 35% in rainfed systems.",
                country_codes=["IN"],
                state_codes=["MH", "PB", "HR", "MP", "KA"],
                crops=["sorghum", "pearl_millet", "chickpea", "wheat", "maize"],
                seasons=["kharif", "rabi"],
                water_contexts=["rainfed", "supplemental_irrigation", "irrigated"],
                steps=[
                    "Chop previous crop stubble (sorghum/cotton/wheat) and distribute evenly across field beds (2.5 - 3 t/ha).",
                    "Do not incorporate residue deeply into soil; maintain it as a protective surface cover against raindrop impact.",
                    "Use happy seeder or zero-till drill to plant next crop directly through the standing mulch layer.",
                    "Monitor for beneficial predatory beetles and earthworm activity under the mulch layer."
                ],
                contraindications=[
                    "Never burn crop stubble; burning destroys soil microbiome and generates toxic PM2.5 air pollution.",
                    "Avoid thick wet mulch layers during continuous heavy rains in poorly drained soils to avoid damping off."
                ],
                source_urls=["https://www.fao.org/conservation-agriculture/principles/en/"],
                license="CC-BY-4.0",
                review_status="reviewed",
                reviewed_by="fao-conservation-agronomist",
                reviewed_at=now,
            ),
        ]
        for practice in defaults:
            self.store.put("practices", practice.id, practice.model_dump(mode="json"))

