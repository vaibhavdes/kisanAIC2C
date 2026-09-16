"""Maharashtra Agro-Climatic Baseline Data.

Ported from Department of Agriculture & Farmers Welfare (DES 2024-25),
India Meteorological Department (IMD Pune Subdivision Normals), and
Central Ground Water Board (CGWB) district assessments.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DistrictAgroProfile:
    district: str
    subdivision: str  # Vidarbha, Marathwada, Madhya Maharashtra, Konkan
    agro_climatic_zone: str
    normal_rainfall_mm: float
    predominant_soil: str
    groundwater_status: str  # safe, semi-critical, critical, over-exploited
    primary_crops: tuple[str, ...]
    agronomic_notes: str
    monsoon_normal_mm: float | None = None
    soil_profile: dict[str, Any] | None = None
    historical_crop_yields_kg_ha: dict[str, int] | None = None
    dryspell_risk_category: str | None = None



# Comprehensive normalized district baseline for Maharashtra
MAHARASHTRA_DISTRICT_PROFILES: dict[str, DistrictAgroProfile] = {
    "yavatmal": DistrictAgroProfile(
        district="Yavatmal",
        subdivision="Vidarbha",
        agro_climatic_zone="Central Vidarbha Zone",
        normal_rainfall_mm=911.3,
        predominant_soil="black",
        groundwater_status="safe",
        primary_crops=("cotton", "soybean", "pigeon_pea", "sorghum", "chickpea"),
        agronomic_notes="Predominantly rainfed black cotton soil. Highly responsive to pigeon pea + cotton/soybean intercropping to replenish nitrogen and break pink bollworm cycle.",
    ),
    "amravati": DistrictAgroProfile(
        district="Amravati",
        subdivision="Vidarbha",
        agro_climatic_zone="Central Vidarbha Zone",
        normal_rainfall_mm=844.2,
        predominant_soil="black",
        groundwater_status="safe",
        primary_crops=("soybean", "cotton", "pigeon_pea", "chickpea"),
        agronomic_notes="Heavy clay-loam black soils with high water retention. Excellent for kharif soybean followed by rabi chickpea or wheat with supplemental moisture.",
    ),
    "wardha": DistrictAgroProfile(
        district="Wardha",
        subdivision="Vidarbha",
        agro_climatic_zone="Central Vidarbha Zone",
        normal_rainfall_mm=982.0,
        predominant_soil="black",
        groundwater_status="safe",
        primary_crops=("cotton", "soybean", "pigeon_pea", "wheat"),
        agronomic_notes="Deep black soils. High organic carbon potential under no-till or residue retention.",
    ),
    "nagpur": DistrictAgroProfile(
        district="Nagpur",
        subdivision="Vidarbha",
        agro_climatic_zone="Eastern Vidarbha Zone",
        normal_rainfall_mm=1045.0,
        predominant_soil="black",
        groundwater_status="safe",
        primary_crops=("soybean", "cotton", "pigeon_pea", "rice", "chickpea"),
        agronomic_notes="Transition between black soils and red gravelly soils. Good moisture for dual-season kharif pulses and rabi legumes.",
    ),
    "akola": DistrictAgroProfile(
        district="Akola",
        subdivision="Vidarbha",
        agro_climatic_zone="Central Vidarbha Zone",
        normal_rainfall_mm=753.8,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("cotton", "soybean", "pigeon_pea", "sorghum"),
        agronomic_notes="Purna river basin with saline tracts in parts. Deep vertisols require broad bed furrow (BBF) to prevent waterlogging and manage dry spells.",
    ),
    "buldhana": DistrictAgroProfile(
        district="Buldhana",
        subdivision="Vidarbha",
        agro_climatic_zone="Central Vidarbha Zone",
        normal_rainfall_mm=740.5,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("soybean", "cotton", "maize", "pigeon_pea", "chickpea"),
        agronomic_notes="Medium to deep black soils. Maize and soybean rotations thrive under moderate monsoon conditions.",
    ),
    "chandrapur": DistrictAgroProfile(
        district="Chandrapur",
        subdivision="Vidarbha",
        agro_climatic_zone="Eastern Vidarbha Zone",
        normal_rainfall_mm=1190.0,
        predominant_soil="alluvial",
        groundwater_status="safe",
        primary_crops=("rice", "soybean", "cotton", "pigeon_pea"),
        agronomic_notes="High rainfall zone. River basin soils suit irrigated and rainfed paddy as well as kharif pulses.",
    ),
    "gadchiroli": DistrictAgroProfile(
        district="Gadchiroli",
        subdivision="Vidarbha",
        agro_climatic_zone="Eastern Vidarbha Zone",
        normal_rainfall_mm=1350.0,
        predominant_soil="red",
        groundwater_status="safe",
        primary_crops=("rice", "soybean", "sorghum"),
        agronomic_notes="Forested undulating red and lateritic soils. Excellent for direct-seeded or transplanted rice and millets.",
    ),
    "chhatrapati sambhajinagar": DistrictAgroProfile(
        district="Chhatrapati Sambhajinagar",
        subdivision="Marathwada",
        agro_climatic_zone="Marathwada Dryland Zone",
        normal_rainfall_mm=670.0,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("cotton", "maize", "soybean", "pearl_millet", "pigeon_pea"),
        agronomic_notes="Semi-arid Deccan plateau. Pearl millet, maize, and drought-hardy pulses excel under deficit rainfall.",
    ),
    "aurangabad": DistrictAgroProfile(
        district="Chhatrapati Sambhajinagar",
        subdivision="Marathwada",
        agro_climatic_zone="Marathwada Dryland Zone",
        normal_rainfall_mm=670.0,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("cotton", "maize", "soybean", "pearl_millet", "pigeon_pea"),
        agronomic_notes="Semi-arid Deccan plateau. Pearl millet, maize, and drought-hardy pulses excel under deficit rainfall.",
    ),
    "jalna": DistrictAgroProfile(
        district="Jalna",
        subdivision="Marathwada",
        agro_climatic_zone="Marathwada Dryland Zone",
        normal_rainfall_mm=688.0,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("cotton", "soybean", "sorghum", "pigeon_pea", "maize"),
        agronomic_notes="Medium black soils. Intercropping pigeon pea with soybean or sorghum stabilizes income against mid-season dry spells.",
    ),
    "beed": DistrictAgroProfile(
        district="Beed",
        subdivision="Marathwada",
        agro_climatic_zone="Scarcity Zone",
        normal_rainfall_mm=630.0,
        predominant_soil="black",
        groundwater_status="critical",
        primary_crops=("cotton", "soybean", "pearl_millet", "pigeon_pea"),
        agronomic_notes="Drought-prone zone. Low water footprint crops like pearl millet and pigeon pea have highest survival probability.",
    ),
    "latur": DistrictAgroProfile(
        district="Latur",
        subdivision="Marathwada",
        agro_climatic_zone="Marathwada Zone",
        normal_rainfall_mm=760.0,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("soybean", "pigeon_pea", "chickpea", "sugarcane"),
        agronomic_notes="Major pulse and oilseed hub. Soybean-pigeon pea intercrop is the gold standard for agro-ecological resilience.",
    ),
    "dharashiv": DistrictAgroProfile(
        district="Dharashiv",
        subdivision="Marathwada",
        agro_climatic_zone="Scarcity Zone",
        normal_rainfall_mm=710.0,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("soybean", "chickpea", "sorghum", "pigeon_pea"),
        agronomic_notes="Medium vertisols with low groundwater. Rabi jowar and chickpea are reliable post-kharif crops.",
    ),
    "osmanabad": DistrictAgroProfile(
        district="Dharashiv",
        subdivision="Marathwada",
        agro_climatic_zone="Scarcity Zone",
        normal_rainfall_mm=710.0,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("soybean", "chickpea", "sorghum", "pigeon_pea"),
        agronomic_notes="Medium vertisols with low groundwater. Rabi jowar and chickpea are reliable post-kharif crops.",
    ),
    "nanded": DistrictAgroProfile(
        district="Nanded",
        subdivision="Marathwada",
        agro_climatic_zone="Marathwada Eastern Zone",
        normal_rainfall_mm=895.0,
        predominant_soil="black",
        groundwater_status="safe",
        primary_crops=("cotton", "soybean", "pigeon_pea", "sorghum"),
        agronomic_notes="Godavari river basin. Deep fertile black soils suitable for kharif cotton/soybean and rabi pulses.",
    ),
    "parbhani": DistrictAgroProfile(
        district="Parbhani",
        subdivision="Marathwada",
        agro_climatic_zone="Marathwada Zone",
        normal_rainfall_mm=790.0,
        predominant_soil="black",
        groundwater_status="safe",
        primary_crops=("cotton", "soybean", "pigeon_pea", "sorghum"),
        agronomic_notes="Heavy black soils prone to crusting. Surface residue mulching improves infiltration.",
    ),
    "solapur": DistrictAgroProfile(
        district="Solapur",
        subdivision="Madhya Maharashtra",
        agro_climatic_zone="Scarcity Zone",
        normal_rainfall_mm=561.0,
        predominant_soil="black",
        groundwater_status="over-exploited",
        primary_crops=("sorghum", "pearl_millet", "pigeon_pea", "onion"),
        agronomic_notes="Low and erratic rainfall. Famous for Maldandi rabi jowar. High water stress makes sugarcane hazardous under rainfed/groundwater.",
    ),
    "ahmednagar": DistrictAgroProfile(
        district="Ahmednagar",
        subdivision="Madhya Maharashtra",
        agro_climatic_zone="Scarcity Zone",
        normal_rainfall_mm=580.0,
        predominant_soil="black",
        groundwater_status="over-exploited",
        primary_crops=("pearl_millet", "soybean", "onion", "sorghum", "cotton"),
        agronomic_notes="Varying topography from hills to plains. Drip irrigation and raised bed planting recommended for high-value onion and pulses.",
    ),
    "pune": DistrictAgroProfile(
        district="Pune",
        subdivision="Madhya Maharashtra",
        agro_climatic_zone="Western Maharashtra Transition Zone",
        normal_rainfall_mm=690.0,
        predominant_soil="loam",
        groundwater_status="semi-critical",
        primary_crops=("soybean", "maize", "onion", "wheat", "sugarcane"),
        agronomic_notes="Transition from heavy rainfall ghats to eastern dry plains. High diversity of vegetable and cereal rotations.",
    ),
    "nashik": DistrictAgroProfile(
        district="Nashik",
        subdivision="Madhya Maharashtra",
        agro_climatic_zone="Western Maharashtra Transition Zone",
        normal_rainfall_mm=750.0,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("onion", "maize", "soybean", "wheat"),
        agronomic_notes="Leading onion producer in India. Requires balanced NPK and sulfur; rotations with legumes improve disease resistance against purple blotch.",
    ),
    "kolhapur": DistrictAgroProfile(
        district="Kolhapur",
        subdivision="Madhya Maharashtra",
        agro_climatic_zone="Sub-Montane Zone",
        normal_rainfall_mm=1772.0,
        predominant_soil="clay",
        groundwater_status="safe",
        primary_crops=("sugarcane", "rice", "soybean", "groundnut"),
        agronomic_notes="High rainfall and fertile Panchganga alluvial soils. Heavy feeder crops thrive under assured canal/river irrigation.",
    ),
    "satara": DistrictAgroProfile(
        district="Satara",
        subdivision="Madhya Maharashtra",
        agro_climatic_zone="Transition Zone",
        normal_rainfall_mm=850.0,
        predominant_soil="black",
        groundwater_status="safe",
        primary_crops=("soybean", "sorghum", "groundnut", "wheat", "sugarcane"),
        agronomic_notes="Diverse agro-ecology. Groundnut and soybean in kharif followed by wheat or chickpea.",
    ),
    "sangli": DistrictAgroProfile(
        district="Sangli",
        subdivision="Madhya Maharashtra",
        agro_climatic_zone="Transition / Scarcity Zone",
        normal_rainfall_mm=600.0,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("soybean", "maize", "sorghum", "sugarcane"),
        agronomic_notes="Krishna basin. Eastern talukas face drought where sorghum and millets excel; western talukas support irrigated crops.",
    ),
    "jalgaon": DistrictAgroProfile(
        district="Jalgaon",
        subdivision="Madhya Maharashtra",
        agro_climatic_zone="Khandesh Black Soil Zone",
        normal_rainfall_mm=740.0,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("cotton", "maize", "soybean"),
        agronomic_notes="Tapi valley deep alluvial vertisols. High cotton and maize acreage. Broad bed furrow conserves moisture for dry spells.",
    ),
    "dhule": DistrictAgroProfile(
        district="Dhule",
        subdivision="Madhya Maharashtra",
        agro_climatic_zone="Khandesh Scarcity Zone",
        normal_rainfall_mm=620.0,
        predominant_soil="black",
        groundwater_status="semi-critical",
        primary_crops=("cotton", "pearl_millet", "maize", "sorghum"),
        agronomic_notes="Light to medium soils. Bajra and drought-hardy pulses are primary kharif crops.",
    ),
    "nandurbar": DistrictAgroProfile(
        district="Nandurbar",
        subdivision="Madhya Maharashtra",
        agro_climatic_zone="Khandesh Tribal Hill Zone",
        normal_rainfall_mm=820.0,
        predominant_soil="red",
        groundwater_status="safe",
        primary_crops=("maize", "soybean", "cotton", "sorghum"),
        agronomic_notes="Satpuda hill tract. Red and coarse shallow soils; responsive to organic matter and bio-fertilizers.",
    ),
    "ratnagiri": DistrictAgroProfile(
        district="Ratnagiri",
        subdivision="Konkan",
        agro_climatic_zone="South Konkan Coastal Zone",
        normal_rainfall_mm=3100.0,
        predominant_soil="red",
        groundwater_status="safe",
        primary_crops=("rice", "pearl_millet", "groundnut"),
        agronomic_notes="High rainfall coastal laterite soils. Acidic pH (5.0-6.2). Rice is the undisputed kharif staple.",
    ),
    "sindhudurg": DistrictAgroProfile(
        district="Sindhudurg",
        subdivision="Konkan",
        agro_climatic_zone="South Konkan Coastal Zone",
        normal_rainfall_mm=3250.0,
        predominant_soil="red",
        groundwater_status="safe",
        primary_crops=("rice", "groundnut"),
        agronomic_notes="Extreme rainfall coastal strip. Terraced rice and post-rice rabi groundnut with residual moisture.",
    ),
    "raigad": DistrictAgroProfile(
        district="Raigad",
        subdivision="Konkan",
        agro_climatic_zone="North Konkan Coastal Zone",
        normal_rainfall_mm=2900.0,
        predominant_soil="alluvial",
        groundwater_status="safe",
        primary_crops=("rice", "pigeon_pea"),
        agronomic_notes="Coastal alluvial plains. Rice-pulse rotation provides restorative nitrogen.",
    ),
    "thane": DistrictAgroProfile(
        district="Thane",
        subdivision="Konkan",
        agro_climatic_zone="North Konkan Coastal Zone",
        normal_rainfall_mm=2400.0,
        predominant_soil="alluvial",
        groundwater_status="safe",
        primary_crops=("rice", "pearl_millet"),
        agronomic_notes="Coastal zone with high monsoon intensity. Suitable for flood-tolerant and traditional aromatic paddy.",
    ),
    "palghar": DistrictAgroProfile(
        district="Palghar",
        subdivision="Konkan",
        agro_climatic_zone="North Konkan Coastal Zone",
        normal_rainfall_mm=2250.0,
        predominant_soil="red",
        groundwater_status="safe",
        primary_crops=("rice", "chickpea"),
        agronomic_notes="Tribal coastal hill tract. Traditional upland paddy and finger millet rotations.",
    ),
}


def _load_dynamic_profiles() -> dict[str, DistrictAgroProfile] | None:
    import json
    from pathlib import Path
    candidate_paths = [
        Path(__file__).resolve().parent / "../../../../../data/agri_baselines/maharashtra_district_agri_profiles.json",
        Path("/app/data/agri_baselines/maharashtra_district_agri_profiles.json"),
    ]
    for p in candidate_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    res = {}
                    for k, v in data.items():
                        res[k] = DistrictAgroProfile(
                            district=v["district"],
                            subdivision=v["subdivision"],
                            agro_climatic_zone=v["agro_climatic_zone"],
                            normal_rainfall_mm=float(v["normal_rainfall_mm"]),
                            predominant_soil=v["predominant_soil"],
                            groundwater_status=v["groundwater_status"],
                            primary_crops=tuple(v["primary_crops"]),
                            agronomic_notes=v["agronomic_notes"],
                            monsoon_normal_mm=float(v.get("monsoon_normal_mm", v["normal_rainfall_mm"] * 0.88)),
                            soil_profile=v.get("soil_profile"),
                            historical_crop_yields_kg_ha=v.get("historical_crop_yields_kg_ha"),
                            dryspell_risk_category=v.get("dryspell_risk_category", "moderate"),
                        )
                    return res
            except Exception:
                pass
    return None


_DYNAMIC_LOADED: bool = False


def get_district_profile(district_name: str | None) -> DistrictAgroProfile | None:
    """Retrieve agro-climatic profile on-demand (lazy-loaded when requested)."""
    global _DYNAMIC_LOADED
    if not district_name:
        return None

    # Lazy on-demand loading: zero I/O on boot or irrelevant requests
    if not _DYNAMIC_LOADED:
        dynamic_data = _load_dynamic_profiles()
        if dynamic_data:
            MAHARASHTRA_DISTRICT_PROFILES.update(dynamic_data)
        _DYNAMIC_LOADED = True

    normalized = district_name.strip().lower()
    return MAHARASHTRA_DISTRICT_PROFILES.get(normalized)
