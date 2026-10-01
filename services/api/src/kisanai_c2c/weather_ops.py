"""Turns a coordinate weather forecast into farm-operation advice.

Inputs are evidence snapshots as stored by WeatherProvider (Open-Meteo daily values named
"<prefix>_<YYYY-MM-DD>", plus the optional "forecast_start_date" marker that separates the
observed past days from the forecast). Every threshold lives in THRESHOLDS so agronomists
can tune it without touching the logic.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

SUPPORTED_LOCALES = ("en-IN", "hi-IN", "mr-IN", "te-IN", "kn-IN")

THRESHOLDS = {
    # Spraying: daily max wind (km/h), rain probability (%) and rain amount (mm).
    "spray_safe_wind": 15.0,
    "spray_caution_wind": 25.0,
    "spray_safe_rain_prob": 30,
    "spray_caution_rain_prob": 60,
    "spray_safe_rain_mm": 1.0,
    "spray_caution_rain_mm": 5.0,
    # Kharif sowing: rain of the past 7 days plus the next 3 days (mm). Maharashtra guidance is
    # to sow after 75-100 mm of cumulative monsoon rain has wetted the root zone.
    "kharif_sowing_ready_mm": 75.0,
    "kharif_sowing_marginal_mm": 35.0,
    # Rabi / summer sowing: heavy rain in the next 3 days risks seed rot and crusting.
    "sowing_heavy_rain_3d_mm": 20.0,
    "rabi_sowing_max_temp": 34.0,
    # Irrigation: crop water demand = ET0 x crop coefficient, compared with forecast rain.
    "crop_coefficient": 0.8,
    "irrigation_deficit_mm": 25.0,
    "irrigation_monitor_deficit_mm": 10.0,
    # Drainage, from IMD rainfall categories (heavy rain is 64.5 mm/day or more).
    "heavy_rain_day_mm": 64.5,
    "moderate_rain_day_mm": 35.0,
    "drainage_high_7d_mm": 100.0,
    "drainage_moderate_7d_mm": 60.0,
    # Temperature stress.
    "heat_high_c": 40.0,
    "heat_moderate_c": 37.0,
    "cold_low_c": 8.0,
    # Hourly spray windows: daylight hours with light wind, no rain and a dry spell after.
    "spray_hour_max_wind": 12.0,
    "spray_hour_max_rain_prob": 30,
    "spray_hour_max_temp": 32.0,
    "spray_rainfast_hours": 2,
    # Leaf-wetness proxy for fungal disease: hours a day with RH >= 90 % at 15-30 C.
    "disease_rh": 90.0,
    "disease_temp_range": (15.0, 30.0),
    "disease_high_hours": 10,
    "disease_moderate_hours": 6,
    # Plant-available soil water (fraction between wilting point and field capacity).
    "soil_wet_fraction": 0.6,
    "soil_dry_fraction": 0.35,
}

# Approximate field capacity / wilting point (m3/m3) by soil type, used to turn the
# Open-Meteo land-model soil moisture into the share of plant-available water.
SOIL_WATER_LIMITS: dict[str, tuple[float, float]] = {
    "black": (0.42, 0.24),
    "clay": (0.40, 0.25),
    "alluvial": (0.30, 0.14),
    "loam": (0.27, 0.12),
    "red": (0.24, 0.12),
    "sandy": (0.12, 0.05),
    "unknown": (0.30, 0.14),
}

_HOURLY_PREFIXES = ("temp", "humidity", "rain_prob", "rain", "wind", "soil_moisture_top", "soil_moisture_root")

_DAILY_PREFIXES = {
    "rainfall": "rain_mm",
    "rain_probability": "rain_prob",
    "temp_max": "temp_max",
    "temp_min": "temp_min",
    "humidity_mean": "humidity",
    "wind_max": "wind_max",
    "gust_max": "gust_max",
    "et0": "et0",
    "weather_code": "weather_code",
}


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=UTC)


def latest_weather_snapshot(evidence: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Newest weather_forecast snapshot that carries numeric rainfall values."""
    candidates = [
        snap for snap in evidence
        if snap.get("kind") == "weather_forecast"
        and any(str(v.get("name", "")).startswith("rainfall_") for v in snap.get("values", []))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda snap: _parse_time(snap.get("fetched_at") or snap.get("issued_at")))


def daily_series(snapshot: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a snapshot into (observed past days, forecast days), each sorted by date.

    Legacy snapshots named "rainfall_day_N" are treated as forecast days in order.
    """
    if not snapshot:
        return [], []
    days: dict[str, dict[str, Any]] = {}
    start: str | None = None
    for item in snapshot.get("values", []):
        name = str(item.get("name", ""))
        value = item.get("value")
        if name == "forecast_start_date":
            start = str(value) if value else None
            continue
        if name.startswith("rainfall_day_"):
            key = f"day-{int(name.removeprefix('rainfall_day_')):02d}" if name.removeprefix("rainfall_day_").isdigit() else name
            days.setdefault(key, {"date": key})["rain_mm"] = value
            continue
        for prefix, field in _DAILY_PREFIXES.items():
            head = f"{prefix}_"
            if name.startswith(head):
                suffix = name[len(head):]
                if len(suffix) == 10 and suffix[4] == "-" and suffix[7] == "-":
                    days.setdefault(suffix, {"date": suffix})[field] = value
                break
    ordered = [days[key] for key in sorted(days)]
    if start:
        past = [day for day in ordered if day["date"] < start]
        future = [day for day in ordered if day["date"] >= start]
        return past, future
    return [], ordered


def hourly_series(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Hourly rows [{time, temp, humidity, rain, rain_prob, wind, soil_moisture_top, soil_moisture_root}]."""
    if not snapshot:
        return []
    hours: dict[str, dict[str, Any]] = {}
    # Longest prefixes first so "rain_prob" is not read as "rain".
    prefixes = sorted(_HOURLY_PREFIXES, key=len, reverse=True)
    for item in snapshot.get("values", []):
        name = str(item.get("name", ""))
        if not name.startswith("hourly_"):
            continue
        rest = name[len("hourly_"):]
        for prefix in prefixes:
            if rest.startswith(prefix + "_") and "T" in rest[len(prefix) + 1:]:
                stamp = rest[len(prefix) + 1:]
                hours.setdefault(stamp, {"time": stamp})[prefix] = item.get("value")
                break
    return [hours[key] for key in sorted(hours)]


def available_water(volumetric: float | None, soil_type: str) -> float | None:
    if volumetric is None:
        return None
    capacity, wilting = SOIL_WATER_LIMITS.get(soil_type, SOIL_WATER_LIMITS["unknown"])
    return round(max(0.0, min(1.0, (volumetric - wilting) / (capacity - wilting))), 2)


def spray_windows(hours: list[dict[str, Any]], limit: int = 4) -> list[dict[str, str]]:
    """Daylight stretches of 2+ hours with light wind, low rain chance and no rain soon after."""
    t = THRESHOLDS
    def ok(index: int) -> bool:
        hour = hours[index]
        clock = int(hour["time"][11:13])
        wind, prob = _num(hour.get("wind")), _num(hour.get("rain_prob")) or 0.0
        temp, rain = _num(hour.get("temp")), _num(hour.get("rain")) or 0.0
        if not 6 <= clock <= 17 or wind is None or wind > t["spray_hour_max_wind"]:
            return False
        if prob >= t["spray_hour_max_rain_prob"] or rain > 0 or (temp is not None and temp > t["spray_hour_max_temp"]):
            return False
        after = hours[index + 1:index + 1 + t["spray_rainfast_hours"]]
        return all((_num(h.get("rain")) or 0.0) == 0 for h in after)

    windows: list[dict[str, str]] = []
    run: list[int] = []
    for index in range(len(hours) + 1):
        if index < len(hours) and ok(index) and (not run or index == run[-1] + 1 and hours[index]["time"][:10] == hours[run[0]]["time"][:10]):
            run.append(index)
            continue
        if len(run) >= 2:
            windows.append({"date": hours[run[0]]["time"][:10], "start": hours[run[0]]["time"][11:16], "end": f"{int(hours[run[-1]]['time'][11:13]) + 1:02d}:00"})
        run = [index] if index < len(hours) and ok(index) else []
    return windows[:limit]


def disease_hours_by_day(hours: list[dict[str, Any]]) -> dict[str, int]:
    """Hours per day with RH >= 90 % at 15-30 C, a common leaf-wetness proxy for fungal infection."""
    t = THRESHOLDS
    low, high = t["disease_temp_range"]
    counts: dict[str, int] = {}
    for hour in hours:
        humidity, temp = _num(hour.get("humidity")), _num(hour.get("temp"))
        day = hour["time"][:10]
        counts.setdefault(day, 0)
        if humidity is not None and temp is not None and humidity >= t["disease_rh"] and low <= temp <= high:
            counts[day] += 1
    return counts


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _sum(days: list[dict[str, Any]], field: str) -> float:
    return sum(_num(day.get(field)) or 0.0 for day in days)


def forecast_rain_total(evidence: list[dict[str, Any]], days: int = 7) -> float | None:
    _, future = daily_series(latest_weather_snapshot(evidence))
    values = [_num(day.get("rain_mm")) for day in future[:days]]
    values = [value for value in values if value is not None]
    return round(sum(values), 1) if values else None


def forecast_mean(evidence: list[dict[str, Any]], field: str, days: int = 7) -> float | None:
    _, future = daily_series(latest_weather_snapshot(evidence))
    values = [_num(day.get(field)) for day in future[:days]]
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 1) if values else None


