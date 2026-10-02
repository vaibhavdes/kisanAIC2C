from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .auth import current_actor, require_roles
from .models import (
    ActionUpdate, Actor, Advisory, AdvisoryRequest, CropRecommendationResult, DiagnosisRequest,
    ExpertReview, Farm, FarmChatRequest, FarmChatResponse, FarmCreate, HealthResponse,
    Role, SoilExtraction, SoilTest, SoilTestCreate,
    SpeechRequest, VoiceTranscription,
)
from .providers.gemini import GeminiUnavailable
from .providers.voice import VoiceProvider, VoiceUnavailable
from .providers.weather import WeatherUnavailable
from .providers.satellite import SatelliteUnavailable
from .service import AppService
from .settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def service() -> AppService:
    return AppService()


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


app.add_exception_handler(GeminiUnavailable, provider_unavailable)
app.add_exception_handler(VoiceUnavailable, provider_unavailable)
app.add_exception_handler(WeatherUnavailable, provider_unavailable)
app.add_exception_handler(SatelliteUnavailable, provider_unavailable)


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception):
    import logging
    logging.getLogger("kisanai_c2c").exception("Unhandled server exception: %s", exc)
    return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", f"Server error: {str(exc)}", False)


def _error(code: int, key: str, message: str, retryable: bool = False):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=code,
        content={"error": {"code": key, "message": message, "retryable": retryable, "request_id": uuid4().hex}},
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", service=settings.app_name, version=app.version, node_id=settings.node_id,
                          dependencies={"store": settings.store_provider, "media": settings.media_provider, "ai": settings.ai_provider})


@app.get("/api/v1/me")
def me(actor: Actor = Depends(current_actor)):
    return actor


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


def get_device_id(request: Request) -> str | None:
    """Random id the browser keeps in local storage; identifies who created a farm."""
    value = (request.headers.get("x-device-id") or "").strip()
    return value if 8 <= len(value) <= 64 and value.replace("-", "").isalnum() else None


