"""Soil test interpretation from the official schemes in data/soil/interpretation.json.

A farm uses its region's scheme (ISO 3166-2, e.g. BR-PR), then its country's (e.g. IN, the
Soil Health Card limits). pH and EC classes apply everywhere. Nothing is rated without a scheme.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .models import SoilEstimate, SoilRating, SoilTest, SoilValues
from .settings import PROJECT_ROOT


@lru_cache
def _interpretation() -> dict[str, Any]:
    return json.loads((PROJECT_ROOT / "data" / "soil" / "interpretation.json").read_text(encoding="utf-8"))


def soil_scheme(country_code: str | None, subdivision: str | None = None) -> dict[str, Any] | None:
    schemes = _interpretation()["schemes"]
    return schemes.get(subdivision or "") or schemes.get(country_code or "")


def scheme_parameters(country_code: str | None, subdivision: str | None = None) -> list[dict[str, Any]]:
    """Fields a farmer can enter for this region: universal pH/EC plus the scheme's parameters."""
    scheme = soil_scheme(country_code, subdivision)
    return [{key: p[key] for key in ("id", "unit", "step", "method") if key in p}
            for p in _interpretation()["universal"] + (scheme["parameters"] if scheme else [])]


def _classify(value: float, classes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in classes:
        if "below" in item and value < item["below"]:
            return item
        if "upto" in item and value <= item["upto"]:
            return item
        if "below" not in item and "upto" not in item:
            return item
    return None


def ph_rating(ph: float) -> str:
    return _classify(ph, _interpretation()["universal"][0]["classes"])["rating"]


def rate_values(values: SoilValues, country_code: str = "IN", subdivision: str | None = None) -> list[SoilRating]:
    scheme = soil_scheme(country_code, subdivision)
    parameters = list(_interpretation()["universal"])
    if scheme:
        condition = scheme.get("applies_if")
        measured = getattr(values, condition["parameter"], None) if condition else None
        if not condition or measured is None or measured >= condition["min"]:
            parameters += scheme["parameters"]
    ratings: list[SoilRating] = []
    for param in parameters:
        value = getattr(values, param["id"], None)
        if value is None or not param.get("classes"):
            continue
        match = _classify(value, param["classes"])
        if match:
            ratings.append(SoilRating(parameter=param["id"], value=value, unit=param["unit"], rating=match["rating"],
                                      note=match.get("note"), doses=match.get("doses"),
                                      scheme=scheme["name"] if scheme and param in scheme["parameters"] else None))
    return ratings


def rating_for(ratings: list[SoilRating], parameter: str) -> str | None:
    return next((item.rating for item in ratings if item.parameter == parameter), None)


FARM_SOIL_TEXTURE = {"black": "heavy", "clay": "heavy", "alluvial": "medium", "loam": "medium", "red": "medium", "sandy": "light"}


def effective_soil(farm_soil_type: str, test: SoilTest | None, estimate: SoilEstimate | None, country_code: str = "IN",
                   subdivision: str | None = None) -> dict:
    """Merge measured, farmer-declared and modelled soil information with provenance."""
    texture = FARM_SOIL_TEXTURE.get(farm_soil_type)
    texture_source = "farmer" if texture else None
    if texture is None and estimate and estimate.texture_class:
        texture, texture_source = estimate.texture_class, "estimated"

    ph, ph_source = None, None
    if test and test.values.ph is not None:
        ph, ph_source = test.values.ph, "measured"
    elif estimate and estimate.ph is not None:
        ph, ph_source = estimate.ph, "estimated"

    oc, oc_source = None, None
    if test and test.values.organic_carbon_percent is not None:
        oc, oc_source = test.values.organic_carbon_percent, "measured"
    elif estimate and estimate.organic_carbon_percent is not None:
        oc, oc_source = estimate.organic_carbon_percent, "estimated"

    ratings = test.ratings if test and test.ratings else (rate_values(test.values, country_code, subdivision) if test else [])
    return {
        "texture": texture, "texture_source": texture_source,
        "ph": ph, "ph_source": ph_source,
        "organic_carbon_percent": oc, "oc_source": oc_source,
        "oc_rating": ("low" if oc < 0.5 else "medium" if oc <= 0.75 else "high") if oc is not None else None,
        "nitrogen_rating": rating_for(ratings, "nitrogen_kg_ha"),
        "phosphorus_rating": rating_for(ratings, "phosphorus_kg_ha") or rating_for(ratings, "phosphorus_mehlich_mg_dm3"),
        "ec_ds_m": test.values.ec_ds_m if test else None,
        "has_test": test is not None,
        "test_source": test.source if test else None,
    }
