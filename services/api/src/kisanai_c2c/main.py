from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import date
from typing import Any
from uuid import uuid4

import requests
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import current_actor, require_roles
from .knowledge import practice_catalog
from .models import (
    ActionUpdate, Actor, Advisory, AdvisoryAction, AdvisoryRequest, CropRecommendationResult, DiagnosisRequest,
    ExchangeReview, ExpertReview, Farm, FarmChatRequest, FarmChatResponse, FarmCreate, HealthResponse,
    LandProfile, Practice, PracticeCreate, PracticeReview, Role, SatelliteMapResult, SoilExtraction, SoilTest,
    SoilTestCreate, SpeechRequest, VoiceTranscription,
)
from .providers.gemini import GeminiProvider, GeminiUnavailable
from .providers.satellite import SatelliteProvider, SatelliteUnavailable
from .providers.bigquery import BigQueryUnavailable
from .providers.maps import GoogleMaps, MapsUnavailable
from .providers.translate import TranslationUnavailable
from .providers.voice import VoiceProvider, VoiceUnavailable
from .providers.weather import WeatherProvider, WeatherUnavailable
from .service import AppService
from .settings import PROJECT_ROOT, get_settings

logger = logging.getLogger("kisanai_c2c")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        AppService().seed_default_practices_if_empty()
    except Exception as exc:  # noqa: BLE001 - the API still starts; the library can be seeded later
        logger.warning("Practice seeding skipped: %s", exc)
    yield


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def service() -> AppService:
    return AppService()


def _error(code: int, key: str, message: str, retryable: bool = False) -> JSONResponse:
    return JSONResponse(status_code=code, content={"error": {"code": key, "message": message, "retryable": retryable, "request_id": uuid4().hex}})


@app.exception_handler(LookupError)
async def not_found(_: Request, exc: LookupError):
    return _error(status.HTTP_404_NOT_FOUND, "not_found", str(exc))


@app.exception_handler(PermissionError)
async def forbidden(_: Request, exc: PermissionError):
    return _error(status.HTTP_403_FORBIDDEN, "forbidden", str(exc))


@app.exception_handler(ValueError)
async def invalid(_: Request, exc: ValueError):
    return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_request", str(exc))


@app.exception_handler(RuntimeError)
async def conflict(_: Request, exc: RuntimeError):
    return _error(status.HTTP_409_CONFLICT, "conflict", str(exc))


async def provider_unavailable(_: Request, exc: Exception):
    return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_unavailable", str(exc), True)


for _exc in (GeminiUnavailable, VoiceUnavailable, WeatherUnavailable, SatelliteUnavailable, TranslationUnavailable, BigQueryUnavailable, MapsUnavailable):
    app.add_exception_handler(_exc, provider_unavailable)


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception):
    logger.exception("Unhandled server exception: %s", exc)
    return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Something went wrong on the server. Please try again.")


# ---------------------------------------------------------------------------- meta
@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", service=settings.app_name, version=app.version, node_id=settings.node_id,
                          dependencies={"store": settings.store_provider, "media": settings.media_provider, "ai": settings.ai_provider,
                                        "model": settings.gemini_model, "earth_engine": str(settings.earth_engine_enabled).lower()})


@app.get("/api/v1/me")
def me(actor: Actor = Depends(current_actor)):
    return {"subject": actor.subject, "roles": sorted(role.value for role in actor.roles), "node_id": actor.node_id,
            "node_label": settings.node_label, "expert_access_required": bool(settings.expert_access_token)}


@app.post("/api/v1/internal/publish")
def publish_shared_data(request: Request, authorization: str | None = Header(default=None), svc: AppService = Depends(service)):
    """Called daily by Cloud Scheduler with a Google-signed OIDC token: publishes shareable data to BigQuery."""
    allowed = [settings.job_service_account] if settings.job_service_account else []
    require_google_identity(request, authorization, "/api/v1/internal/publish", allowed)
    published = svc.publish_shared_data()
    try:  # regions whose farms have no crop calendar get an AI draft for expert review (one per day)
        drafted = svc.auto_draft_missing_packs(limit=1)
    except Exception as exc:  # noqa: BLE001 - publishing already succeeded
        logger.warning("AI pack draft skipped: %s", exc)
        drafted = []
    return {"node_id": settings.node_id, "published": published, "drafted_packs": drafted}


