"""Soil test interpretation using ICAR / Soil Health Card rating limits.

Limits follow the ratings used on India's Soil Health Card: available N (alkaline
permanganate), P (Olsen), K (ammonium acetate) in kg/ha, organic carbon (Walkley-Black) in %,
and DTPA / hot-water micronutrient critical limits in ppm.
"""

from __future__ import annotations

from .models import SoilEstimate, SoilRating, SoilTest, SoilValues

MACRO_LIMITS = {
    "organic_carbon_percent": ("%", 0.5, 0.75),
    "nitrogen_kg_ha": ("kg/ha", 280.0, 560.0),
    "phosphorus_kg_ha": ("kg/ha", 10.0, 25.0),
    "potassium_kg_ha": ("kg/ha", 108.0, 280.0),
}

MICRO_CRITICAL = {
    "sulphur_ppm": 10.0,
    "zinc_ppm": 0.6,
    "iron_ppm": 4.5,
    "copper_ppm": 0.2,
    "manganese_ppm": 2.0,
    "boron_ppm": 0.5,
}


def ph_rating(ph: float) -> str:
    # Soil Health Card classes: <6.0 acidic, 6.0-6.5 slightly acidic, 6.5-7.5 neutral.
    if ph < 6.0:
        return "acidic"
    if ph < 6.5:
        return "slightly_acidic"
    if ph <= 7.5:
        return "neutral"
    if ph <= 8.5:
        return "alkaline"
    return "strongly_alkaline"


# Countries whose nutrient rating limits (and units) are encoded below. Elsewhere only pH and salinity,
# which do not depend on the lab method, are rated.
NUTRIENT_LIMIT_COUNTRIES = {"IN"}


def rate_values(values: SoilValues, country_code: str = "IN") -> list[SoilRating]:
    ratings: list[SoilRating] = []
    if values.ph is not None:
        ratings.append(SoilRating(parameter="ph", value=values.ph, unit="pH", rating=ph_rating(values.ph)))
    if values.ec_ds_m is not None:
        ratings.append(SoilRating(parameter="ec_ds_m", value=values.ec_ds_m, unit="dS/m",
                                  rating="normal" if values.ec_ds_m < 1.0 else "saline",
                                  note=None if values.ec_ds_m < 1.0 else "Above 1 dS/m can affect germination of sensitive crops"))
    if country_code not in NUTRIENT_LIMIT_COUNTRIES:
        return ratings
    for field, (unit, low, high) in MACRO_LIMITS.items():
        value = getattr(values, field)
        if value is None:
            continue
        rating = "low" if value < low else "medium" if value <= high else "high"
        ratings.append(SoilRating(parameter=field, value=value, unit=unit, rating=rating))
    for field, critical in MICRO_CRITICAL.items():
        value = getattr(values, field)
        if value is None:
            continue
        ratings.append(SoilRating(parameter=field, value=value, unit="ppm",
                                  rating="deficient" if value < critical else "sufficient",
                                  note=f"Critical limit {critical:g} ppm"))
    return ratings


def rating_for(ratings: list[SoilRating], parameter: str) -> str | None:
    return next((item.rating for item in ratings if item.parameter == parameter), None)


FARM_SOIL_TEXTURE = {"black": "heavy", "clay": "heavy", "alluvial": "medium", "loam": "medium", "red": "medium", "sandy": "light"}


def effective_soil(farm_soil_type: str, test: SoilTest | None, estimate: SoilEstimate | None, country_code: str = "IN") -> dict:
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

    ratings = test.ratings if test and test.ratings else (rate_values(test.values, country_code) if test else [])
    return {
        "texture": texture, "texture_source": texture_source,
        "ph": ph, "ph_source": ph_source,
        "organic_carbon_percent": oc, "oc_source": oc_source,
        "oc_rating": ("low" if oc < 0.5 else "medium" if oc <= 0.75 else "high") if oc is not None else None,
        "nitrogen_rating": rating_for(ratings, "nitrogen_kg_ha"),
        "phosphorus_rating": rating_for(ratings, "phosphorus_kg_ha"),
        "ec_ds_m": test.values.ec_ds_m if test else None,
        "has_test": test is not None,
        "test_source": test.source if test else None,
    }
