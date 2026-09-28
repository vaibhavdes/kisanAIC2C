"""Field-operation windows and weather-based pest/disease risk from the latest forecast.

Everything here is derived from the most recent Open-Meteo snapshot (model forecast) plus the
farm's soil texture and, when available, the latest satellite moisture signal. Outputs carry a
status code and numeric params so the UI can render them in the farmer's language.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .knowledge import normalize_crop

FIELD_CAPACITY = {"heavy": 0.42, "medium": 0.32, "light": 0.20}  # volumetric m3/m3, 3-9 cm layer
SPRAY_MAX_WIND_KMH = 15.0
SPRAY_MAX_RAIN_PROB = 40
HEAVY_RAIN_MM = 64.5  # IMD "heavy rainfall" threshold for 24 h


def latest_snapshot(evidence: list[dict[str, Any]], kind: str, provider: str | None = None) -> dict[str, Any] | None:
    candidates = [
        item for item in evidence
        if item.get("kind") == kind and (provider is None or item.get("provider") == provider) and item.get("mode") != "missing"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: str(item.get("fetched_at") or ""))


def satellite_values(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    snap = latest_snapshot(evidence, "satellite_observation")
    if not snap:
        return {}
    values = {item["name"]: item.get("value") for item in snap.get("values", [])}
    values["observed_at"] = snap.get("observed_at")
    return values


def imd_warnings(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    status = "unavailable"
    level = None
    for snap in evidence:
        if snap.get("provider") != "imd":
            continue
        if snap.get("mode") == "missing":
            continue
        status = "available"
        for item in snap.get("values", []):
            if "color_code" in str(item.get("name")) or "warning_code" in str(item.get("name")):
                try:
                    code = int(item.get("value"))
                except (TypeError, ValueError):
                    continue
                if code in (1, 2, 3):
                    level = min(level or 9, code)
    return {"status": status, "level": {1: "red", 2: "orange", 3: "yellow"}.get(level) if level else None}


def _hour_ok_for_spray(hour: dict[str, Any]) -> bool:
    wind, prob, rain = hour.get("wind_speed_10m"), hour.get("precipitation_probability"), hour.get("precipitation")
    if wind is None or prob is None or rain is None:
        return False  # a missing forecast value is unknown, never assumed dry and calm
    return wind < SPRAY_MAX_WIND_KMH and prob < SPRAY_MAX_RAIN_PROB and rain < 0.2


def _spray_window(hourly: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    upcoming = [h for h in hourly if datetime.fromisoformat(h["time"]) >= now.replace(minute=0, second=0, microsecond=0)]
    for idx, hour in enumerate(upcoming[:72]):
        moment = datetime.fromisoformat(hour["time"])
        if not 6 <= moment.hour <= 17:
            continue
        block = []
        for follow in upcoming[idx: idx + 4]:
            follow_time = datetime.fromisoformat(follow["time"])
            if not 6 <= follow_time.hour <= 18 or not _hour_ok_for_spray(follow):
                break
            block.append(follow)
        after = upcoming[idx + len(block): idx + len(block) + 6]
        dry_after = len(after) == 6 and all(h.get("precipitation") is not None and h["precipitation"] < 0.5
                                            and h.get("precipitation_probability") is not None and h["precipitation_probability"] < 50 for h in after)
        if len(block) >= 2 and dry_after:
            return {
                "start": block[0]["time"],
                "end": block[-1]["time"],
                "max_wind_kmh": round(max(h["wind_speed_10m"] for h in block), 1),
                "hours_from_now": round((moment - now).total_seconds() / 3600, 1),
            }
    return None


def _daily_groups(hourly: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for hour in hourly:
        groups.setdefault(hour["time"][:10], []).append(hour)
    return groups


def disease_risks(hourly: list[dict[str, Any]], crop_id: str | None) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    wet_hours = sum(1 for h in hourly if (h.get("relative_humidity_2m") or 0) >= 90 and 15 <= (h.get("temperature_2m") or -99) <= 30)
    fungal = "high" if wet_hours >= 40 else "moderate" if wet_hours >= 15 else "low"
    risks.append({"id": "fungal_leaf", "status": fungal, "params": {"leaf_wet_hours": wet_hours},
                  "message": f"{wet_hours} humid leaf-wetness hours (RH>=90%, 15-30 C) in the next 7 days."})

    days = _daily_groups(hourly)
    if crop_id in {"potato", "tomato"}:
        consecutive, smith = 0, False
        for hours in days.values():
            min_temp = min((h.get("temperature_2m") or 99) for h in hours)
            humid = sum(1 for h in hours if (h.get("relative_humidity_2m") or 0) >= 90)
            consecutive = consecutive + 1 if min_temp >= 10 and humid >= 11 else 0
            smith = smith or consecutive >= 2
        risks.append({"id": "late_blight", "status": "high" if smith else "low", "params": {"smith_period": smith},
                      "message": "Smith Period conditions (2 days, min temp >= 10 C and >= 11 h RH >= 90%) " + ("forecast." if smith else "not forecast.")})
    if crop_id == "rice":
        blast_days = 0
        for hours in days.values():
            night = [h for h in hours if int(h["time"][11:13]) < 6 or int(h["time"][11:13]) >= 20]
            if night and all(18 <= (h.get("temperature_2m") or 0) <= 27 for h in night) and sum(1 for h in hours if (h.get("relative_humidity_2m") or 0) >= 90) >= 8:
                blast_days += 1
        risks.append({"id": "rice_blast", "status": "high" if blast_days >= 3 else "moderate" if blast_days >= 1 else "low",
                      "params": {"favourable_days": blast_days}, "message": f"{blast_days} days with warm humid nights favourable for blast."})
    if crop_id in {"cotton", "chickpea", "green_gram", "black_gram", "tomato", "onion"}:
        hot_dry = sum(1 for hours in days.values()
                      if max((h.get("temperature_2m") or 0) for h in hours) >= 32 and sum((h.get("relative_humidity_2m") or 0) for h in hours) / len(hours) < 60)
        risks.append({"id": "sucking_pests", "status": "moderate" if hot_dry >= 3 else "low", "params": {"hot_dry_days": hot_dry},
                      "message": f"{hot_dry} hot, dry days that favour sucking pests (whitefly, thrips, jassids)."})
    return risks


def operational_indicators(
    evidence: list[dict[str, Any]],
    *,
    texture: str | None,
    water_access: str,
    crop_status: str,
    current_crop: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    snap = latest_snapshot(evidence, "weather_forecast", "open_meteo")
    if not snap or not snap.get("data"):
        return {"available": False, "message": "No forecast has been fetched yet for this farm."}

    data = snap["data"]
    daily = data.get("daily") or []
    hourly = data.get("hourly") or []
    current_time = data.get("current", {}).get("time")
    now = now or (datetime.fromisoformat(current_time) if current_time else datetime.fromisoformat(hourly[0]["time"]))
    crop_id = normalize_crop(current_crop) if current_crop else None
    texture = texture or "medium"

    rain = [d.get("precipitation_sum") or 0.0 for d in daily]
    et0 = [d.get("et0_fao_evapotranspiration") or 0.0 for d in daily]
    rain_7d = round(sum(rain[:7]), 1)
    et0_7d = round(sum(et0[:7]), 1)
    max_3day = round(max((sum(rain[i:i + 3]) for i in range(max(1, len(rain) - 2))), default=0.0), 1)
    sat = satellite_values(evidence)

    # Sowing readiness (seed-zone moisture now + rain expected soon)
    now_hour = next((h for h in hourly if datetime.fromisoformat(h["time"]) >= now.replace(minute=0, second=0, microsecond=0)), hourly[0] if hourly else {})
    soil_moisture = now_hour.get("soil_moisture_3_to_9cm")
    fc = FIELD_CAPACITY.get(texture, 0.32)
    moisture_ratio = round(soil_moisture / fc, 2) if soil_moisture is not None else None
    rain_next_3 = round(sum(rain[:3]), 1)
    likely_rain_3 = max((d.get("precipitation_probability_max") or 0) for d in daily[:3]) if daily else 0
    if crop_status == "planted":
        sowing = {"status": "not_applicable", "params": {}, "message": "Crop already planted."}
    elif moisture_ratio is not None and moisture_ratio >= 0.6 and rain_next_3 < 40:
        sowing = {"status": "ready", "params": {"moisture_ratio": moisture_ratio, "rain_next_3d_mm": rain_next_3},
                  "message": f"Seed-zone moisture is {int(moisture_ratio * 100)}% of field capacity and no heavy rain is due: good for sowing."}
    elif rain_next_3 >= 20 and likely_rain_3 >= 60:
        sowing = {"status": "wait_for_rain", "params": {"moisture_ratio": moisture_ratio, "rain_next_3d_mm": rain_next_3, "probability": likely_rain_3},
                  "message": f"{rain_next_3} mm of rain is likely in 3 days ({likely_rain_3}% chance): sow after it soaks the seed zone."}
    elif water_access != "rainfed":
        sowing = {"status": "irrigate_first", "params": {"moisture_ratio": moisture_ratio},
                  "message": "Seed zone is dry: give a pre-sowing irrigation before sowing."}
    else:
        sowing = {"status": "wait", "params": {"moisture_ratio": moisture_ratio, "rain_next_3d_mm": rain_next_3},
                  "message": "Seed zone is too dry and no soaking rain is expected: avoid dry sowing."}

    # Spray window
    window = _spray_window(hourly, now)
    if window and window["hours_from_now"] <= 24:
        spray = {"status": "good", "window": window, "params": window,
                 "message": f"Calm, dry spell from {window['start'][11:16]} ({window['start'][:10]}): wind below {SPRAY_MAX_WIND_KMH:g} km/h and no rain for 6 h after."}
    elif window:
        spray = {"status": "caution", "window": window, "params": window,
                 "message": f"No safe spell in the next 24 h; next calm, dry window starts {window['start'][:10]} {window['start'][11:16]}."}
    else:
        spray = {"status": "avoid", "window": None, "params": {},
                 "message": "No calm, rain-free daylight window in the next 3 days; postpone spraying."}

    # Irrigation water balance (FAO-56 reference ET, crop factor ~1 for an active canopy)
    balance = round(rain_7d * 0.8 - et0_7d, 1)
    stress = str(sat.get("water_stress") or "").lower()
    if rain_7d >= 20 and balance >= 0:
        irrigation = {"status": "not_needed", "params": {"balance_mm": balance, "rain_7d_mm": rain_7d, "et0_7d_mm": et0_7d},
                      "message": f"Expected rain ({rain_7d} mm) covers crop water use ({et0_7d} mm): hold irrigation."}
    elif balance < -25 or stress == "high":
        irrigation = {"status": "irrigate" if water_access != "rainfed" else "deficit",
                      "params": {"balance_mm": balance, "rain_7d_mm": rain_7d, "et0_7d_mm": et0_7d, "satellite_stress": stress or None},
                      "message": f"7-day water deficit of {abs(balance)} mm" + (" and satellite shows canopy water stress" if stress == "high" else "") + "."}
    else:
        irrigation = {"status": "monitor", "params": {"balance_mm": balance, "rain_7d_mm": rain_7d, "et0_7d_mm": et0_7d},
                      "message": f"Small water deficit ({balance} mm over 7 days): check soil moisture before irrigating."}

    # Drainage / waterlogging
    if max_3day >= HEAVY_RAIN_MM:
        drainage = {"status": "high" if texture == "heavy" else "watch", "params": {"max_3day_mm": max_3day},
                    "message": f"Up to {max_3day} mm of rain over 3 days: open field drains" + (" (heavy soil drains slowly)." if texture == "heavy" else ".")}
    elif max_3day >= 35:
        drainage = {"status": "watch", "params": {"max_3day_mm": max_3day}, "message": f"Moderate rain ({max_3day} mm over 3 days): keep furrows clear."}
    else:
        drainage = {"status": "normal", "params": {"max_3day_mm": max_3day}, "message": "No waterlogging risk from the forecast."}

    heat_days = sum(1 for d in daily if (d.get("temperature_2m_max") or 0) >= 40)
    cold_days = sum(1 for d in daily if (d.get("temperature_2m_min") or 99) <= 4)

    return {
        "available": True,
        "source": "open_meteo",
        "forecast_issued_at": snap.get("fetched_at"),
        "timezone": data.get("timezone"),
        "rain_7d_mm": rain_7d,
        "et0_7d_mm": et0_7d,
        "rain_days": sum(1 for value in rain if value >= 2.5),
        "sowing": sowing,
        "spray": spray,
        "irrigation": irrigation,
        "drainage": drainage,
        "temperature_extremes": {"heat_days": heat_days, "cold_days": cold_days},
        "disease_risks": disease_risks(hourly[:168], crop_id),
        "imd": imd_warnings(evidence),
        "daily": [
            {"date": d["date"], "rain_mm": d.get("precipitation_sum"), "rain_probability": d.get("precipitation_probability_max"),
             "tmax": d.get("temperature_2m_max"), "tmin": d.get("temperature_2m_min"), "wind_max_kmh": d.get("wind_speed_10m_max"),
             "humidity_mean": d.get("relative_humidity_2m_mean"), "et0_mm": d.get("et0_fao_evapotranspiration")}
            for d in daily
        ],
        "current": data.get("current"),
    }
