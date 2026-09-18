from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_flexible_date(v: Any) -> date | None:
    """Safely parse flexible date strings into a standard python date.

    Supports:
    - ISO format: YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
    - Indian / British format: DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY
    - 2-digit year: DD-MM-YY, DD/MM/YY
    - Textual dates: '25 June 2015', '25 Jun 2015'
    - Falls back to None if unparseable, preventing validation crashes on OCR cards.
    """
    if v is None or v == "" or str(v).lower() in ("null", "none", "n/a", "-"):
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if not isinstance(v, str):
        return None

    s = v.strip()
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
        "%d-%m-%y",
        "%d/%m/%y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    return None


class Role(StrEnum):
    farmer = "farmer"
    expert = "expert"
    operator = "operator"


class Actor(BaseModel):
    subject: str
    node_id: str
    roles: set[Role] = Field(default_factory=lambda: {Role.farmer})
    locale: str = "en-IN"
    email: str | None = None


class Location(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    source: Literal["farmer", "device", "imported"] = "farmer"
    confirmed: bool = True

    @field_validator("source", mode="before")
    @classmethod
    def validate_source(cls, v: Any) -> str:
        if v in {"farmer", "device", "imported"}:
            return v
        if v in {"polygon_plot", "manual"}:
            return "farmer"
        if v in {"gps", "browser"}:
            return "device"
        return "farmer"


class FarmCreate(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    country_code: str = Field(default="IN", min_length=2, max_length=2)
    state_code: str = Field(min_length=2, max_length=20)
    state_name: str = Field(min_length=2, max_length=120)
    district: str = Field(min_length=2, max_length=120)
    village: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=10)
    boundary_coordinates: list[list[float]] = Field(default_factory=list)
    area_value: float = Field(gt=0, le=10000)
    area_unit: Literal["hectare", "acre"] = "acre"
    location: Location
    water_access: Literal["rainfed", "supplemental_irrigation", "irrigated"]
    soil_type: Literal["unknown", "black", "red", "alluvial", "sandy", "clay", "loam"] = "unknown"
    current_crop: str | None = Field(default=None, max_length=80)
    previous_crop: str | None = Field(default=None, max_length=80)
    sowing_date: date | None = None
    crop_status: Literal["planning", "planted", "harvested"] = "planning"
    creator_ip: str | None = None

    @field_validator("country_code", "state_code")
    @classmethod
    def uppercase_codes(cls, value: str) -> str:
        return value.upper()


class Farm(FarmCreate):
    id: str = Field(default_factory=lambda: f"farm_{uuid4().hex}")
    owner_subject: str
    node_id: str
    area_ha: float
    version: int = 1
    creator_ip: str | None = None
    is_mine: bool | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)



class SoilValues(BaseModel):
    ph: float | None = Field(default=None, ge=0, le=14)
    ec_ds_m: float | None = Field(default=None, ge=0, le=100)
    organic_carbon_percent: float | None = Field(default=None, ge=0, le=30)
    nitrogen_kg_ha: float | None = Field(default=None, ge=0, le=10000)
    phosphorus_kg_ha: float | None = Field(default=None, ge=0, le=10000)
    potassium_kg_ha: float | None = Field(default=None, ge=0, le=10000)


class SoilExtraction(BaseModel):
    values: SoilValues
    sample_date: date | None = None
    lab_name: str | None = None
    raw_text: str | None = None
    uncertain_fields: list[str] = Field(default_factory=list)
    source: str
    model: str

    @field_validator("sample_date", mode="before")
    @classmethod
    def validate_sample_date(cls, v: Any) -> date | None:
        return parse_flexible_date(v)


class SoilTestCreate(BaseModel):
    values: SoilValues
    sample_date: date | None = None
    lab_name: str | None = Field(default=None, max_length=160)
    source: Literal["manual", "soil_card_confirmed"] = "manual"
    extraction_id: str | None = None
    confirmed: bool = True

    @field_validator("sample_date", mode="before")
    @classmethod
    def validate_sample_date(cls, v: Any) -> date | None:
        return parse_flexible_date(v)