@app.post("/api/v1/farms", response_model=Farm, status_code=201)
def create_farm(payload: FarmCreate, request: Request, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    client_ip = get_client_ip(request)
    return svc.create_farm(actor, payload, client_ip=client_ip, device_id=get_device_id(request))


@app.get("/api/v1/farms", response_model=list[Farm])
def list_farms(request: Request, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    client_ip = get_client_ip(request)
    return svc.farms(actor, client_ip=client_ip, device_id=get_device_id(request))


@app.get("/api/v1/farms/{farm_id}", response_model=Farm)
def get_farm(farm_id: str, request: Request, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    client_ip = get_client_ip(request)
    try:
        return svc.farm(actor, farm_id, client_ip=client_ip, device_id=get_device_id(request))
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


@app.put("/api/v1/farms/{farm_id}", response_model=Farm)
def update_farm(farm_id: str, payload: FarmCreate, version: int, request: Request, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    client_ip = get_client_ip(request)
    return svc.update_farm(actor, farm_id, payload, version, client_ip=client_ip, device_id=get_device_id(request))


@app.delete("/api/v1/farms/{farm_id}", status_code=200)
def delete_farm(farm_id: str, request: Request, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    client_ip = get_client_ip(request)
    try:
        svc.delete_farm(actor, farm_id, client_ip=client_ip, device_id=get_device_id(request))
        return {"status": "deleted", "farm_id": farm_id}
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


@app.post("/api/v1/media", status_code=201)
async def upload_media(purpose: str = Form(...), file: UploadFile = File(...), actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    content = await file.read(settings.media_max_bytes + 1)
    return svc.save_media(actor, content, file.content_type or "application/octet-stream", purpose)


@app.get("/api/v1/media/{media_id}")
def get_media(media_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    content, content_type = svc.media_content(actor, media_id)
    return Response(content=content, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/v1/farms/{farm_id}/soil/extract", response_model=SoilExtraction)
def extract_soil(farm_id: str, media_id: str, locale: str = "en-IN", actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.extract_soil(actor, farm_id, media_id, locale)


@app.post("/api/v1/farms/{farm_id}/soil", response_model=SoilTest, status_code=201)
def save_soil(farm_id: str, payload: SoilTestCreate, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.save_soil_test(actor, farm_id, payload)


@app.get("/api/v1/farms/{farm_id}/soil", response_model=SoilTest | None)
def get_soil(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    farm = svc.farm(actor, farm_id)
    return svc.latest_soil(farm.id)


@app.get("/api/v1/farms/{farm_id}/soil/profile")
def soil_profile(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.soil_profile(actor, farm_id)


@app.get("/api/v1/farms/{farm_id}/fertilizer")
def fertilizer(farm_id: str, crop: str, season: Literal["kharif", "rabi", "summer"] | None = None, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.fertilizer(actor, farm_id, crop, season)


@app.post("/api/v1/farms/{farm_id}/evidence/refresh", status_code=201)
def refresh_evidence(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.refresh_evidence(actor, farm_id)


@app.get("/api/v1/farms/{farm_id}/evidence")
def list_evidence(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.evidence(actor, farm_id)


@app.post("/api/v1/farms/{farm_id}/advisories", response_model=Advisory, status_code=201)
def create_advisory(farm_id: str, payload: AdvisoryRequest, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.create_advisory(actor, farm_id, payload)


@app.get("/api/v1/farms/{farm_id}/advisories", response_model=list[Advisory])
def list_advisories(farm_id: str, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.advisories(actor, farm_id)


@app.get("/api/v1/farms/{farm_id}/crop-recommendations", response_model=CropRecommendationResult)
def crop_recommendations(farm_id: str, season: Literal["kharif", "rabi", "summer"] | None = None, locale: str = "en-IN", actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.crop_recommendations(actor, farm_id, season=season, locale=locale)


@app.patch("/api/v1/actions/{action_id}")
def update_action(action_id: str, payload: ActionUpdate, actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.update_action(actor, action_id, payload)


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


@app.get("/api/v1/expert/cases")
def expert_cases(actor: Actor = Depends(require_roles(Role.expert)), svc: AppService = Depends(service)):
    return svc.expert_cases(actor)


@app.patch("/api/v1/expert/cases/{case_id}")
def review_case(case_id: str, payload: ExpertReview, actor: Actor = Depends(require_roles(Role.expert)), svc: AppService = Depends(service)):
    return svc.review_case(actor, case_id, payload)


@app.post("/api/v1/voice/transcribe", response_model=VoiceTranscription)
async def transcribe(file: UploadFile = File(...), locale: str = Form("en-IN"), actor: Actor = Depends(current_actor)):
    content = await file.read(settings.media_max_bytes + 1)
    transcript, confidence = VoiceProvider(settings).transcribe(content, locale, file.content_type or "audio/webm")
    return VoiceTranscription(transcript=transcript, locale=locale, confidence=confidence, provider="google_cloud_speech")


@app.post("/api/v1/voice/speak")
def speak(payload: SpeechRequest, actor: Actor = Depends(current_actor)):
    content, content_type = VoiceProvider(settings).speak(payload.text, payload.locale)
    return Response(content=content, media_type=content_type)

@app.get("/api/v1/farms/{farm_id}/satellite/map")
def satellite_map(farm_id: str, index: str = "NDVI", days: int = Query(30, ge=7, le=120), locale: str = "en-IN", actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    from .satellite_explain import explain_map, narrative, scene_note, simple_label
    farm = svc.farm(actor, farm_id)
    result = svc.satellite_map(actor, farm_id, index=index, days=days)
    # The stored map is shared across languages; the plain-language text is added per request.
    zones = [z.model_copy(update={"simple_label": simple_label(result.index, z.id - 1, locale)}) for z in result.zones]
    has_boundary = len(farm.boundary_coordinates or []) >= 3
    return result.model_copy(update={
        "zones": zones,
        "simple_summary": explain_map(result.index, zones, result.scene_date, has_boundary, locale),
        "acquisition_note": scene_note(result.scene_date, result.clear_percent, has_boundary, locale) or result.acquisition_note,
        "field_status_narrative": narrative(result.index, result.median, zones, locale) or result.field_status_narrative,
    })


@app.get("/api/v1/farms/{farm_id}/satellite/image")
def satellite_image(farm_id: str, index: str = "NDVI", days: int = Query(30, ge=7, le=120), actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    content = svc.satellite_image(actor, farm_id, index=index, days=days)
    return Response(content=content, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/v1/farms/{farm_id}/weather/operational")
def weather_operational(farm_id: str, season: Literal["kharif", "rabi", "summer"] | None = None, locale: str = "en-IN", actor: Actor = Depends(current_actor), svc: AppService = Depends(service)):
    return svc.weather_operations(actor, farm_id, season=season, locale=locale)


import time

_CHAT_SESSIONS: dict[str, dict[str, Any]] = {}
CHAT_SESSION_TTL_SECONDS = 300  # 5 minutes inactivity timeout


def _cleanup_expired_chat_sessions():
    now = time.time()
    expired = [
        sid for sid, sess in _CHAT_SESSIONS.items()
        if now - sess.get("last_active", 0) > CHAT_SESSION_TTL_SECONDS
    ]
    for sid in expired:
        _CHAT_SESSIONS.pop(sid, None)


@app.post("/api/v1/farms/{farm_id}/chat", response_model=FarmChatResponse)
def farm_chat(
    farm_id: str,
    payload: FarmChatRequest,
    actor: Actor = Depends(current_actor),
    svc: AppService = Depends(service),
):
    _cleanup_expired_chat_sessions()
    farm = svc.farm(actor, farm_id)

    session_id = payload.session_id or f"sess_{uuid4().hex[:12]}"
    sess = _CHAT_SESSIONS.get(session_id)
    if not sess or sess.get("farm_id") != farm_id:
        sess = {
            "farm_id": farm_id,
            "history": [],
            "last_active": time.time(),
        }
        _CHAT_SESSIONS[session_id] = sess

    sess["last_active"] = time.time()

    operational = svc.weather_operations(actor, farm_id, locale=payload.locale)

    from .providers.gemini import GeminiProvider
    from .settings import get_settings
    provider = GeminiProvider(get_settings())

    answer = provider.followup_chat(
        locale=payload.locale,
        farm=farm.model_dump(),
        message=payload.message,
        conversation_history=sess["history"],
        weather_context={"district": farm.district, "state": farm.state_name},
        operational_context={k: v for k, v in operational.items() if k != "thresholds"},
    )

    sess["history"].append({"role": "user", "text": payload.message})
    sess["history"].append({"role": "assistant", "text": answer})

    return FarmChatResponse(
        session_id=session_id,
        response=answer,
        locale=payload.locale,
        expires_in_seconds=CHAT_SESSION_TTL_SECONDS,
        cleaned_up=False,
    )


@app.delete("/api/v1/farms/{farm_id}/chat/{session_id}")
def end_farm_chat(farm_id: str, session_id: str):
    _CHAT_SESSIONS.pop(session_id, None)
    return {"cleaned_up": True, "session_id": session_id, "detail": "Session state purged from memory."}


_PINCODE_CACHE: dict[str, dict[str, Any]] = {}


STATE_NAME_TO_CODE: dict[str, str] = {
    "maharashtra": "MH",
    "telangana": "TG",
    "karnataka": "KA",
    "andhra pradesh": "AP",
    "gujarat": "GJ",
    "madhya pradesh": "MP",
    "rajasthan": "RJ",
    "punjab": "PB",
    "haryana": "HR",
    "uttar pradesh": "UP",
    "bihar": "BR",
    "west bengal": "WB",
    "odisha": "OD",
    "tamil nadu": "TN",
    "kerala": "KL",
    "assam": "AS",
    "chhattisgarh": "CG",
    "jharkhand": "JH",
    "uttarakhand": "UK",
    "himachal pradesh": "HP",
    "jammu and kashmir": "JK",
    "goa": "GA",
    "delhi": "DL",
    "tripura": "TR",
    "meghalaya": "ML",
    "manipur": "MN",
    "nagaland": "NL",
    "mizoram": "MZ",
    "arunachal pradesh": "AR",
    "sikkim": "SK",
    "puducherry": "PY",
    "ladakh": "LA",
    "chandigarh": "CH",
}


@app.get("/api/v1/geo/pincode/{pincode}")
def lookup_pincode(pincode: str):
    clean = pincode.strip()
    if not clean.isdigit() or len(clean) != 6:
        raise HTTPException(status_code=400, detail="Pincode must be a 6-digit Indian postal code")

    if clean in _PINCODE_CACHE:
        return _PINCODE_CACHE[clean]

    # 1. Primary: pincodeapi.in (exact post offices, villages, lat/lon per village)
    try:
        import requests
        resp = requests.get(
            f"https://api.pincodeapi.in/api/v1/pincode/{clean}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KISANAI-C2C/1.0)"},
            timeout=4.0,
        )
        if resp.status_code == 200:
            payload = resp.json()
            if payload.get("success") and payload.get("data", {}).get("post_offices"):
                raw_offices = payload["data"]["post_offices"]
                first = raw_offices[0]
                state_name = first.get("state") or ""
                state_code = STATE_NAME_TO_CODE.get(state_name.strip().lower(), "IN")
                district = first.get("district") or ""

                post_offices = []
                for po in raw_offices:
                    lat_val = po.get("latitude")
                    lon_val = po.get("longitude")
                    post_offices.append({
                        "name": po.get("office_name", ""),
                        "office_type": po.get("office_type", ""),
                        "delivery_status": po.get("delivery_status", ""),
                        "district": po.get("district", district),
                        "state": po.get("state", state_name),
                        "latitude": float(lat_val) if lat_val is not None else None,
                        "longitude": float(lon_val) if lon_val is not None else None,
                        "digipin": po.get("digipin", ""),
                    })

                valid_office = next((o for o in post_offices if o["latitude"] and o["longitude"]), post_offices[0])

                result = {
                    "pincode": clean,
                    "district": district,
                    "state_code": state_code,
                    "state_name": state_name,
                    "village": valid_office["name"],
                    "latitude": valid_office["latitude"],
                    "longitude": valid_office["longitude"],
                    "post_offices": post_offices,
                    "source": "pincodeapi.in",
                }
                _PINCODE_CACHE[clean] = result
                return result
    except Exception:
        pass

    # 2. Fallback: zippopotam.us
    try:
        import requests
        resp = requests.get(
            f"https://api.zippopotam.us/in/{clean}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KISANAI-C2C/1.0)"},
            timeout=3.0,
        )
        if resp.status_code == 200:
            payload = resp.json()
            places = payload.get("places", [])
            if places:
                first = places[0]
                place_name = first.get("place name", "")
                state_name = first.get("state", "")
                state_code = STATE_NAME_TO_CODE.get(state_name.lower(), first.get("state abbreviation") or "IN")
                lat = float(first["latitude"])
                lon = float(first["longitude"])

                post_offices = [
                    {
                        "name": p.get("place name", ""),
                        "office_type": "PO",
                        "delivery_status": "Delivery",
                        "district": place_name,
                        "state": state_name,
                        "latitude": float(p.get("latitude", lat)),
                        "longitude": float(p.get("longitude", lon)),
                        "digipin": "",
                    }
                    for p in places
                ]

                # zippopotam has no district; take it from reverse geocoding of the coordinates.
                try:
                    district_name = reverse_geocode(lat, lon).get("district") or place_name
                except HTTPException:
                    district_name = place_name
                result = {
                    "pincode": clean,
                    "district": district_name,
                    "state_code": state_code,
                    "state_name": state_name,
                    "village": place_name,
                    "latitude": lat,
                    "longitude": lon,
                    "post_offices": post_offices,
                    "source": "zippopotam.us",
                }
                _PINCODE_CACHE[clean] = result
                return result
    except Exception:
        pass

    raise HTTPException(status_code=503, detail="PIN code lookup services are unreachable. Use GPS or pick the location on the map.")


_REVERSE_GEO_CACHE: dict[str, dict] = {}

MAHARASHTRA_DISTRICT_CENTROIDS = [
    ("Ahmednagar", "MH", "Maharashtra", 19.0952, 74.7496),
    ("Akola", "MH", "Maharashtra", 20.7002, 77.0082),
    ("Amravati", "MH", "Maharashtra", 20.9374, 77.7796),
    ("Chhatrapati Sambhajinagar", "MH", "Maharashtra", 19.8762, 75.3433),
    ("Beed", "MH", "Maharashtra", 18.9891, 75.7601),
    ("Bhandara", "MH", "Maharashtra", 21.1714, 79.6543),
    ("Buldhana", "MH", "Maharashtra", 20.5293, 76.1843),
    ("Chandrapur", "MH", "Maharashtra", 19.9615, 79.2961),
    ("Dhule", "MH", "Maharashtra", 20.9042, 74.7749),
    ("Gadchiroli", "MH", "Maharashtra", 20.1849, 79.9948),
    ("Gondia", "MH", "Maharashtra", 21.4604, 80.1961),
    ("Hingoli", "MH", "Maharashtra", 19.7196, 77.1476),
    ("Jalgaon", "MH", "Maharashtra", 21.0077, 75.5626),
    ("Jalna", "MH", "Maharashtra", 19.8410, 75.8864),
    ("Kolhapur", "MH", "Maharashtra", 16.7050, 74.2433),
    ("Latur", "MH", "Maharashtra", 18.4088, 76.5604),
    ("Mumbai City", "MH", "Maharashtra", 18.9220, 72.8347),
    ("Mumbai Suburban", "MH", "Maharashtra", 19.1136, 72.8697),
    ("Nagpur", "MH", "Maharashtra", 21.1458, 79.0882),
    ("Nanded", "MH", "Maharashtra", 19.1383, 77.3210),
    ("Nandurbar", "MH", "Maharashtra", 21.3736, 74.2405),
    ("Nashik", "MH", "Maharashtra", 19.9975, 73.7898),
    ("Dharashiv", "MH", "Maharashtra", 18.1861, 76.0419),
    ("Palghar", "MH", "Maharashtra", 19.6967, 72.7699),
    ("Parbhani", "MH", "Maharashtra", 19.2686, 76.7711),
    ("Pune", "MH", "Maharashtra", 18.5204, 73.8567),
    ("Raigad", "MH", "Maharashtra", 18.5158, 73.1812),
    ("Ratnagiri", "MH", "Maharashtra", 16.9902, 73.3120),
    ("Sangli", "MH", "Maharashtra", 16.8524, 74.5815),
    ("Satara", "MH", "Maharashtra", 17.6805, 74.0183),
    ("Sindhudurg", "MH", "Maharashtra", 16.1158, 73.6934),
    ("Solapur", "MH", "Maharashtra", 17.6599, 75.9064),
    ("Thane", "MH", "Maharashtra", 19.2183, 72.9781),
    ("Wardha", "MH", "Maharashtra", 20.7453, 78.6022),
    ("Washim", "MH", "Maharashtra", 20.1112, 77.1362),
    ("Yavatmal", "MH", "Maharashtra", 20.3888, 78.1204),
]


@app.get("/api/v1/geo/reverse")
def reverse_geocode(latitude: float, longitude: float):
    cache_key = f"{round(latitude, 3)},{round(longitude, 3)}"
    if cache_key in _REVERSE_GEO_CACHE:
        return _REVERSE_GEO_CACHE[cache_key]

    # Try OpenStreetMap Nominatim reverse geocode
    try:
        import requests
        resp = requests.get(
            f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}&zoom=14&addressdetails=1",
            headers={"User-Agent": "KISANAI-C2C-Agricultural-Intelligence/1.0"},
            timeout=3.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            addr = data.get("address", {})
            district = (
                addr.get("state_district")
                or addr.get("district")
                or addr.get("county")
                or ""
            )
            district = district.replace(" District", "").strip()
            state = addr.get("state", "")
            village = (
                addr.get("village")
                or addr.get("town")
                or addr.get("suburb")
                or addr.get("hamlet")
                or addr.get("city")
                or ""
            )
            postcode = addr.get("postcode", "")
            sc = STATE_NAME_TO_CODE.get(state.lower(), "IN")
            if district:
                result = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "district": district,
                    "state_name": state,
                    "state_code": sc,
                    "village": village,
                    "pincode": postcode,
                    "source": "nominatim_reverse",
                }
                _REVERSE_GEO_CACHE[cache_key] = result
                return result
    except Exception:
        pass

    # Offline fallback: nearest Maharashtra district centroid, only when the point is plausibly
    # in that district (within ~45 km); elsewhere report that the place could not be resolved.
    best = min(
        MAHARASHTRA_DISTRICT_CENTROIDS,
        key=lambda d: (d[3] - latitude) ** 2 + (d[4] - longitude) ** 2,
    )
    dist, sc, sn, dlat, dlon = best
    if ((dlat - latitude) ** 2 + (dlon - longitude) ** 2) ** 0.5 > 0.4:
        raise HTTPException(status_code=503, detail="Place name lookup is unavailable for these coordinates.")
    result = {
        "latitude": latitude,
        "longitude": longitude,
        "district": dist,
        "state_name": sn,
        "state_code": sc,
        "village": "",
        "pincode": None,
        "source": "nearest_district_centroid",
    }
    _REVERSE_GEO_CACHE[cache_key] = result
    return result


@app.get("/api/v1/geo/ip")
def ip_geocode(request: Request):
    """Approximate location from the caller's network address (city level), when GPS is unavailable."""
    import ipaddress
    client_ip = get_client_ip(request)
    try:
        public = ipaddress.ip_address(client_ip).is_global
    except ValueError:
        public = False
    if public:
        try:
            import requests
            resp = requests.get(f"https://ipapi.co/{client_ip}/json/", headers={"User-Agent": "KISANAI/1.0"}, timeout=3)
            data = resp.json() if resp.status_code == 200 else {}
            if data.get("latitude") is not None and data.get("longitude") is not None:
                region = data.get("region") or ""
                return {
                    "latitude": round(float(data["latitude"]), 4),
                    "longitude": round(float(data["longitude"]), 4),
                    "district": data.get("city") or "",
                    "state_name": region,
                    "state_code": STATE_NAME_TO_CODE.get(region.lower(), data.get("region_code") or ""),
                    "village": data.get("city") or "",
                    "pincode": data.get("postal") or None,
                    "source": "ipapi.co (city-level, approximate)",
                }
        except Exception:
            pass
    raise HTTPException(status_code=404, detail="Network location is not available. Enter the PIN code or use GPS.")


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .settings import PROJECT_ROOT

candidates = [
    PROJECT_ROOT / "static",           # Docker container (/app/static)
    PROJECT_ROOT / "apps/web/dist",    # Local dev build
]
static_dir = next((p for p in candidates if p.exists() and (p / "index.html").exists()), None)

if static_dir and static_dir.exists():
    if (static_dir / "assets").exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("health"):
            raise HTTPException(status_code=404, detail="Not Found")
        
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        
        # The page itself is never cached, so a new deploy shows up on the next load;
        # hashed files under /assets stay cacheable.
        return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})
