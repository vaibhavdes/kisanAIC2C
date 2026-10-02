from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from .domain import POLICY_VERSION, build_options, generate_crop_recommendations, rainfall_total
from .weather_ops import current_season, operational_forecast_indicators
from .media import MediaStore, get_media_store
from .models import (
    ActionUpdate,
    AdvisoryAction,
    Actor,
    Advisory,
    AdvisoryRequest,
    CropRecommendationResult,
    Diagnosis,
    DiagnosisRequest,
    EvidenceSnapshot,
    ExpertCase,
    ExpertReview,
    Farm,
    FarmCreate,
    MediaRecord,
    Role,
    SatelliteMapResult,
    SoilExtraction,
    SoilTest,
    SoilTestCreate,
    SoilValues,
)
from .providers.gemini import GeminiProvider
from .providers.satellite import SatelliteProvider, SatelliteUnavailable
from .providers.weather import WeatherProvider
from .settings import Settings, get_settings
from .store import DocumentStore, get_store


# Open-Meteo updates its models hourly; older forecasts are refetched before giving advice.
WEATHER_MAX_AGE = timedelta(hours=3)
SATELLITE_MAX_AGE = timedelta(days=5)
# A field's satellite map (zones + PNG) is stored and reused for a day, then fetched again.
SATELLITE_MAP_MAX_AGE = timedelta(days=1)


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

    @staticmethod
    def _is_creator(farm: Farm, actor: Actor, client_ip: str | None, device_id: str | None) -> bool:
        """Who may delete or edit a farm: the browser that created it (device id), otherwise the
        same network address for farms created before device ids existed, or an expert."""
        if Role.expert in actor.roles:
            return True
        if farm.creator_device:
            return bool(device_id) and farm.creator_device == device_id
        if farm.creator_ip:
            return bool(client_ip) and farm.creator_ip == client_ip
        return farm.owner_subject == actor.subject

    @staticmethod
    def _public(farm: Farm) -> Farm:
        """Never send another person's network address or device id to the browser."""
        return farm.model_copy(update={"creator_ip": None, "creator_device": None})

    def create_farm(self, actor: Actor, payload: FarmCreate, client_ip: str | None = None, device_id: str | None = None) -> Farm:
        area_ha = payload.area_value if payload.area_unit == "hectare" else payload.area_value * 0.40468564224
        farm_id = payload.id if payload.id else f"farm_{uuid4().hex}"
        farm = Farm(
            id=farm_id,
            **payload.model_dump(exclude={"id", "creator_ip"}),
            creator_ip=client_ip,
            creator_device=device_id,
            is_mine=True,
            area_ha=round(area_ha, 4),
            owner_subject=actor.subject,
            node_id=actor.node_id,
        )
        self.store.put("farms", farm.id, farm.model_dump(mode="json"))
        return self._public(farm)

    def farms(self, actor: Actor, client_ip: str | None = None, device_id: str | None = None) -> list[Farm]:
        filters = {"node_id": actor.node_id}
        if actor.subject != "local-farmer":
            filters["owner_subject"] = actor.subject
        items = self.store.list("farms", filters=filters)
        result: list[Farm] = []
        for item in items:
            f = Farm.model_validate(item)
            f.is_mine = self._is_creator(f, actor, client_ip, device_id)
            result.append(self._public(f))
        return result

    def farm(self, actor: Actor, farm_id: str, client_ip: str | None = None, *, expert_allowed: bool = False, device_id: str | None = None) -> Farm:
        value = self.store.get("farms", farm_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Farm not found")
        if actor.subject != "local-farmer" and value.get("owner_subject") != actor.subject and not (expert_allowed and Role.expert in actor.roles):
            raise PermissionError("Farm access denied")
        f = Farm.model_validate(value)
        f.is_mine = self._is_creator(f, actor, client_ip, device_id)
        return self._public(f)

    def delete_farm(self, actor: Actor, farm_id: str, client_ip: str | None = None, device_id: str | None = None) -> bool:
        value = self.store.get("farms", farm_id)
        if not value or value.get("node_id") != actor.node_id:
            raise LookupError("Farm not found")
        if not self._is_creator(Farm.model_validate(value), actor, client_ip, device_id):
            raise PermissionError("Only the creator of this farm can delete it.")
        # The farm's own records go with it; plant doctor cases stay for the expert's history.
        for collection in ("evidence", "soil_tests", "soil_extractions", "advisories"):
            for item in self.store.list(collection, filters={"farm_id": farm_id}, limit=500):
                self.store.delete(collection, item["id"])
        self._drop_satellite_maps(farm_id)
        return self.store.delete("farms", farm_id)

    def upsert_farm(self, actor: Actor, farm_id: str, payload: FarmCreate, expected_version: int | None = None, client_ip: str | None = None, device_id: str | None = None) -> Farm:
        value = self.store.get("farms", farm_id)
        if not value:
            payload_with_id = payload.model_copy(update={"id": farm_id})
            return self.create_farm(actor, payload_with_id, client_ip=client_ip, device_id=device_id)
        current = Farm.model_validate(value)
        if current.node_id != actor.node_id:
            raise LookupError("Farm not found")
        if not self._is_creator(current, actor, client_ip, device_id):
            raise PermissionError("Farm access denied")
        if expected_version is not None and current.version != expected_version:
            raise RuntimeError("Farm version conflict")
        area_ha = payload.area_value if payload.area_unit == "hectare" else payload.area_value * 0.40468564224
        # Validate the merged record so nested fields (location) are proper models, not dicts.
        updated = Farm.model_validate({
            **current.model_dump(),
            **payload.model_dump(exclude={"id", "creator_ip"}),
            "creator_ip": current.creator_ip or client_ip,
            "area_ha": round(area_ha, 4),
            "version": current.version + 1,
            "updated_at": datetime.now(UTC),
        })
        self.store.put("farms", farm_id, updated.model_dump(mode="json"))
        moved = (updated.location.latitude, updated.location.longitude) != (current.location.latitude, current.location.longitude)
        if moved or updated.boundary_coordinates != current.boundary_coordinates:
            # Weather and satellite readings belong to the old place; fetch them again.
            for item in self.store.list("evidence", filters={"farm_id": farm_id}, limit=500):
                self.store.delete("evidence", item["id"])
            self._drop_satellite_maps(farm_id)
        return self._public(updated)

    def update_farm(self, actor: Actor, farm_id: str, payload: FarmCreate, expected_version: int, client_ip: str | None = None, device_id: str | None = None) -> Farm:
        return self.upsert_farm(actor, farm_id, payload, expected_version, client_ip=client_ip, device_id=device_id)

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

    def refresh_evidence(self, actor: Actor, farm_id: str, *, include_satellite: bool = True) -> list[EvidenceSnapshot]:
        farm = self.farm(actor, farm_id)
        snapshots = WeatherProvider(self.settings).fetch(farm)
        if not include_satellite:
            self._store_evidence(farm.id, snapshots)
            return snapshots
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
        self._store_evidence(farm.id, snapshots)
        return snapshots

    def _store_evidence(self, farm_id: str, snapshots: list[EvidenceSnapshot]) -> None:
        """Save new snapshots and delete the ones they replace, so a farm keeps one per source and kind.

        A failed ("missing") fetch is saved but does not remove the last good reading.
        """
        for snapshot in snapshots:
            self.store.put("evidence", snapshot.id, snapshot.model_dump(mode="json"))
        replaced = {(snap.provider, snap.kind) for snap in snapshots if snap.mode != "missing"}
        fresh = {snap.id for snap in snapshots}
        for item in self.store.list("evidence", filters={"farm_id": farm_id}, limit=500):
            if item["id"] not in fresh and (item.get("provider"), item.get("kind")) in replaced:
                self.store.delete("evidence", item["id"])

    def satellite_map(self, actor: Actor, farm_id: str, index: str = "NDVI", days: int = 30) -> SatelliteMapResult:
        """The field's satellite map, from the database when a stored one is under a day old.

        The zones and the PNG are stored together (PNG in the media store, since the Earth Engine
        link expires) and dropped when the field is moved, redrawn or deleted.
        """
        farm = self.farm(actor, farm_id)
        index = index.upper()
        doc_id = f"{farm.id}_{index}_{days}"
        shape = SatelliteProvider.shape_key(farm)
        stored = self.store.get("satellite_maps", doc_id)
        if (
            stored and stored.get("shape") == shape and stored.get("image_uri")
            and datetime.now(UTC) - datetime.fromisoformat(stored["fetched_at"]) < SATELLITE_MAP_MAX_AGE
        ):
            return SatelliteMapResult.model_validate(stored["result"])

        provider = SatelliteProvider(self.settings)
        result = provider.satellite_map(farm, index=index, days=days)
        if result.data_mode != "live" or not result.map_url:
            return result
        try:
            image = provider.download_image(result.map_url)
        except Exception as exc:
            return result.model_copy(update={"data_mode": "missing", "zones": [], "map_url": None, "acquisition_note": str(exc)})
        image_uri, _ = self.media_store.save(image, "image/png", folder="satellite")
        if stored and stored.get("image_uri"):
            self._delete_media(stored["image_uri"])
        result = result.model_copy(update={"map_url": None})
        now = datetime.now(UTC)
        self.store.put("satellite_maps", doc_id, {
            "id": doc_id, "farm_id": farm.id, "node_id": farm.node_id, "index": index, "days": days,
            "shape": shape, "image_uri": image_uri,
            "fetched_at": now.isoformat(), "created_at": now.isoformat(),
            "result": result.model_dump(mode="json"),
        })
        return result

    def satellite_image(self, actor: Actor, farm_id: str, index: str = "NDVI", days: int = 30) -> bytes:
        result = self.satellite_map(actor, farm_id, index=index, days=days)
        stored = self.store.get("satellite_maps", f"{farm_id}_{index.upper()}_{days}")
        if not stored or not stored.get("image_uri"):
            raise SatelliteUnavailable(result.acquisition_note or "Satellite map is not available")
        return self.media_store.read(stored["image_uri"])

    def _drop_satellite_maps(self, farm_id: str) -> None:
        for item in self.store.list("satellite_maps", filters={"farm_id": farm_id}, limit=500):
            if item.get("image_uri"):
                self._delete_media(item["image_uri"])
            self.store.delete("satellite_maps", item["id"])

    def _delete_media(self, storage_uri: str) -> None:
        try:
            self.media_store.delete(storage_uri)
        except Exception:
            pass  # an orphaned PNG is harmless; the record that pointed to it is gone

    def evidence(self, actor: Actor, farm_id: str) -> list[EvidenceSnapshot]:
        """Newest snapshot per (provider, kind) for the farm, newest first."""
        self.farm(actor, farm_id, expert_allowed=True)
        snapshots = [EvidenceSnapshot.model_validate(item) for item in self.store.list("evidence", filters={"farm_id": farm_id}, limit=60)]
        snapshots.sort(key=lambda snap: snap.fetched_at, reverse=True)
        latest: dict[tuple[str, str], EvidenceSnapshot] = {}
        for snap in snapshots:
            latest.setdefault((snap.provider, snap.kind), snap)
        return list(latest.values())

    def current_evidence(self, actor: Actor, farm_id: str) -> list[EvidenceSnapshot]:
        """Evidence with a weather forecast younger than WEATHER_MAX_AGE; refetches when stale.

        If the refetch fails, the stale evidence is returned so advice degrades instead of failing.
        """
        evidence = self.evidence(actor, farm_id)
        forecasts = [snap for snap in evidence if snap.kind == "weather_forecast" and snap.mode != "missing"]
        newest = max(forecasts, key=lambda snap: snap.fetched_at, default=None)
        # Snapshots stored before the daily temperature/wind/ET0 fields existed are refetched too.
        outdated_shape = newest is not None and newest.provider == "open_meteo" and not any(v.name.startswith("hourly_") for v in newest.values)
        if newest is None or outdated_shape or datetime.now(UTC) - newest.fetched_at > WEATHER_MAX_AGE:
            # Sentinel-2 revisits every ~5 days, so the satellite query is only repeated when its
            # last observation is older than that; weather alone is refetched otherwise.
            satellite = next((snap for snap in evidence if snap.kind == "satellite_observation"), None)
            satellite_stale = satellite is None or datetime.now(UTC) - satellite.fetched_at > SATELLITE_MAX_AGE
            try:
                self.refresh_evidence(actor, farm_id, include_satellite=satellite_stale)
                evidence = self.evidence(actor, farm_id)
            except Exception:
                pass
        return evidence

    def create_advisory(self, actor: Actor, farm_id: str, payload: AdvisoryRequest) -> Advisory:
        farm = self.farm(actor, farm_id)
        evidence = self.current_evidence(actor, farm_id)
        soil = self.latest_soil(farm_id)
        evidence_dump = [item.model_dump(mode="json") for item in evidence]
        if payload.goal == "crop_plan":
            # Same ranking as the crop recommendation screen, so the plan never contradicts it.
            ranked = generate_crop_recommendations(farm, soil, season=payload.season, evidence=evidence_dump, locale=payload.locale)
            options = ranked.recommendations + ranked.unsuitable_crops
        else:
            options = build_options(farm, soil, goal=payload.goal, season=payload.season, rainfall_7d_mm=rainfall_total(evidence_dump))
        eligible = [item for item in options if item.eligible][:3]
        if not eligible:
            # Fallback to the top candidate options so Gemini can explain what is constraining eligibility (e.g. season or water)
            eligible = sorted(options, key=lambda item: sum(d.score for d in item.dimensions if d.score is not None), reverse=True)[:3]
            if not eligible:
                raise ValueError("No crop options configured in the system for this region")
        operational = operational_forecast_indicators(
            evidence_dump, soil_type=farm.soil_type, water_access=farm.water_access, season=payload.season, locale=payload.locale,
        )
        result, ai_generated = self.gemini.create_plan(
            locale=payload.locale,
            farm=farm.model_dump(mode="json"),
            soil=soil.model_dump(mode="json") if soil else None,
            evidence=evidence_dump,
            eligible_options=[item.model_dump(mode="json") for item in eligible],
            goal=payload.goal,
            operational=operational,
            farmer_query=payload.farmer_query,
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
            model_provider=self.gemini.provider_name if ai_generated else "rule_based",
            model=self.settings.gemini_model if ai_generated else "weather-rules",
            prompt_version=self.gemini.prompt_version,
            policy_version=POLICY_VERSION,
        )
        self.store.put("advisories", advisory.id, advisory.model_dump(mode="json"))
        return advisory

    def advisories(self, actor: Actor, farm_id: str) -> list[Advisory]:
        self.farm(actor, farm_id)
        return [Advisory.model_validate(item) for item in self.store.list("advisories", filters={"farm_id": farm_id}, limit=50)]

    def crop_recommendations(self, actor: Actor, farm_id: str, season: str | None = None, locale: str = "en-IN") -> CropRecommendationResult:
        farm = self.farm(actor, farm_id)
        evidence = self.current_evidence(actor, farm_id)
        soil = self.latest_soil(farm_id)
        evidence_dump = [item.model_dump(mode="json") for item in evidence]
        return generate_crop_recommendations(farm, soil, season=season, evidence=evidence_dump, locale=locale)

    def soil_profile(self, actor: Actor, farm_id: str) -> dict[str, Any]:
        farm = self.farm(actor, farm_id)
        soil = self.latest_soil(farm_id)
        from .fertilizer import _soil_values
        return {
            "farm_id": farm_id,
            "soil_type": farm.soil_type,
            "values": _soil_values(soil, farm),
            "soil_test": soil.model_dump(mode="json") if soil else None,
        }

    def fertilizer(self, actor: Actor, farm_id: str, crop: str, season: str | None = None) -> dict[str, Any]:
        farm = self.farm(actor, farm_id)
        from .fertilizer import fertilizer_plan
        return fertilizer_plan(farm, self.latest_soil(farm_id), crop, season or current_season())

    def weather_operations(self, actor: Actor, farm_id: str, season: str | None = None, locale: str = "en-IN") -> dict[str, Any]:
        farm = self.farm(actor, farm_id)
        evidence = self.current_evidence(actor, farm_id)
        return operational_forecast_indicators(
            [item.model_dump(mode="json") for item in evidence],
            soil_type=farm.soil_type, water_access=farm.water_access, season=season, locale=locale,
        )

    def update_action(self, actor: Actor, action_id: str, payload: ActionUpdate) -> AdvisoryAction:
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

    def expert_cases(self, actor: Actor) -> list[dict[str, Any]]:
        """Escalated cases with the diagnosis and photo reference the expert needs to review them."""
        cases = []
        for item in self.store.list("expert_cases", filters={"node_id": actor.node_id}, limit=100):
            case = ExpertCase.model_validate(item).model_dump(mode="json")
            diagnosis = self.store.get("diagnoses", case["diagnosis_id"])
            if diagnosis:
                case["diagnosis"] = {key: diagnosis.get(key) for key in (
                    "crop", "image_quality", "visible_findings", "plausible_causes", "uncertainty_reasons", "safe_next_steps", "created_at")}
                case["image_url"] = f"/api/v1/media/{diagnosis.get('media_id')}"
            farm = self.store.get("farms", case["farm_id"]) if case["farm_id"] != "standalone" else None
            if farm:
                case["farm"] = {key: farm.get(key) for key in ("name", "district", "state_name", "soil_type", "water_access", "current_crop")}
            cases.append(case)
        return cases

    def media_content(self, actor: Actor, media_id: str) -> tuple[bytes, str]:
        media = self.media(actor, media_id, expert_allowed=True)
        return self.media_store.read(media.storage_uri), media.content_type

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