def spray_status(day: dict[str, Any]) -> str:
    t = THRESHOLDS
    wind = _num(day.get("wind_max"))
    prob = _num(day.get("rain_prob")) or 0.0
    rain = _num(day.get("rain_mm")) or 0.0
    if wind is None:
        return "unknown"
    if wind < t["spray_safe_wind"] and prob < t["spray_safe_rain_prob"] and rain < t["spray_safe_rain_mm"]:
        return "safe"
    if wind < t["spray_caution_wind"] and prob < t["spray_caution_rain_prob"] and rain < t["spray_caution_rain_mm"]:
        return "caution"
    return "avoid"


# ---------------------------------------------------------------------------
# Localised text. Each entry is a template formatted with the computed numbers.
# ---------------------------------------------------------------------------

TEXT: dict[str, dict[str, str]] = {
    "no_data": {
        "en-IN": "Forecast not available yet. Refresh weather to get advice.",
        "hi-IN": "मौसम पूर्वानुमान अभी उपलब्ध नहीं है। सलाह के लिए मौसम रीफ्रेश करें।",
        "mr-IN": "हवामान अंदाज अजून उपलब्ध नाही. सल्ल्यासाठी हवामान रिफ्रेश करा.",
        "te-IN": "వాతావరణ సూచన ఇంకా అందుబాటులో లేదు. సలహా కోసం రిఫ్రెష్ చేయండి.",
        "kn-IN": "ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ ಇನ್ನೂ ಲಭ್ಯವಿಲ್ಲ. ಸಲಹೆಗಾಗಿ ರಿಫ್ರೆಶ್ ಮಾಡಿ.",
    },
    # Sowing
    "sow_kharif_ready": {
        "en-IN": "Enough soil moisture for sowing: {moisture:.0f} mm rain in the last 7 days and next 3 days.",
        "hi-IN": "बुवाई के लिए पर्याप्त नमी: पिछले 7 और अगले 3 दिनों में {moisture:.0f} मिमी वर्षा।",
        "mr-IN": "पेरणीसाठी पुरेसा ओलावा: मागील ७ व पुढील ३ दिवसांत {moisture:.0f} मिमी पाऊस.",
        "te-IN": "విత్తడానికి తగిన తేమ: గత 7 మరియు రాబోయే 3 రోజుల్లో {moisture:.0f} మి.మీ వర్షం.",
        "kn-IN": "ಬಿತ್ತನೆಗೆ ಸಾಕಷ್ಟು ತೇವಾಂಶ: ಹಿಂದಿನ 7 ಮತ್ತು ಮುಂದಿನ 3 ದಿನಗಳಲ್ಲಿ {moisture:.0f} ಮಿ.ಮೀ ಮಳೆ.",
    },
    "sow_kharif_marginal": {
        "en-IN": "Only {moisture:.0f} mm rain (last 7 + next 3 days). Wait for about {needed:.0f} mm more before sowing.",
        "hi-IN": "केवल {moisture:.0f} मिमी वर्षा। बुवाई से पहले लगभग {needed:.0f} मिमी और वर्षा का इंतज़ार करें।",
        "mr-IN": "फक्त {moisture:.0f} मिमी पाऊस. पेरणीपूर्वी अजून सुमारे {needed:.0f} मिमी पावसाची वाट पाहा.",
        "te-IN": "కేవలం {moisture:.0f} మి.మీ వర్షం. విత్తే ముందు మరో {needed:.0f} మి.మీ వర్షం కోసం వేచి ఉండండి.",
        "kn-IN": "ಕೇವಲ {moisture:.0f} ಮಿ.ಮೀ ಮಳೆ. ಬಿತ್ತನೆಗೆ ಮುನ್ನ ಇನ್ನೂ {needed:.0f} ಮಿ.ಮೀ ಮಳೆಗಾಗಿ ಕಾಯಿರಿ.",
    },
    "sow_kharif_wait": {
        "en-IN": "Soil too dry ({moisture:.0f} mm rain). Do not dry-sow; germination may fail.",
        "hi-IN": "मिट्टी बहुत सूखी है ({moisture:.0f} मिमी)। सूखी बुवाई न करें, अंकुरण विफल हो सकता है।",
        "mr-IN": "जमीन खूप कोरडी ({moisture:.0f} मिमी). धूळपेरणी टाळा, उगवण अयशस्वी होऊ शकते.",
        "te-IN": "నేల చాలా పొడిగా ఉంది ({moisture:.0f} మి.మీ). పొడి విత్తనం వద్దు.",
        "kn-IN": "ಮಣ್ಣು ತುಂಬಾ ಒಣಗಿದೆ ({moisture:.0f} ಮಿ.ಮೀ). ಒಣ ಬಿತ್ತನೆ ಬೇಡ.",
    },
    "sow_heavy_rain": {
        "en-IN": "{rain3:.0f} mm rain expected in the next 3 days. Delay sowing to avoid seed rot and crusting.",
        "hi-IN": "अगले 3 दिनों में {rain3:.0f} मिमी वर्षा संभावित। बीज सड़न से बचने के लिए बुवाई टालें।",
        "mr-IN": "पुढील ३ दिवसांत {rain3:.0f} मिमी पाऊस अपेक्षित. बियाणे कुजू नये म्हणून पेरणी पुढे ढकला.",
        "te-IN": "రాబోయే 3 రోజుల్లో {rain3:.0f} మి.మీ వర్షం. విత్తనం కుళ్లకుండా విత్తడం వాయిదా వేయండి.",
        "kn-IN": "ಮುಂದಿನ 3 ದಿನಗಳಲ್ಲಿ {rain3:.0f} ಮಿ.ಮೀ ಮಳೆ. ಬೀಜ ಕೊಳೆಯದಂತೆ ಬಿತ್ತನೆ ಮುಂದೂಡಿ.",
    },
    "sow_rabi_ready": {
        "en-IN": "Dry, mild days ahead (around {tmax:.0f}°C). A good time for rabi sowing while the soil still holds moisture.",
        "hi-IN": "आगे सूखे और सामान्य दिन (औसत अधिकतम {tmax:.0f}°C)। संचित नमी पर रबी बुवाई के लिए उपयुक्त।",
        "mr-IN": "पुढे कोरडे व सौम्य दिवस (सरासरी कमाल {tmax:.0f}°C). जमिनीतील ओलाव्यावर रब्बी पेरणीस योग्य.",
        "te-IN": "రాబోయే రోజులు పొడిగా, మితంగా (సగటు గరిష్ఠ {tmax:.0f}°C). రబీ విత్తనానికి అనుకూలం.",
        "kn-IN": "ಮುಂದಿನ ದಿನಗಳು ಒಣ ಮತ್ತು ಸೌಮ್ಯ (ಸರಾಸರಿ ಗರಿಷ್ಠ {tmax:.0f}°C). ರಬಿ ಬಿತ್ತನೆಗೆ ಸೂಕ್ತ.",
    },
    "sow_rabi_warm": {
        "en-IN": "Days still warm (avg max {tmax:.0f}°C). Chickpea and rabi sorghum can start; wait for cooler nights for wheat.",
        "hi-IN": "दिन अभी गर्म हैं (औसत अधिकतम {tmax:.0f}°C)। चना व रबी ज्वार बो सकते हैं; गेहूं के लिए ठंडी रातों का इंतज़ार करें।",
        "mr-IN": "दिवस अजून उष्ण (सरासरी कमाल {tmax:.0f}°C). हरभरा व रब्बी ज्वारी पेरता येईल; गव्हासाठी थंड रात्रींची वाट पाहा.",
        "te-IN": "పగలు ఇంకా వేడిగా ఉంది (సగటు గరిష్ఠ {tmax:.0f}°C). శనగ, రబీ జొన్న విత్తవచ్చు; గోధుమకు చల్లని రాత్రుల కోసం ఆగండి.",
        "kn-IN": "ಹಗಲು ಇನ್ನೂ ಬಿಸಿ (ಸರಾಸರಿ ಗರಿಷ್ಠ {tmax:.0f}°C). ಕಡಲೆ, ರಬಿ ಜೋಳ ಬಿತ್ತಬಹುದು; ಗೋಧಿಗೆ ತಂಪು ರಾತ್ರಿಗಳಿಗಾಗಿ ಕಾಯಿರಿ.",
    },
    "sow_rabi_dry": {
        "en-IN": "No heavy rain in the next 3 days ({rain3:.0f} mm). Rabi sowing can go ahead on stored soil moisture.",
        "hi-IN": "अगले 3 दिनों में भारी वर्षा नहीं ({rain3:.0f} मिमी)। संचित नमी पर रबी बुवाई कर सकते हैं।",
        "mr-IN": "पुढील ३ दिवसांत जोराचा पाऊस नाही ({rain3:.0f} मिमी). जमिनीतील ओलाव्यावर रब्बी पेरणी करता येईल.",
        "te-IN": "రాబోయే 3 రోజుల్లో భారీ వర్షం లేదు ({rain3:.0f} మి.మీ). నిల్వ తేమపై రబీ విత్తనం వేయవచ్చు.",
        "kn-IN": "ಮುಂದಿನ 3 ದಿನಗಳಲ್ಲಿ ಭಾರೀ ಮಳೆ ಇಲ್ಲ ({rain3:.0f} ಮಿ.ಮೀ). ಸಂಗ್ರಹಿತ ತೇವದಲ್ಲಿ ರಬಿ ಬಿತ್ತನೆ ಮಾಡಬಹುದು.",
    },
    "sow_soil_moist": {
        "en-IN": "Soil holds {top:.0f}% of its available water near the surface. Enough moisture to sow now.",
        "hi-IN": "सतह के पास मिट्टी में {top:.0f}% उपलब्ध नमी है। अभी बुवाई के लिए पर्याप्त।",
        "mr-IN": "जमिनीच्या वरच्या थरात {top:.0f}% उपलब्ध ओलावा आहे. आता पेरणीस पुरेसा.",
        "te-IN": "పై పొరలో నేలలో {top:.0f}% తేమ ఉంది. ఇప్పుడు విత్తడానికి సరిపోతుంది.",
        "kn-IN": "ಮೇಲ್ಪದರದಲ್ಲಿ ಮಣ್ಣಿನಲ್ಲಿ {top:.0f}% ತೇವ ಇದೆ. ಈಗ ಬಿತ್ತಲು ಸಾಕು.",
    },
    "irr_soil_ok": {
        "en-IN": "There is still enough water around the roots ({root:.0f}%). No need to irrigate yet.",
        "hi-IN": "जड़ क्षेत्र में अभी {root:.0f}% उपलब्ध नमी है। अभी सिंचाई की ज़रूरत नहीं।",
        "mr-IN": "मुळांच्या भागात अजून {root:.0f}% उपलब्ध ओलावा आहे. अजून पाणी देण्याची गरज नाही.",
        "te-IN": "వేర్ల ప్రాంతంలో ఇంకా {root:.0f}% తేమ ఉంది. ఇప్పుడే నీరు అవసరం లేదు.",
        "kn-IN": "ಬೇರು ವಲಯದಲ್ಲಿ ಇನ್ನೂ {root:.0f}% ತೇವ ಇದೆ. ಈಗ ನೀರು ಬೇಕಿಲ್ಲ.",
    },
    "soil_moisture_note": {
        "en-IN": "Soil moisture (model estimate): top {top}%, root zone {root}% of available water.",
        "hi-IN": "मिट्टी की नमी (मॉडल अनुमान): ऊपरी {top}%, जड़ क्षेत्र {root}%।",
        "mr-IN": "जमिनीतील ओलावा (मॉडेल अंदाज): वरचा थर {top}%, मुळांचा भाग {root}%.",
        "te-IN": "నేల తేమ (మోడల్ అంచనా): పై పొర {top}%, వేర్ల ప్రాంతం {root}%.",
        "kn-IN": "ಮಣ್ಣಿನ ತೇವ (ಮಾದರಿ ಅಂದಾಜು): ಮೇಲ್ಪದರ {top}%, ಬೇರು ವಲಯ {root}%.",
    },
    "spray_hours": {
        "en-IN": "Best spray hours: {windows}.",
        "hi-IN": "छिड़काव के सर्वोत्तम घंटे: {windows}।",
        "mr-IN": "फवारणीचे योग्य तास: {windows}.",
        "te-IN": "పిచికారీకి మంచి సమయం: {windows}.",
        "kn-IN": "ಸಿಂಪಡಣೆಗೆ ಉತ್ತಮ ಸಮಯ: {windows}.",
    },
    "disease_high": {
        "en-IN": "High fungal disease risk: {hours} humid hours (RH ≥ 90%) on {date}. Scout leaves and avoid overhead irrigation.",
        "hi-IN": "फफूंद रोग का अधिक जोखिम: {date} को {hours} घंटे अधिक नमी (RH ≥ 90%)। पत्तियों की जांच करें।",
        "mr-IN": "बुरशीजन्य रोगाचा जास्त धोका: {date} रोजी {hours} तास जास्त आर्द्रता (RH ≥ 90%). पानांची पाहणी करा.",
        "te-IN": "శిలీంధ్ర వ్యాధి ఎక్కువ ప్రమాదం: {date} న {hours} గంటలు అధిక తేమ (RH ≥ 90%). ఆకులను పరిశీలించండి.",
        "kn-IN": "ಶಿಲೀಂಧ್ರ ರೋಗದ ಹೆಚ್ಚಿನ ಅಪಾಯ: {date} ರಂದು {hours} ಗಂಟೆ ಹೆಚ್ಚು ತೇವ (RH ≥ 90%). ಎಲೆಗಳನ್ನು ಪರಿಶೀಲಿಸಿ.",
    },
    "disease_moderate": {
        "en-IN": "Moderate fungal disease risk: up to {hours} humid hours a day. Keep watching for leaf spots.",
        "hi-IN": "फफूंद रोग का मध्यम जोखिम: दिन में {hours} घंटे तक अधिक नमी। पत्ती धब्बों पर नज़र रखें।",
        "mr-IN": "बुरशीजन्य रोगाचा मध्यम धोका: दिवसात {hours} तासांपर्यंत जास्त आर्द्रता. पानांवरील ठिपके पाहा.",
        "te-IN": "శిలీంధ్ర వ్యాధి మధ్యస్థ ప్రమాదం: రోజుకు {hours} గంటల వరకు అధిక తేమ.",
        "kn-IN": "ಶಿಲೀಂಧ್ರ ರೋಗದ ಮಧ್ಯಮ ಅಪಾಯ: ದಿನಕ್ಕೆ {hours} ಗಂಟೆವರೆಗೆ ಹೆಚ್ಚು ತೇವ.",
    },
    "disease_low": {
        "en-IN": "Leaves should stay dry enough over the next 3 days, so fungal disease is unlikely.",
        "hi-IN": "अगले 3 दिनों में फफूंद रोग का जोखिम कम।",
        "mr-IN": "पुढील ३ दिवसांत बुरशीजन्य रोगाचा धोका कमी.",
        "te-IN": "రాబోయే 3 రోజుల్లో శిలీంధ్ర వ్యాధి ప్రమాదం తక్కువ.",
        "kn-IN": "ಮುಂದಿನ 3 ದಿನಗಳಲ್ಲಿ ಶಿಲೀಂಧ್ರ ರೋಗದ ಅಪಾಯ ಕಡಿಮೆ.",
    },
    "sow_summer_rainfed": {
        "en-IN": "Summer crops need assured irrigation. Without an irrigation source, do not sow now.",
        "hi-IN": "गर्मी की फसलों को सुनिश्चित सिंचाई चाहिए। सिंचाई साधन के बिना अभी बुवाई न करें।",
        "mr-IN": "उन्हाळी पिकांना खात्रीशीर सिंचन लागते. सिंचनाशिवाय आता पेरणी करू नका.",
        "te-IN": "వేసవి పంటలకు నీటి వసతి తప్పనిసరి. నీటి వసతి లేకుంటే ఇప్పుడు విత్తవద్దు.",
        "kn-IN": "ಬೇಸಿಗೆ ಬೆಳೆಗಳಿಗೆ ಖಚಿತ ನೀರಾವರಿ ಬೇಕು. ನೀರಾವರಿ ಇಲ್ಲದೆ ಈಗ ಬಿತ್ತಬೇಡಿ.",
    },
    "sow_summer_ready": {
        "en-IN": "No heavy rain ahead. Sow summer crops with a pre-sowing irrigation.",
        "hi-IN": "आगे भारी वर्षा नहीं। बुवाई पूर्व सिंचाई देकर गर्मी की फसल बोएं।",
        "mr-IN": "पुढे जोराचा पाऊस नाही. पेरणीपूर्व पाणी देऊन उन्हाळी पीक पेरा.",
        "te-IN": "భారీ వర్షం లేదు. ముందస్తు తడి ఇచ్చి వేసవి పంట విత్తండి.",
        "kn-IN": "ಭಾರೀ ಮಳೆ ಇಲ್ಲ. ಬಿತ್ತನೆ ಪೂರ್ವ ನೀರು ಕೊಟ್ಟು ಬೇಸಿಗೆ ಬೆಳೆ ಬಿತ್ತಿ.",
    },
    # Spraying
    "spray_today_safe": {
        "en-IN": "Fine for spraying today: wind up to {wind:.0f} km/h and {prob:.0f}% chance of rain. Early morning is best.",
        "hi-IN": "आज छिड़काव उपयुक्त: हवा {wind:.0f} किमी/घं तक, वर्षा संभावना {prob:.0f}%। सुबह जल्दी छिड़काव करें।",
        "mr-IN": "आज फवारणीस योग्य: वारा {wind:.0f} किमी/तास पर्यंत, पावसाची शक्यता {prob:.0f}%. सकाळी लवकर फवारणी करा.",
        "te-IN": "ఈరోజు పిచికారీకి అనుకూలం: గాలి {wind:.0f} కి.మీ/గం, వర్ష అవకాశం {prob:.0f}%. ఉదయాన్నే పిచికారీ చేయండి.",
        "kn-IN": "ಇಂದು ಸಿಂಪಡಣೆಗೆ ಸೂಕ್ತ: ಗಾಳಿ {wind:.0f} ಕಿ.ಮೀ/ಗಂ, ಮಳೆ ಸಾಧ್ಯತೆ {prob:.0f}%. ಬೆಳಿಗ್ಗೆ ಬೇಗ ಸಿಂಪಡಿಸಿ.",
    },
    "spray_today_caution": {
        "en-IN": "Today is marginal: wind up to {wind:.0f} km/h, {prob:.0f}% rain chance. Spray only in calm early-morning hours.",
        "hi-IN": "आज सीमित अनुकूल: हवा {wind:.0f} किमी/घं, वर्षा संभावना {prob:.0f}%। केवल शांत सुबह में छिड़काव करें।",
        "mr-IN": "आज मर्यादित योग्य: वारा {wind:.0f} किमी/तास, पावसाची शक्यता {prob:.0f}%. फक्त शांत सकाळी फवारणी करा.",
        "te-IN": "ఈరోజు పరిమితంగా అనుకూలం: గాలి {wind:.0f} కి.మీ/గం, వర్ష అవకాశం {prob:.0f}%. ప్రశాంతమైన ఉదయం మాత్రమే.",
        "kn-IN": "ಇಂದು ಮಿತ ಸೂಕ್ತ: ಗಾಳಿ {wind:.0f} ಕಿ.ಮೀ/ಗಂ, ಮಳೆ ಸಾಧ್ಯತೆ {prob:.0f}%. ಶಾಂತ ಬೆಳಗಿನ ಹೊತ್ತು ಮಾತ್ರ.",
    },
    "spray_today_avoid": {
        "en-IN": "Avoid spraying today: wind up to {wind:.0f} km/h or {prob:.0f}% rain chance ({rain:.1f} mm) will cause drift or wash-off.",
        "hi-IN": "आज छिड़काव न करें: हवा {wind:.0f} किमी/घं या वर्षा संभावना {prob:.0f}% ({rain:.1f} मिमी) से दवा बह/उड़ सकती है।",
        "mr-IN": "आज फवारणी टाळा: वारा {wind:.0f} किमी/तास किंवा पावसाची शक्यता {prob:.0f}% ({rain:.1f} मिमी) मुळे औषध वाहून जाईल.",
        "te-IN": "ఈరోజు పిచికారీ వద్దు: గాలి {wind:.0f} కి.మీ/గం లేదా వర్ష అవకాశం {prob:.0f}% ({rain:.1f} మి.మీ).",
        "kn-IN": "ಇಂದು ಸಿಂಪಡಣೆ ಬೇಡ: ಗಾಳಿ {wind:.0f} ಕಿ.ಮೀ/ಗಂ ಅಥವಾ ಮಳೆ ಸಾಧ್ಯತೆ {prob:.0f}% ({rain:.1f} ಮಿ.ಮೀ).",
    },
    "spray_best_days": {
        "en-IN": "Best spray days this week: {days}.",
        "hi-IN": "इस सप्ताह छिड़काव के अच्छे दिन: {days}।",
        "mr-IN": "या आठवड्यातील फवारणीचे योग्य दिवस: {days}.",
        "te-IN": "ఈ వారం పిచికారీకి మంచి రోజులు: {days}.",
        "kn-IN": "ಈ ವಾರ ಸಿಂಪಡಣೆಗೆ ಉತ್ತಮ ದಿನಗಳು: {days}.",
    },
    "spray_no_days": {
        "en-IN": "No fully safe spray day in the next 7 days; use the calmest early mornings.",
        "hi-IN": "अगले 7 दिनों में पूर्णतः सुरक्षित दिन नहीं; सबसे शांत सुबह का उपयोग करें।",
        "mr-IN": "पुढील ७ दिवसांत पूर्ण सुरक्षित दिवस नाही; सर्वात शांत सकाळ वापरा.",
        "te-IN": "రాబోయే 7 రోజుల్లో పూర్తిగా సురక్షిత రోజు లేదు; ప్రశాంతమైన ఉదయాలను ఎంచుకోండి.",
        "kn-IN": "ಮುಂದಿನ 7 ದಿನಗಳಲ್ಲಿ ಸಂಪೂರ್ಣ ಸುರಕ್ಷಿತ ದಿನವಿಲ್ಲ; ಶಾಂತ ಬೆಳಗುಗಳನ್ನು ಬಳಸಿ.",
    },
    # Irrigation
    "irr_not_needed": {
        "en-IN": "Expected rain ({rain:.0f} mm) is enough for the crop this week ({demand:.0f} mm). No need to irrigate.",
        "hi-IN": "अनुमानित वर्षा ({rain:.0f} मिमी) इस सप्ताह फसल की जल आवश्यकता ({demand:.0f} मिमी) पूरी करेगी। सिंचाई रोकें।",
        "mr-IN": "अंदाजित पाऊस ({rain:.0f} मिमी) या आठवड्यातील पिकाची पाण्याची गरज ({demand:.0f} मिमी) भागवेल. सिंचन थांबवा.",
        "te-IN": "సూచిత వర్షం ({rain:.0f} మి.మీ) ఈ వారం పంట నీటి అవసరాన్ని ({demand:.0f} మి.మీ) తీరుస్తుంది. నీరు ఆపండి.",
        "kn-IN": "ಮುನ್ಸೂಚಿತ ಮಳೆ ({rain:.0f} ಮಿ.ಮೀ) ಈ ವಾರದ ಬೆಳೆ ನೀರಿನ ಅಗತ್ಯ ({demand:.0f} ಮಿ.ಮೀ) ಪೂರೈಸುತ್ತದೆ. ನೀರು ನಿಲ್ಲಿಸಿ.",
    },
    "irr_monitor": {
        "en-IN": "Rain will be a little short this week ({rain:.0f} mm against {demand:.0f} mm needed). Dig a few inches and check if the soil is moist.",
        "hi-IN": "इस सप्ताह {deficit:.0f} मिमी की हल्की कमी (उपयोग {demand:.0f} मिमी, वर्षा {rain:.0f} मिमी)। जड़ क्षेत्र की नमी जांचें।",
        "mr-IN": "या आठवड्यात {deficit:.0f} मिमी थोडी तूट (गरज {demand:.0f} मिमी, पाऊस {rain:.0f} मिमी). मुळांजवळ ओलावा तपासा.",
        "te-IN": "ఈ వారం {deficit:.0f} మి.మీ స్వల్ప లోటు (అవసరం {demand:.0f}, వర్షం {rain:.0f} మి.మీ). వేర్ల వద్ద తేమ చూడండి.",
        "kn-IN": "ಈ ವಾರ {deficit:.0f} ಮಿ.ಮೀ ಸ್ವಲ್ಪ ಕೊರತೆ (ಅಗತ್ಯ {demand:.0f}, ಮಳೆ {rain:.0f} ಮಿ.ಮೀ). ಬೇರು ಮಟ್ಟದ ತೇವ ಪರೀಕ್ಷಿಸಿ.",
    },
    "irr_needed": {
        "en-IN": "The crop will use about {demand:.0f} mm this week but only {rain:.0f} mm of rain is expected. Give one irrigation.",
        "hi-IN": "इस सप्ताह {deficit:.0f} मिमी जल की कमी (उपयोग {demand:.0f} मिमी, वर्षा {rain:.0f} मिमी)। संरक्षित सिंचाई दें।",
        "mr-IN": "या आठवड्यात {deficit:.0f} मिमी पाण्याची तूट (गरज {demand:.0f} मिमी, पाऊस {rain:.0f} मिमी). संरक्षित पाणी द्या.",
        "te-IN": "ఈ వారం {deficit:.0f} మి.మీ నీటి లోటు (అవసరం {demand:.0f}, వర్షం {rain:.0f} మి.మీ). రక్షణ తడి ఇవ్వండి.",
        "kn-IN": "ಈ ವಾರ {deficit:.0f} ಮಿ.ಮೀ ನೀರಿನ ಕೊರತೆ (ಅಗತ್ಯ {demand:.0f}, ಮಳೆ {rain:.0f} ಮಿ.ಮೀ). ರಕ್ಷಣಾತ್ಮಕ ನೀರು ಕೊಡಿ.",
    },
    "irr_rainfed": {
        "en-IN": "This week the rain will be about {deficit:.0f} mm short of what the crop needs, and there is no irrigation. Mulch and hoe lightly to keep moisture in.",
        "hi-IN": "इस सप्ताह {deficit:.0f} मिमी जल की कमी और सिंचाई साधन नहीं। नमी बचाने के लिए मल्चिंग व हल्की गुड़ाई करें।",
        "mr-IN": "या आठवड्यात {deficit:.0f} मिमी तूट आणि सिंचन नाही. ओलावा टिकवण्यासाठी आच्छादन व हलकी कोळपणी करा.",
        "te-IN": "ఈ వారం {deficit:.0f} మి.మీ లోటు, నీటి వసతి లేదు. తేమ కాపాడేందుకు మల్చింగ్, తేలికపాటి గొర్రు చేయండి.",
        "kn-IN": "ಈ ವಾರ {deficit:.0f} ಮಿ.ಮೀ ಕೊರತೆ, ನೀರಾವರಿ ಇಲ್ಲ. ತೇವ ಉಳಿಸಲು ಮಲ್ಚಿಂಗ್ ಮತ್ತು ಹಗುರ ಎಡೆಕುಂಟೆ ಮಾಡಿ.",
    },
    "irr_satellite_dry": {
        "en-IN": "The latest satellite photo also shows the crop is thirsty.",
        "hi-IN": "नवीनतम उपग्रह फोटो में भी फसल प्यासी दिख रही है।",
        "mr-IN": "नवीनतम उपग्रह फोटोतही पीक तहानलेले दिसत आहे.",
        "te-IN": "తాజా ఉపగ్రహ ఫోటోలో కూడా పంటకు దాహంగా కనిపిస్తోంది.",
        "kn-IN": "ಇತ್ತೀಚಿನ ಉಪಗ್ರಹ ಫೋಟೋದಲ್ಲೂ ಬೆಳೆಗೆ ಬಾಯಾರಿಕೆ ಕಾಣುತ್ತಿದೆ.",
    },
    # Drainage
    "drain_high": {
        "en-IN": "Heavy rain risk: {max_day:.0f} mm on {max_date}, {rain:.0f} mm in 7 days. Open field drains and furrows now.",
        "hi-IN": "भारी वर्षा का जोखिम: {max_date} को {max_day:.0f} मिमी, 7 दिनों में {rain:.0f} मिमी। अभी नालियां खोलें।",
        "mr-IN": "जोरदार पावसाचा धोका: {max_date} रोजी {max_day:.0f} मिमी, ७ दिवसांत {rain:.0f} मिमी. आताच चर व सऱ्या मोकळ्या करा.",
        "te-IN": "భారీ వర్ష ప్రమాదం: {max_date} న {max_day:.0f} మి.మీ, 7 రోజుల్లో {rain:.0f} మి.మీ. కాలువలు తెరవండి.",
        "kn-IN": "ಭಾರೀ ಮಳೆ ಅಪಾಯ: {max_date} ರಂದು {max_day:.0f} ಮಿ.ಮೀ, 7 ದಿನಗಳಲ್ಲಿ {rain:.0f} ಮಿ.ಮೀ. ಕಾಲುವೆ ತೆರೆಯಿರಿ.",
    },
    "drain_moderate": {
        "en-IN": "Moderate rain spells ({rain:.0f} mm in 7 days). Keep furrow ends open so water does not stand.",
        "hi-IN": "मध्यम वर्षा ({rain:.0f} मिमी, 7 दिन)। पानी न रुके इसलिए नालियों के सिरे खुले रखें।",
        "mr-IN": "मध्यम पाऊस (७ दिवसांत {rain:.0f} मिमी). पाणी साचू नये म्हणून सऱ्यांची टोके मोकळी ठेवा.",
        "te-IN": "మితమైన వర్షం (7 రోజుల్లో {rain:.0f} మి.మీ). నీరు నిలవకుండా కాలువ చివరలు తెరిచి ఉంచండి.",
        "kn-IN": "ಮಧ್ಯಮ ಮಳೆ (7 ದಿನಗಳಲ್ಲಿ {rain:.0f} ಮಿ.ಮೀ). ನೀರು ನಿಲ್ಲದಂತೆ ಕಾಲುವೆ ತುದಿ ತೆರೆದಿಡಿ.",
    },
    "drain_low": {
        "en-IN": "Water is unlikely to stand in the field ({rain:.0f} mm expected this week).",
        "hi-IN": "जलभराव का जोखिम कम ({rain:.0f} मिमी, 7 दिन)।",
        "mr-IN": "पाणी साचण्याचा धोका कमी (७ दिवसांत {rain:.0f} मिमी).",
        "te-IN": "నీరు నిలిచే ప్రమాదం తక్కువ (7 రోజుల్లో {rain:.0f} మి.మీ).",
        "kn-IN": "ನೀರು ನಿಲ್ಲುವ ಅಪಾಯ ಕಡಿಮೆ (7 ದಿನಗಳಲ್ಲಿ {rain:.0f} ಮಿ.ಮೀ).",
    },
    # Temperature
    "heat_high": {
        "en-IN": "Heat stress: up to {tmax:.0f}°C on {date}. Irrigate in the evening and avoid spraying at midday.",
        "hi-IN": "गर्मी का तनाव: {date} को {tmax:.0f}°C तक। शाम को सिंचाई करें, दोपहर में छिड़काव न करें।",
        "mr-IN": "उष्णतेचा ताण: {date} रोजी {tmax:.0f}°C पर्यंत. संध्याकाळी पाणी द्या, दुपारी फवारणी टाळा.",
        "te-IN": "వేడి ఒత్తిడి: {date} న {tmax:.0f}°C వరకు. సాయంత్రం నీరు ఇవ్వండి, మధ్యాహ్నం పిచికారీ వద్దు.",
        "kn-IN": "ಬಿಸಿ ಒತ್ತಡ: {date} ರಂದು {tmax:.0f}°C ವರೆಗೆ. ಸಂಜೆ ನೀರು ಕೊಡಿ, ಮಧ್ಯಾಹ್ನ ಸಿಂಪಡಿಸಬೇಡಿ.",
    },
    "heat_moderate": {
        "en-IN": "Warm days up to {tmax:.0f}°C. Watch young seedlings for wilting.",
        "hi-IN": "{tmax:.0f}°C तक गर्म दिन। छोटे पौधों में मुरझाने पर नज़र रखें।",
        "mr-IN": "{tmax:.0f}°C पर्यंत उष्ण दिवस. लहान रोपे कोमेजत नाहीत ना ते पाहा.",
        "te-IN": "{tmax:.0f}°C వరకు వేడి రోజులు. చిన్న మొక్కలు వాడుతున్నాయేమో చూడండి.",
        "kn-IN": "{tmax:.0f}°C ವರೆಗೆ ಬಿಸಿ ದಿನಗಳು. ಎಳೆಯ ಸಸಿಗಳು ಬಾಡುತ್ತಿವೆಯೇ ನೋಡಿ.",
    },
    "cold_low": {
        "en-IN": "Cold night down to {tmin:.0f}°C on {date}. Light irrigation in the evening protects against chilling.",
        "hi-IN": "{date} को रात {tmin:.0f}°C तक ठंडी। शाम की हल्की सिंचाई पाले से बचाती है।",
        "mr-IN": "{date} रोजी रात्री {tmin:.0f}°C पर्यंत थंडी. संध्याकाळी हलके पाणी दिल्यास गारठ्यापासून संरक्षण.",
        "te-IN": "{date} న రాత్రి {tmin:.0f}°C వరకు చలి. సాయంత్రం తేలికపాటి తడి రక్షిస్తుంది.",
        "kn-IN": "{date} ರಂದು ರಾತ್ರಿ {tmin:.0f}°C ವರೆಗೆ ಚಳಿ. ಸಂಜೆ ಹಗುರ ನೀರು ರಕ್ಷಿಸುತ್ತದೆ.",
    },
    "temp_normal": {
        "en-IN": "Normal temperatures this week, {tmin:.0f}–{tmax:.0f}°C.",
        "hi-IN": "तापमान सामान्य: इस सप्ताह {tmin:.0f}–{tmax:.0f}°C।",
        "mr-IN": "तापमान सामान्य: या आठवड्यात {tmin:.0f}–{tmax:.0f}°C.",
        "te-IN": "ఉష్ణోగ్రత సాధారణం: ఈ వారం {tmin:.0f}–{tmax:.0f}°C.",
        "kn-IN": "ತಾಪಮಾನ ಸಾಮಾನ್ಯ: ಈ ವಾರ {tmin:.0f}–{tmax:.0f}°C.",
    },
}


