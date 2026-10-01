"""Soil-test-based fertilizer plan for one crop on one farm.

Method (the standard soil-test-rating approach used with Soil Health Cards):
1. Start from the crop's general recommended dose of N, P2O5 and K2O (kg/ha).
2. Rate each nutrient low / medium / high with data/agri_baselines/soil_npk_standards.json
   and adjust the dose by +25 % / 0 / -25 %.
3. Convert the nutrient dose into DAP, urea and MOP for the farm's area.

Soil values come from the farmer's confirmed soil test when present, otherwise from the
district baseline, and every value carries its source so the screen can say which one it is.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any

from .data.maharashtra_agri_context import get_district_profile
from .domain import normalize_crop
from .models import Farm, SoilTest
from .settings import PROJECT_ROOT

# General recommended dose (kg/ha N, P2O5, K2O) per crop, checked against published
# recommendations (October 2026). Keys: "default", a season, "irrigated" or "<season>_irrigated".
RECOMMENDED_DOSE: dict[str, dict[str, tuple[float, float, float]]] = {
    "soybean": {"default": (30, 60, 30)},
    "cotton": {"default": (80, 40, 40), "irrigated": (100, 50, 50)},
    "pigeon_pea": {"default": (25, 50, 0)},
    "sorghum": {"default": (80, 40, 40), "rabi": (50, 25, 0), "rabi_irrigated": (80, 40, 40)},
    "chickpea": {"default": (25, 50, 25)},
    "wheat": {"default": (120, 60, 40)},
    "groundnut": {"default": (25, 50, 0)},
    "maize": {"default": (120, 60, 40)},
    "pearl_millet": {"default": (50, 25, 0)},
    "onion": {"default": (100, 50, 50)},
    "sugarcane": {"default": (250, 115, 115)},
    "rice": {"default": (100, 50, 50)},
}

# Where each dose comes from, shown with the plan.
DOSE_SOURCES: dict[str, str] = {
    "soybean": "Dr. PDKV Akola recommendation for Vertisols of Vidarbha (30:60:30)",
    "cotton": "Approved package of practices for cotton, Maharashtra: rainfed hybrids 80:40:40, irrigated 100:50:50",
    "pigeon_pea": "Package of practices for pigeon pea (25:50 N:P2O5)",
    "sorghum": "ICAR agro-advisory for Maharashtra (80:40:40); MPKV Rahuri for rainfed rabi sorghum (50:25)",
    "chickpea": "ICAR rabi agro-advisory for Maharashtra (25:50:25)",
    "wheat": "MPKV Rahuri, timely sown irrigated wheat (120:60:40 with 5 t/ha FYM)",
    "groundnut": "Dr. BSKKV Dapoli, kharif groundnut (25:50:0)",
    "maize": "MPKV Rahuri and ICAR-IIMR, medium and late maize (120:60:40)",
    "pearl_millet": "ICAR-IIMR package of practices for pearl millet (50:25)",
    "onion": "ICAR-Directorate of Onion and Garlic Research (100:50:50, plus 50 kg sulphur)",
    "sugarcane": "MPKV Rahuri, suru sugarcane (250:115:115)",
    "rice": "Dr. BSKKV Dapoli, kharif rice in Konkan (100:50:50)",
}
DOSE_NOTE = "Confirm with your local KVK or agriculture officer."

# Legumes fix their own nitrogen; all fertilizer goes in at sowing.
LEGUMES = {"soybean", "pigeon_pea", "chickpea", "groundnut"}

# Fertilizer products: nutrient fractions and bag size (kg).
DAP = {"n": 0.18, "p": 0.46, "bag": 50}
UREA = {"n": 0.46, "bag": 45}
MOP = {"k": 0.60, "bag": 50}

ADJUSTMENT = {"low": 1.25, "medium": 1.0, "high": 0.75}


@lru_cache
def _standards() -> dict[str, Any]:
    path = PROJECT_ROOT / "data" / "agri_baselines" / "soil_npk_standards.json"
    return json.loads(path.read_text(encoding="utf-8"))["nutrients"]


def rate(nutrient: str, value: float | None) -> str | None:
    if value is None:
        return None
    thresholds = _standards()[nutrient]["thresholds"]
    if value < thresholds["low"]["max"]:
        return "low"
    if value < thresholds["medium"]["max"]:
        return "medium"
    return "high"


def _soil_values(soil: SoilTest | None, farm: Farm) -> dict[str, dict[str, Any]]:
    """{nutrient: {value, source}} using the soil test first, then the district baseline."""
    measured = soil.values.model_dump() if soil else {}
    profile = get_district_profile(farm.district)
    baseline = (profile.soil_profile or {}) if profile else {}
    baseline_keys = {
        "nitrogen_kg_ha": "available_nitrogen_kg_ha",
        "phosphorus_kg_ha": "available_phosphorus_kg_ha",
        "potassium_kg_ha": "available_potassium_kg_ha",
        "organic_carbon_percent": "organic_carbon_percent",
        "ph": "ph_typical",
    }
    result: dict[str, dict[str, Any]] = {}
    for key, base_key in baseline_keys.items():
        if measured.get(key) is not None:
            result[key] = {"value": measured[key], "source": "soil_test"}
        elif isinstance(baseline.get(base_key), (int, float)):
            result[key] = {"value": float(baseline[base_key]), "source": "district_baseline"}
        else:
            result[key] = {"value": None, "source": "unknown"}
        if key != "ph":
            result[key]["rating"] = rate(key, result[key]["value"])
    return result


def recommended_dose(crop: str, season: str | None, water_access: str) -> tuple[float, float, float] | None:
    doses = RECOMMENDED_DOSE.get(crop)
    if not doses:
        return None
    irrigated = water_access == "irrigated"
    for key in (f"{season}_irrigated" if irrigated else None, "irrigated" if irrigated else None, season):
        if key and key in doses:
            return doses[key]
    return doses["default"]


def _bags(kg: float, bag: int) -> float:
    # Rounded up to half bags, which is how farmers buy and split fertilizer.
    return math.ceil(kg / bag * 2) / 2 if kg > 0 else 0.0


def fertilizer_plan(farm: Farm, soil: SoilTest | None, crop: str, season: str | None) -> dict[str, Any]:
    crop = normalize_crop(crop)
    soil_values = _soil_values(soil, farm)
    dose = recommended_dose(crop, season, farm.water_access)
    if dose is None:
        raise ValueError(f"No recommended fertilizer dose is configured for {crop}")

    adjusted = []
    for base, key in zip(dose, ("nitrogen_kg_ha", "phosphorus_kg_ha", "potassium_kg_ha")):
        rating = soil_values[key]["rating"]
        adjusted.append(round(base * ADJUSTMENT.get(rating or "medium", 1.0), 1))
    n_ha, p_ha, k_ha = adjusted

    area = farm.area_ha
    n, p, k = n_ha * area, p_ha * area, k_ha * area
    dap_kg = p / DAP["p"] if p > 0 else 0.0
    urea_kg = max(0.0, (n - dap_kg * DAP["n"]) / UREA["n"])
    mop_kg = k / MOP["k"] if k > 0 else 0.0

    legume = crop in LEGUMES
    basal_urea = urea_kg if legume else urea_kg / 2
    applications = [
        {"stage": "basal", "dap_kg": round(dap_kg, 1), "urea_kg": round(basal_urea, 1), "mop_kg": round(mop_kg, 1)},
    ]
    if not legume and urea_kg > 0:
        applications.append({"stage": "top_dress_30_45_das", "dap_kg": 0.0, "urea_kg": round(urea_kg - basal_urea, 1), "mop_kg": 0.0})

    oc = soil_values["organic_carbon_percent"]
    organic_advice = None
    if oc["rating"] == "low":
        organic_advice = _standards()["organic_carbon_percent"]["thresholds"]["low"]["remedy"]

    return {
        "crop": crop,
        "season": season,
        "area_ha": round(area, 3),
        "soil": soil_values,
        "soil_source": "soil_test" if soil else "district_baseline",
        "recommended_dose_kg_ha": {"n": dose[0], "p2o5": dose[1], "k2o": dose[2]},
        "adjusted_dose_kg_ha": {"n": n_ha, "p2o5": p_ha, "k2o": k_ha},
        "products_total": {
            "dap_kg": round(dap_kg, 1), "dap_bags": _bags(dap_kg, DAP["bag"]),
            "urea_kg": round(urea_kg, 1), "urea_bags": _bags(urea_kg, UREA["bag"]),
            "mop_kg": round(mop_kg, 1), "mop_bags": _bags(mop_kg, MOP["bag"]),
        },
        "applications": applications,
        "organic_advice": organic_advice,
        "legume": legume,
        "rhizobium_advice": legume,
        "source": f"{DOSE_SOURCES[crop]}. {DOSE_NOTE}",
        "rating_source": "Soil test rating thresholds (ICAR): low / medium / high adjust dose by +25 % / 0 / -25 %",
    }