class SoilTest(SoilTestCreate):
    id: str = Field(default_factory=lambda: f"soil_{uuid4().hex}")
    farm_id: str
    owner_subject: str
    node_id: str
    created_at: datetime = Field(default_factory=utcnow)


class EvidenceValue(BaseModel):
    name: str
    value: str | float | int | bool | None
    unit: str | None = None


class EvidenceSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: f"evidence_{uuid4().hex}")
    farm_id: str
    node_id: str
    provider: str
    kind: str
    mode: Literal["live", "cached", "historical", "missing"]
    observed_at: datetime | None = None
    issued_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=utcnow)
    valid_until: datetime | None = None
    spatial_scope: str
    values: list[EvidenceValue] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    source_reference: str


class SatelliteZone(BaseModel):
    """A distinct classified zone within the farm parcel (GeoPard layout)."""
    id: int
    color: str
    label: str
    min_val: float
    max_val: float
    median_val: float
    area_acres: float
    percentage: float


class SatelliteMapResult(BaseModel):
    """Result of a satellite map thumbnail request with GeoPard zonal breakdown."""
    farm_id: str
    index: str  # NDVI, NDWI, NDMI
    meaning: str  # human label: "Crop growth map", etc.
    map_url: str | None = None  # Earth Engine thumbnail URL
    fallback_map_url: str | None = None  # Google Maps Static API URL (always available)
    image_api_path: str | None = None  # Local authenticated proxy: /api/v1/farms/{id}/satellite/image?index=NDVI
    start_date: str
    end_date: str
    scene_date: str | None = None  # Exact observation date e.g. "07 Sep 2026, 05:33 UTC"
    sensor: str = "Sentinel-2 MSI Level-2A"
    cloud_coverage_percent: float | None = None
    resolution_m: int = 10
    field_status_narrative: str | None = None
    source: str
    legend: dict[str, str]  # {"red": "weak growth", "green": "healthy growth"}
    zones: list[SatelliteZone] = Field(default_factory=list)
    data_mode: str  # "live", "fixture", "missing"
    acquisition_note: str | None = None


class AdvisoryRequest(BaseModel):
    goal: Literal["crop_plan", "manage_current_crop"]
    season: Literal["kharif", "rabi", "summer"] | None = None
    locale: str = "en-IN"
    budget_level: Literal["low", "medium", "flexible"] = "low"
    labor_access: Literal["limited", "family", "hired"] = "family"
    equipment_access: list[str] = Field(default_factory=list)


class ScoreDimension(BaseModel):
    name: str
    score: float | None = Field(default=None, ge=0, le=1)
    explanation: str


class CropDecisionFactor(BaseModel):
    factor_id: str  # "season", "water", "soil", "weather", "rotation", "regional_fit", "regenerative_practice"
    factor_name: str
    status: Literal["optimal", "compatible", "constrained", "rejected"]
    data_used: str
    reasoning: str
    remedy: str | None = None


class CropPracticeOption(BaseModel):
    crop: str
    crop_name: str = ""
    practice_ids: list[str] = Field(default_factory=list)
    eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    dimensions: list[ScoreDimension] = Field(default_factory=list)
    evidence_coverage: float = Field(default=1.0, ge=0, le=1)
    rank_score: float | None = Field(default=None, ge=0, le=1)
    factors: list[CropDecisionFactor] = Field(default_factory=list)


class CropRecommendationResult(BaseModel):
    farm_id: str
    farm_name: str
    district: str
    state_name: str
    season: str
    locale: str
    water_access: str
    soil_type: str
    previous_crop: str | None = None
    rainfall_7d_forecast_mm: float | None = None
    data_sources_used: list[dict[str, str]] = Field(default_factory=list)
    recommendations: list[CropPracticeOption] = Field(default_factory=list)
    unsuitable_crops: list[CropPracticeOption] = Field(default_factory=list)
    regional_notes: str | None = None


class AdvisoryAction(BaseModel):
    id: str = Field(default_factory=lambda: f"action_{uuid4().hex}")
    practice_id: str
    instruction: str
    timing: str
    why: str
    caution: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["proposed", "accepted", "completed", "declined"] = "proposed"