def _text(key: str, locale: str, **values: Any) -> str:
    templates = TEXT[key]
    return templates.get(locale, templates["en-IN"]).format(**values)


def _weekday(day: str, locale: str) -> str:
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        return day
    names = {
        "en-IN": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "hi-IN": ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"],
        "mr-IN": ["सोम", "मंगळ", "बुध", "गुरु", "शुक्र", "शनि", "रवि"],
        "te-IN": ["సోమ", "మంగళ", "బుధ", "గురు", "శుక్ర", "శని", "ఆది"],
        "kn-IN": ["ಸೋಮ", "ಮಂಗಳ", "ಬುಧ", "ಗುರು", "ಶುಕ್ರ", "ಶನಿ", "ಭಾನು"],
    }
    return f"{names.get(locale, names['en-IN'])[parsed.weekday()]} {parsed.day}"


def current_season(today: date | None = None) -> str:
    """Indian cropping season for planning: kharif Jun-Sep, rabi Oct-Feb, summer (zaid) Mar-May."""
    month = (today or date.today()).month
    if 6 <= month <= 9:
        return "kharif"
    if month >= 10 or month <= 2:
        return "rabi"
    return "summer"


def operational_forecast_indicators(
    evidence: list[dict[str, Any]],
    *,
    soil_type: str = "unknown",
    water_access: str = "rainfed",
    season: str | None = None,
    locale: str = "en-IN",
) -> dict[str, Any]:
    """Seven-day forecast -> sowing, spraying, irrigation, drainage and temperature advice."""
    t = THRESHOLDS
    locale = locale if locale in SUPPORTED_LOCALES else "en-IN"
    season = season or current_season()
    snapshot = latest_weather_snapshot(evidence)
    past, future = daily_series(snapshot)
    week = future[:7]

    water_stress = "unknown"
    for snap in evidence:
        if snap.get("kind") in ("satellite_observation", "satellite_indices"):
            for item in snap.get("values", []):
                if item.get("name") == "water_stress" and isinstance(item.get("value"), str):
                    water_stress = item["value"].lower()

    base: dict[str, Any] = {
        "season": season,
        "source": snapshot.get("provider") if snapshot else None,
        "fetched_at": snapshot.get("fetched_at") if snapshot else None,
        "thresholds": t,
    }
    if not week:
        message = _text("no_data", locale)
        unknown = {"status": "unknown", "summary": message, "details": ""}
        return base | {
            "has_forecast": False, "daily": [], "rain_7d_total_mm": None, "et0_7d_total_mm": None,
            "water_balance_7d_mm": None, "dry_days_count": 0, "rain_days_count": 0,
            "sowing": unknown, "spraying": unknown | {"best_days": []}, "irrigation": unknown,
            "drainage": unknown, "temperature": unknown, "disease": unknown,
            "soil_moisture": {"top_available_pct": None, "root_available_pct": None, "source": None},
        }

    hours = hourly_series(snapshot)
    now_hour = hours[0] if hours else {}
    top_fraction = available_water(_num(now_hour.get("soil_moisture_top")), soil_type)
    root_fraction = available_water(_num(now_hour.get("soil_moisture_root")), soil_type)

    daily = []
    for day in week:
        entry = {
            "date": day["date"],
            "label": _weekday(day["date"], locale),
            **{field: _num(day.get(field)) for field in _DAILY_PREFIXES.values()},
        }
        entry["spray"] = spray_status(day)
        daily.append(entry)

    rain_7d = _sum(week, "rain_mm")
    rain_3d = _sum(week[:3], "rain_mm")
    past_rain = _sum(past[-7:], "rain_mm")
    et0_values = [_num(day.get("et0")) for day in week if _num(day.get("et0")) is not None]
    et0_7d = sum(et0_values) if et0_values else None
    demand = et0_7d * t["crop_coefficient"] if et0_7d is not None else None
    balance = rain_7d - demand if demand is not None else None
    dry_days = sum(1 for day in week if (_num(day.get("rain_mm")) or 0.0) < 2.0)
    temps_max = [(d["date"], _num(d.get("temp_max"))) for d in week if _num(d.get("temp_max")) is not None]
    temps_min = [(d["date"], _num(d.get("temp_min"))) for d in week if _num(d.get("temp_min")) is not None]
    mean_tmax = sum(v for _, v in temps_max) / len(temps_max) if temps_max else None

    # Sowing readiness depends on the season being planned.
    if rain_3d >= t["sowing_heavy_rain_3d_mm"] and season != "kharif":
        sowing = {"status": "wait", "summary": _text("sow_heavy_rain", locale, rain3=rain_3d)}
    elif season == "kharif":
        moisture = past_rain + rain_3d
        if moisture >= t["kharif_sowing_ready_mm"]:
            sowing = {"status": "ready", "summary": _text("sow_kharif_ready", locale, moisture=moisture)}
        elif top_fraction is not None and top_fraction >= t["soil_wet_fraction"] and moisture >= t["kharif_sowing_marginal_mm"]:
            sowing = {"status": "ready", "summary": _text("sow_soil_moist", locale, top=top_fraction * 100)}
        elif moisture >= t["kharif_sowing_marginal_mm"]:
            sowing = {"status": "marginal", "summary": _text("sow_kharif_marginal", locale, moisture=moisture, needed=t["kharif_sowing_ready_mm"] - moisture)}
        else:
            sowing = {"status": "wait", "summary": _text("sow_kharif_wait", locale, moisture=moisture)}
    elif season == "rabi":
        if mean_tmax is not None and mean_tmax > t["rabi_sowing_max_temp"]:
            sowing = {"status": "marginal", "summary": _text("sow_rabi_warm", locale, tmax=mean_tmax)}
        elif mean_tmax is not None:
            sowing = {"status": "ready", "summary": _text("sow_rabi_ready", locale, tmax=mean_tmax)}
        else:
            sowing = {"status": "ready", "summary": _text("sow_rabi_dry", locale, rain3=rain_3d)}
    else:
        if water_access == "rainfed":
            sowing = {"status": "wait", "summary": _text("sow_summer_rainfed", locale)}
        else:
            sowing = {"status": "ready", "summary": _text("sow_summer_ready", locale)}
    sowing["details"] = (
        _text("soil_moisture_note", locale, top=round(top_fraction * 100), root=round(root_fraction * 100))
        if top_fraction is not None and root_fraction is not None else ""
    )

    # Spraying: today's status plus the best days of the week.
    today = daily[0]
    spray_key = {"safe": "spray_today_safe", "caution": "spray_today_caution", "avoid": "spray_today_avoid"}.get(today["spray"], "no_data")
    safe_days = [d["label"] for d in daily if d["spray"] == "safe"][:3]
    windows = spray_windows(hours)
    for window in windows:
        window["label"] = f"{_weekday(window['date'], locale)} {window['start']}–{window['end']}"
    if windows:
        spray_details = _text("spray_hours", locale, windows=", ".join(w["label"] for w in windows))
    elif safe_days:
        spray_details = _text("spray_best_days", locale, days=", ".join(safe_days))
    else:
        spray_details = _text("spray_no_days", locale)
    spraying = {
        "status": today["spray"],
        "summary": _text(spray_key, locale, wind=today["wind_max"] or 0.0, prob=today["rain_prob"] or 0.0, rain=today["rain_mm"] or 0.0),
        "details": spray_details,
        "best_days": [d["date"] for d in daily if d["spray"] == "safe"][:3],
        "windows": windows,
    }

    # Irrigation: forecast rain against crop water use (ET0 x Kc).
    if balance is None:
        irrigation = {"status": "unknown", "summary": _text("no_data", locale), "details": ""}
    else:
        deficit = -balance
        values = {"rain": rain_7d, "demand": demand, "deficit": max(deficit, 0.0)}
        if root_fraction is not None and root_fraction >= t["soil_wet_fraction"]:
            irrigation = {"status": "not_needed", "summary": _text("irr_soil_ok", locale, root=root_fraction * 100)}
        elif deficit <= 0:
            irrigation = {"status": "not_needed", "summary": _text("irr_not_needed", locale, **values)}
        elif deficit < t["irrigation_monitor_deficit_mm"]:
            irrigation = {"status": "not_needed", "summary": _text("irr_monitor", locale, **values)}
        elif deficit < t["irrigation_deficit_mm"] and water_stress not in {"high", "very_dry"} and not (root_fraction is not None and root_fraction < t["soil_dry_fraction"]):
            irrigation = {"status": "monitor", "summary": _text("irr_monitor", locale, **values)}
        elif water_access == "rainfed":
            irrigation = {"status": "conserve", "summary": _text("irr_rainfed", locale, **values)}
        else:
            irrigation = {"status": "irrigate", "summary": _text("irr_needed", locale, **values)}
        irrigation["details"] = _text("irr_satellite_dry", locale) if water_stress in {"high", "very_dry"} else ""

    # Drainage / waterlogging, using IMD heavy-rain categories.
    max_day = max(week, key=lambda d: _num(d.get("rain_mm")) or 0.0)
    max_rain = _num(max_day.get("rain_mm")) or 0.0
    heavy_soil = soil_type in {"black", "clay"}
    if max_rain >= t["heavy_rain_day_mm"] or (rain_7d >= t["drainage_high_7d_mm"] and heavy_soil):
        drainage = {"status": "high", "summary": _text("drain_high", locale, max_day=max_rain, max_date=_weekday(max_day["date"], locale), rain=rain_7d)}
    elif max_rain >= t["moderate_rain_day_mm"] or rain_7d >= t["drainage_moderate_7d_mm"]:
        drainage = {"status": "moderate", "summary": _text("drain_moderate", locale, rain=rain_7d)}
    else:
        drainage = {"status": "low", "summary": _text("drain_low", locale, rain=rain_7d)}
    drainage["details"] = ""

    # Heat and cold stress.
    hottest = max(temps_max, key=lambda item: item[1]) if temps_max else None
    coldest = min(temps_min, key=lambda item: item[1]) if temps_min else None
    if hottest and hottest[1] >= t["heat_high_c"]:
        temperature = {"status": "high", "summary": _text("heat_high", locale, tmax=hottest[1], date=_weekday(hottest[0], locale))}
    elif coldest and coldest[1] <= t["cold_low_c"]:
        temperature = {"status": "cold", "summary": _text("cold_low", locale, tmin=coldest[1], date=_weekday(coldest[0], locale))}
    elif hottest and hottest[1] >= t["heat_moderate_c"]:
        temperature = {"status": "moderate", "summary": _text("heat_moderate", locale, tmax=hottest[1])}
    elif hottest and coldest:
        temperature = {"status": "normal", "summary": _text("temp_normal", locale, tmin=coldest[1], tmax=hottest[1])}
    else:
        temperature = {"status": "unknown", "summary": _text("no_data", locale)}
    temperature["details"] = ""

    # Fungal disease weather risk from the hourly humidity of the next 3 days.
    wet_hours = disease_hours_by_day(hours)
    if wet_hours:
        worst_day, worst = max(wet_hours.items(), key=lambda item: item[1])
        if worst >= t["disease_high_hours"]:
            disease = {"status": "high", "summary": _text("disease_high", locale, hours=worst, date=_weekday(worst_day, locale))}
        elif worst >= t["disease_moderate_hours"]:
            disease = {"status": "moderate", "summary": _text("disease_moderate", locale, hours=worst)}
        else:
            disease = {"status": "low", "summary": _text("disease_low", locale)}
        disease["details"] = ""
        disease["humid_hours_by_day"] = wet_hours
    else:
        disease = {"status": "unknown", "summary": _text("no_data", locale), "details": ""}

    return base | {
        "has_forecast": True,
        "daily": daily,
        "rain_7d_total_mm": round(rain_7d, 1),
        "past_7d_rain_mm": round(past_rain, 1) if past else None,
        "et0_7d_total_mm": round(et0_7d, 1) if et0_7d is not None else None,
        "water_balance_7d_mm": round(balance, 1) if balance is not None else None,
        "dry_days_count": dry_days,
        "rain_days_count": len(week) - dry_days,
        "satellite_water_stress": water_stress,
        "sowing": sowing,
        "spraying": spraying,
        "irrigation": irrigation,
        "drainage": drainage,
        "temperature": temperature,
        "disease": disease,
        "soil_moisture": {
            "top_available_pct": round(top_fraction * 100) if top_fraction is not None else None,
            "root_available_pct": round(root_fraction * 100) if root_fraction is not None else None,
            "source": "Open-Meteo land-surface model (estimate)",
        },
    }