class ImdRelayRequest(BaseModel):
    state_name: str = Field(min_length=2, max_length=80)
    district: str = Field(min_length=2, max_length=80)


@app.post("/api/v1/internal/imd")
def imd_relay(body: ImdRelayRequest, request: Request, authorization: str | None = Header(default=None)):
    """IMD authorises one caller IP; other India nodes fetch district IMD products through this node."""
    if not settings.imd_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This node has no IMD access")
    require_google_identity(request, authorization, "/api/v1/internal/imd", settings.imd_relay_caller_list)
    provider = WeatherProvider(settings)
    try:
        return {"node_id": settings.node_id, "snapshots": provider.fetch_imd_for_district(body.state_name, body.district)}
    except Exception as exc:  # noqa: BLE001 - IMD's reason is passed back, without credentials
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, provider._redact(str(exc))[:200]) from exc


def require_google_identity(request: Request, authorization: str | None, path: str, allowed: list[str]) -> None:
    """Accepts only a Google-signed identity token for this endpoint from one of the allowed service accounts."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    if not allowed or not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google identity token required")
    audience = f"{(settings.public_base_url or str(request.base_url)).rstrip('/')}{path}"
    try:
        claims = id_token.verify_oauth2_token(authorization.removeprefix("Bearer ").strip(), google_requests.Request(), audience=audience)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid identity token") from exc
    if claims.get("email") not in allowed or not claims.get("email_verified"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This identity may not call this endpoint")


@app.get("/api/v1/node")
def node_info(svc: AppService = Depends(service)):
    return svc.node_info()


@app.get("/api/v1/i18n/{locale}")
def ui_strings(locale: str, svc: AppService = Depends(service)):
    return svc.ui_strings(locale)


@app.get("/api/v1/catalog/crops")
def catalog_crops(locale: str = "en-IN", country_code: str | None = None, state_code: str | None = None, svc: AppService = Depends(service)):
    return svc.crop_catalog_view(locale, country_code, state_code)


@app.get("/api/v1/catalog/practices")
def catalog_practices():
    return list(practice_catalog().values())


# ---------------------------------------------------------------------------- farms
@app.post("/api/v1/farms", response_model=Farm, status_code=201)
def create_farm(payload: FarmCreate, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.create_farm(actor, payload)


@app.get("/api/v1/farms", response_model=list[Farm])
def list_farms(actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.farms(actor)


@app.get("/api/v1/farms/{farm_id}", response_model=Farm)
def get_farm(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.farm(actor, farm_id)


@app.put("/api/v1/farms/{farm_id}", response_model=Farm)
def update_farm(farm_id: str, payload: FarmCreate, version: int, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.update_farm(actor, farm_id, payload, version)


@app.delete("/api/v1/farms/{farm_id}")
def delete_farm(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    svc.delete_farm(actor, farm_id)
    return {"status": "deleted", "farm_id": farm_id}


# ---------------------------------------------------------------------------- media & soil
@app.post("/api/v1/media", status_code=201)
async def upload_media(purpose: str = Form(...), file: UploadFile = File(...), actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    if purpose not in {"soil_card", "crop_diagnosis"}:
        raise ValueError("Unsupported upload purpose")
    content = await file.read(settings.media_max_bytes + 1)
    return svc.save_media(actor, content, file.content_type or "application/octet-stream", purpose)


@app.post("/api/v1/farms/{farm_id}/soil/extract", response_model=SoilExtraction)
def extract_soil(farm_id: str, media_id: str, locale: str = "en-IN", actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.extract_soil(actor, farm_id, media_id, locale)


@app.post("/api/v1/farms/{farm_id}/soil", response_model=SoilTest, status_code=201)
def save_soil(farm_id: str, payload: SoilTestCreate, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.save_soil_test(actor, farm_id, payload)


@app.get("/api/v1/farms/{farm_id}/soil", response_model=SoilTest | None)
def get_soil(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    svc.farm(actor, farm_id)
    return svc.latest_soil(farm_id)


@app.get("/api/v1/farms/{farm_id}/soil/scheme")
def soil_scheme(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.soil_scheme_for(actor, farm_id)


@app.get("/api/v1/farms/{farm_id}/land-profile", response_model=LandProfile | None)
def land_profile(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.land_profile(svc.farm(actor, farm_id))


# ---------------------------------------------------------------------------- evidence, weather, satellite
@app.post("/api/v1/farms/{farm_id}/evidence/refresh", status_code=201)
def refresh_evidence(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.refresh_evidence(actor, farm_id)


@app.get("/api/v1/farms/{farm_id}/evidence")
def list_evidence(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.evidence(actor, farm_id)


@app.get("/api/v1/farms/{farm_id}/weather/operational")
def weather_operational(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.operational(actor, farm_id)


@app.get("/api/v1/farms/{farm_id}/satellite/map", response_model=SatelliteMapResult)
def satellite_map(farm_id: str, index: str = "NDVI", actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return SatelliteProvider(settings).satellite_map(svc.farm(actor, farm_id), index=index)


_IMAGE_CACHE: dict[tuple[str, str, str], tuple[bytes, str]] = {}


@app.get("/api/v1/farms/{farm_id}/satellite/image")
def satellite_image(farm_id: str, index: str = "NDVI", actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    farm = svc.farm(actor, farm_id)
    key = (farm.id + str(farm.version), index.upper(), date.today().isoformat())
    if key not in _IMAGE_CACHE:
        if len(_IMAGE_CACHE) > 200:
            _IMAGE_CACHE.clear()
        _IMAGE_CACHE[key] = SatelliteProvider(settings).satellite_image_bytes(farm, index=index)
    content, content_type = _IMAGE_CACHE[key]
    return Response(content=content, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------------------- recommendations & plans
@app.get("/api/v1/farms/{farm_id}/crop-recommendations", response_model=CropRecommendationResult)
def crop_recommendations(farm_id: str, locale: str = "en-IN", actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.crop_recommendations(actor, farm_id, locale=locale)


@app.post("/api/v1/farms/{farm_id}/advisories", response_model=Advisory, status_code=201)
def create_advisory(farm_id: str, payload: AdvisoryRequest, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.create_advisory(actor, farm_id, payload)


@app.get("/api/v1/farms/{farm_id}/advisories", response_model=list[Advisory])
def list_advisories(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.advisories(actor, farm_id)


@app.patch("/api/v1/actions/{action_id}", response_model=AdvisoryAction)
def update_action(action_id: str, payload: ActionUpdate, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.update_action(actor, action_id, payload)


# ---------------------------------------------------------------------------- diagnosis
@app.post("/api/v1/diagnoses", status_code=201)
def standalone_diagnose(payload: DiagnosisRequest, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    diagnosis, case = svc.diagnose(actor, None, payload)
    return {"diagnosis": diagnosis, "expert_case": case}


@app.post("/api/v1/farms/{farm_id}/diagnoses", status_code=201)
def diagnose(farm_id: str, payload: DiagnosisRequest, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    diagnosis, case = svc.diagnose(actor, farm_id, payload)
    return {"diagnosis": diagnosis, "expert_case": case}


@app.get("/api/v1/farms/{farm_id}/cases")
def farmer_cases(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.farmer_cases(actor, farm_id)

# ---------------------------------------------------------------------------- expert workspace
expert = require_roles(Role.expert)


@app.get("/api/v1/expert/cases")
def expert_cases(actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.expert_cases(actor)


@app.get("/api/v1/expert/cases/{case_id}/image")
def expert_case_image(case_id: str, actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    content, content_type = svc.expert_case_image(actor, case_id)
    return Response(content=content, media_type=content_type, headers={"Cache-Control": "private, max-age=600"})


@app.patch("/api/v1/expert/cases/{case_id}")
def review_case(case_id: str, payload: ExpertReview, actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.review_case(actor, case_id, payload)


@app.post("/api/v1/expert/practices", response_model=Practice, status_code=201)
def create_practice(payload: PracticeCreate, actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.create_practice(actor, payload)


@app.get("/api/v1/expert/practices", response_model=list[Practice])
def practices(actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.practices(actor)


@app.post("/api/v1/expert/practices/{practice_id}/review", response_model=Practice)
def review_practice(practice_id: str, payload: PracticeReview, actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.review_practice(actor, practice_id, payload)


@app.get("/api/v1/expert/practices/{practice_id}/export")
def export_practice(practice_id: str, actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.export_practice(actor, practice_id)


@app.post("/api/v1/expert/exchange/imports", status_code=201)
def import_bundle(bundle: dict[str, Any], actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.import_bundle(actor, bundle)


@app.get("/api/v1/expert/exchange/imports")
def imports(actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.imports(actor)


@app.patch("/api/v1/expert/exchange/imports/{import_id}")
def review_import(import_id: str, payload: ExchangeReview, actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.review_import(actor, import_id, payload)


@app.get("/api/v1/expert/packs")
def packs(actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.list_packs()


@app.get("/api/v1/expert/packs/missing")
def packs_missing(actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.regions_without_pack(actor)


class PackDraftRequest(BaseModel):
    subdivision_code: str = Field(pattern="^[A-Za-z]{2}-[A-Za-z0-9]{1,3}$")


@app.post("/api/v1/expert/packs/draft", status_code=201)
def draft_pack(payload: PackDraftRequest, actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.draft_pack(actor, payload.subdivision_code)


@app.get("/api/v1/expert/network/peers")
def peers(actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return {"node_id": settings.node_id, "peers": svc.peers()}


@app.get("/api/v1/expert/network/signals")
def peer_signals(actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return {"signals": svc.peer_signals()}


class PeerImport(BaseModel):
    peer_url: str = Field(min_length=8, max_length=300)
    kind: str = Field(pattern="^(packs|practices)$")
    item_id: str = Field(min_length=3, max_length=80)


@app.post("/api/v1/expert/network/import", status_code=201)
def import_from_peer(payload: PeerImport, actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.import_from_peer(actor, payload.peer_url, payload.kind, payload.item_id)


@app.get("/api/v1/expert/dashboard")
def dashboard(actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    return svc.dashboard(actor)


@app.post("/api/v1/expert/dashboard/brief")
def dashboard_brief(actor: Actor = Depends(expert), svc: AppService = Depends(service)):
    stats = svc.dashboard(actor)
    if stats["totals"]["diagnoses_30d"] < 5 and not any(row["outcomes"] for row in stats["practice_adoption"]):
        return {"brief": None, "reason": "Not enough reports yet for a meaningful brief (needs at least 5 diagnoses or reported outcomes)."}
    return {"brief": GeminiProvider(settings).dashboard_brief(stats), "reason": None}


# ---------------------------------------------------------------------------- public network API (no personal data)
@app.get("/.well-known/agrin-node")
def node_manifest(svc: AppService = Depends(service)):
    return svc.node_manifest()


@app.get("/api/v1/network/packs/{pack_id}")
def network_pack(pack_id: str, svc: AppService = Depends(service)):
    return svc.export_pack(pack_id)


@app.get("/api/v1/network/practices/{practice_id}")
def network_practice(practice_id: str, svc: AppService = Depends(service)):
    return svc.public_practice(practice_id)


@app.get("/api/v1/network/nodes")
def network_nodes(svc: AppService = Depends(service)):
    """Public list of this node and its peers, so farmers and testers can move between nodes."""
    return svc.network_nodes()


@app.get("/api/v1/network/signals")
def network_signals(svc: AppService = Depends(service)):
    return svc.shared_signals()


# ---------------------------------------------------------------------------- voice
@app.post("/api/v1/voice/transcribe", response_model=VoiceTranscription)
async def transcribe(file: UploadFile = File(...), locale: str = Form("en-IN"), actor: Actor = Depends(current_actor)):
    content = await file.read(settings.media_max_bytes + 1)
    transcript, confidence = VoiceProvider(settings).transcribe(content, locale, file.content_type or "audio/webm")
    return VoiceTranscription(transcript=transcript, locale=locale, confidence=confidence, provider="google_cloud_speech")


@app.post("/api/v1/voice/speak")
def speak(payload: SpeechRequest, actor: Actor = Depends(current_actor)):
    content, content_type = VoiceProvider(settings).speak(payload.text, payload.locale)
    return Response(content=content, media_type=content_type)


# ---------------------------------------------------------------------------- follow-up chat
_CHAT_SESSIONS: dict[str, dict[str, Any]] = {}
CHAT_SESSION_TTL_SECONDS = 300


def _cleanup_expired_chat_sessions() -> None:
    now = time.time()
    for sid in [sid for sid, sess in _CHAT_SESSIONS.items() if now - sess.get("last_active", 0) > CHAT_SESSION_TTL_SECONDS]:
        _CHAT_SESSIONS.pop(sid, None)


@app.post("/api/v1/farms/{farm_id}/chat", response_model=FarmChatResponse)
def farm_chat(farm_id: str, payload: FarmChatRequest, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    _cleanup_expired_chat_sessions()
    farm = svc.farm(actor, farm_id)
    session_id = payload.session_id or f"sess_{uuid4().hex[:12]}"
    sess = _CHAT_SESSIONS.get(session_id)
    if not sess or sess.get("farm_id") != farm_id or sess.get("subject") != actor.subject:
        sess = {"farm_id": farm_id, "subject": actor.subject, "history": [], "context": svc.chat_context(actor, farm, payload.locale)}
        _CHAT_SESSIONS[session_id] = sess
    sess["last_active"] = time.time()
    answer = GeminiProvider(settings).followup_chat(locale=payload.locale, farm=farm.model_dump(mode="json"), message=payload.message,
                                                    conversation_history=sess["history"], context=sess["context"])
    sess["history"].extend([{"role": "user", "text": payload.message}, {"role": "assistant", "text": answer}])
    return FarmChatResponse(session_id=session_id, response=answer, locale=payload.locale, expires_in_seconds=CHAT_SESSION_TTL_SECONDS)


@app.delete("/api/v1/farms/{farm_id}/chat/{session_id}")
def end_farm_chat(farm_id: str, session_id: str, actor: Actor = Depends(current_actor)):
    sess = _CHAT_SESSIONS.get(session_id)
    if sess and sess.get("subject") == actor.subject:
        _CHAT_SESSIONS.pop(session_id, None)
    return {"cleaned_up": True, "session_id": session_id}

# ---------------------------------------------------------------------------- geo lookups
NOMINATIM_HEADERS = {"User-Agent": "KISANAI-AgriN-Node/2.0 (agricultural advisory digital public good)"}
INDIA_STATE_CODES = {
    "andaman and nicobar islands": "AN", "andhra pradesh": "AP", "arunachal pradesh": "AR", "assam": "AS", "bihar": "BR",
    "chandigarh": "CH", "chhattisgarh": "CG", "dadra and nagar haveli and daman and diu": "DH", "delhi": "DL", "goa": "GA",
    "gujarat": "GJ", "haryana": "HR", "himachal pradesh": "HP", "jammu and kashmir": "JK", "jharkhand": "JH", "karnataka": "KA",
    "kerala": "KL", "ladakh": "LA", "lakshadweep": "LD", "madhya pradesh": "MP", "maharashtra": "MH", "manipur": "MN",
    "meghalaya": "ML", "mizoram": "MZ", "nagaland": "NL", "odisha": "OD", "puducherry": "PY", "punjab": "PB", "rajasthan": "RJ",
    "sikkim": "SK", "tamil nadu": "TN", "telangana": "TG", "tripura": "TR", "uttar pradesh": "UP", "uttarakhand": "UK",
    "west bengal": "WB",
}
_GEO_CACHE: dict[str, Any] = {}


def _place_from_nominatim(item: dict[str, Any]) -> dict[str, Any]:
    address = item.get("address") or {}
    country = (address.get("country_code") or "").upper()
    iso = address.get("ISO3166-2-lvl4") or address.get("ISO3166-2-lvl3") or ""
    state_name = address.get("state") or address.get("region") or address.get("province") or ""
    state_code = iso.split("-", 1)[1] if "-" in iso else INDIA_STATE_CODES.get(state_name.lower(), "")
    district = (address.get("state_district") or address.get("district") or address.get("county") or address.get("city")
                or address.get("municipality") or "").replace(" District", "").strip()
    village = address.get("village") or address.get("town") or address.get("hamlet") or address.get("suburb") or address.get("city") or ""
    return {
        "latitude": float(item["lat"]), "longitude": float(item["lon"]),
        "country_code": country, "country_name": address.get("country"),
        "state_code": state_code, "state_name": state_name,
        "district": district, "village": village, "pincode": address.get("postcode"),
        "label": item.get("display_name"), "source": "openstreetmap_nominatim",
    }


@app.get("/api/v1/geo/pincode/{pincode}")
def lookup_pincode(pincode: str):
    clean = pincode.strip()
    if not clean.isdigit() or len(clean) != 6:
        raise ValueError("PIN code must be 6 digits")
    if clean in _GEO_CACHE:
        return _GEO_CACHE[clean]
    try:
        resp = requests.get(f"https://api.pincodeapi.in/api/v1/pincode/{clean}", headers={"User-Agent": NOMINATIM_HEADERS["User-Agent"]}, timeout=5)
        payload = resp.json() if resp.status_code == 200 else {}
    except Exception:  # noqa: BLE001
        payload = {}
    offices = ((payload.get("data") or {}).get("post_offices") or []) if payload.get("success") else []
    if not offices:
        raise LookupError("PIN code not found. Use GPS or search for your village instead.")
    post_offices = []
    for po in offices:
        lat, lon = po.get("latitude"), po.get("longitude")
        post_offices.append({"name": po.get("office_name", ""), "office_type": po.get("office_type", ""), "district": po.get("district"),
                             "state": po.get("state"), "latitude": float(lat) if lat is not None else None,
                             "longitude": float(lon) if lon is not None else None})
    located = next((o for o in post_offices if o["latitude"] and o["longitude"]), None)
    if not located:
        raise LookupError("This PIN code has no coordinates. Use GPS or search for your village instead.")
    state_name = offices[0].get("state") or ""
    result = {
        "pincode": clean, "country_code": "IN", "district": offices[0].get("district") or "", "state_name": state_name,
        "state_code": INDIA_STATE_CODES.get(state_name.strip().lower(), ""), "village": located["name"],
        "latitude": located["latitude"], "longitude": located["longitude"], "post_offices": post_offices, "source": "pincodeapi.in",
    }
    _GEO_CACHE[clean] = result
    return result


@app.get("/api/v1/maps/satellite/{z}/{x}/{y}")
def satellite_tile(z: int, x: int, y: int):
    """Google Map Tiles satellite basemap through the node, so the Maps key stays on the server."""
    if not (0 <= z <= 21 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise ValueError("Invalid tile")
    content, content_type = GoogleMaps(settings).satellite_tile(z, x, y)
    return Response(content=content, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/v1/geo/reverse")
def reverse_geocode(latitude: float, longitude: float):
    key = f"rev:{round(latitude, 3)},{round(longitude, 3)}"
    if key in _GEO_CACHE:
        return _GEO_CACHE[key]
    try:  # Google Maps Geocoding first; OpenStreetMap Nominatim if Maps is not configured or fails
        result = GoogleMaps(settings).reverse(latitude, longitude)
        _GEO_CACHE[key] = result
        return result
    except MapsUnavailable:
        pass
    try:
        resp = requests.get("https://nominatim.openstreetmap.org/reverse",
                            params={"format": "jsonv2", "lat": latitude, "lon": longitude, "zoom": 14, "addressdetails": 1},
                            headers=NOMINATIM_HEADERS, timeout=6)
        resp.raise_for_status()
        result = _place_from_nominatim(resp.json()) | {"latitude": latitude, "longitude": longitude}
    except Exception as exc:  # noqa: BLE001
        raise LookupError("Could not name this location; please type the state and district.") from exc
    _GEO_CACHE[key] = result
    return result


@app.get("/api/v1/geo/search")
def search_place(q: str, country_code: str | None = None):
    query = q.strip()
    if len(query) < 3:
        raise ValueError("Type at least 3 letters")
    key = f"search:{query.lower()}:{country_code or ''}"
    if key in _GEO_CACHE:
        return _GEO_CACHE[key]
    try:
        google = GoogleMaps(settings).search(query, country_code)
        if google:
            _GEO_CACHE[key] = google
            return google
    except MapsUnavailable:
        pass
    params: dict[str, Any] = {"format": "jsonv2", "q": query, "limit": 6, "addressdetails": 1}
    if country_code:
        params["countrycodes"] = country_code.lower()
    resp = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers=NOMINATIM_HEADERS, timeout=6)
    resp.raise_for_status()
    result = [_place_from_nominatim(item) for item in resp.json()]
    _GEO_CACHE[key] = result
    return result


# ---------------------------------------------------------------------------- single-page app
static_dir = next((p for p in (PROJECT_ROOT / "static", PROJECT_ROOT / "apps/web/dist") if (p / "index.html").exists()), None)
if static_dir:
    if (static_dir / "assets").exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("health"):
            raise HTTPException(status_code=404, detail="Not Found")
        file_path = (static_dir / full_path).resolve()
        if full_path and static_dir.resolve() in file_path.parents and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(static_dir / "index.html")