class Advisory(BaseModel):
    id: str = Field(default_factory=lambda: f"advisory_{uuid4().hex}")
    farm_id: str
    owner_subject: str
    node_id: str
    goal: str
    locale: str
    summary: str
    options: list[CropPracticeOption]
    actions: list[AdvisoryAction]
    evidence_ids: list[str]
    uncertainty_reasons: list[str] = Field(default_factory=list)
    model_provider: str
    model: str
    prompt_version: str
    policy_version: str
    created_at: datetime = Field(default_factory=utcnow)


class ActionUpdate(BaseModel):
    status: Literal["accepted", "completed", "declined"]
    observation: str | None = Field(default=None, max_length=2000)


class MediaRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"media_{uuid4().hex}")
    owner_subject: str
    node_id: str
    storage_uri: str
    content_type: str
    size_bytes: int
    purpose: Literal["soil_card", "crop_diagnosis", "voice"]
    created_at: datetime = Field(default_factory=utcnow)


class DiagnosisRequest(BaseModel):
    media_id: str
    crop: str = Field(default="auto-detect", max_length=80)
    crop_stage: str | None = Field(default=None, max_length=120)
    symptoms: str | None = Field(default=None, max_length=1200)
    locale: str = "en-IN"


class Diagnosis(BaseModel):
    id: str = Field(default_factory=lambda: f"diagnosis_{uuid4().hex}")
    farm_id: str
    owner_subject: str
    node_id: str
    media_id: str
    crop: str
    image_quality: Literal["good", "usable", "poor", "not_crop"]
    visible_findings: list[str]
    plausible_causes: list[str]
    uncertainty_reasons: list[str]
    safe_next_steps: list[str]
    needs_expert_review: bool
    model_provider: str
    model: str
    created_at: datetime = Field(default_factory=utcnow)


class ExpertCase(BaseModel):
    id: str = Field(default_factory=lambda: f"case_{uuid4().hex}")
    node_id: str
    owner_subject: str
    farm_id: str
    diagnosis_id: str
    status: Literal["open", "in_review", "resolved"] = "open"
    assigned_subject: str | None = None
    review_text: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    version: int = 1
    created_at: datetime = Field(default_factory=utcnow)


class ExpertReview(BaseModel):
    version: int
    review_text: str = Field(min_length=3, max_length=4000)
    status: Literal["in_review", "resolved"]


class PracticeCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    summary: str = Field(min_length=10, max_length=1200)
    country_codes: list[str] = Field(default_factory=lambda: ["IN"])
    state_codes: list[str] = Field(default_factory=list)
    crops: list[str]
    seasons: list[str]
    water_contexts: list[str]
    steps: list[str]
    contraindications: list[str]
    source_urls: list[str]
    license: Literal["CC0-1.0", "CC-BY-4.0"]


class Practice(PracticeCreate):
    id: str = Field(default_factory=lambda: f"practice_{uuid4().hex}")
    node_id: str
    created_by: str
    version: int = 1
    review_status: Literal["draft", "reviewed"] = "draft"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class PracticeReview(BaseModel):
    approve: bool
    note: str = Field(min_length=3, max_length=1000)


class ExchangeImport(BaseModel):
    id: str = Field(default_factory=lambda: f"exchange_{uuid4().hex}")
    node_id: str
    imported_by: str
    digest: str
    bundle: dict[str, Any]
    compatibility_findings: list[str]
    local_review_status: Literal["pending", "approved", "rejected"] = "pending"
    local_review_note: str | None = None
    local_reviewed_by: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ExchangeReview(BaseModel):
    approve: bool
    note: str = Field(min_length=3, max_length=2000)


class VoiceTranscription(BaseModel):
    transcript: str
    locale: str
    confidence: float | None = None
    provider: str


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    locale: str = "en-IN"


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    node_id: str
    dependencies: dict[str, str] = Field(default_factory=dict)


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    request_id: str | None = None
    fields: dict[str, str] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class Document(BaseModel):
    model_config = ConfigDict(extra="allow")


class FarmChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    locale: str = Field(default="en-IN", max_length=10)
    session_id: str | None = Field(default=None, max_length=64)


class FarmChatResponse(BaseModel):
    session_id: str
    response: str
    locale: str
    expires_in_seconds: int = 300
    cleaned_up: bool = False
