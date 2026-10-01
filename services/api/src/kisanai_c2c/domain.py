from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .data.maharashtra_agri_context import get_district_profile
from .weather_ops import current_season, forecast_mean, forecast_rain_total, latest_weather_snapshot, operational_forecast_indicators  # noqa: F401
from .models import (
    CropDecisionFactor,
    CropPracticeOption,
    CropRecommendationResult,
    Farm,
    ScoreDimension,
    SoilTest,
)


POLICY_VERSION = "c2c-regenerative-1.0.0"


@dataclass(frozen=True)
class CropPolicy:
    crop: str
    seasons: tuple[str, ...]
    soil_types: tuple[str, ...]
    ph_range: tuple[float, float]
    rainfall_range_mm: tuple[float, float]
    water_need: int
    practice_ids: tuple[str, ...]
    # Seasons in which the crop is commonly grown without irrigation in the region
    # (kharif on monsoon rain, rabi sorghum/chickpea on stored soil moisture).
    rainfed_seasons: tuple[str, ...] = ()
    # Rainfed only where the district's normal annual rainfall is at least this (e.g. Konkan rice).
    rainfed_min_normal_mm: float = 0.0
    # Average daily maximum temperature (C) above which sowing should be delayed.
    sowing_tmax_max: float = 38.0


CROP_POLICIES = (
    CropPolicy("pearl_millet", ("kharif", "summer"), ("red", "sandy", "black", "loam", "unknown"), (5.5, 8.0), (300, 700), 2, ("diverse-rotation", "retain-soil-cover", "rainfall-timed-sowing"), rainfed_seasons=("kharif",), sowing_tmax_max=40.0),
    CropPolicy("sorghum", ("kharif", "rabi"), ("black", "red", "loam", "unknown"), (5.5, 8.5), (350, 800), 2, ("diverse-rotation", "retain-soil-cover", "field-scouting"), rainfed_seasons=("kharif", "rabi"), sowing_tmax_max=35.0),
    CropPolicy("pigeon_pea", ("kharif",), ("black", "red", "alluvial", "loam", "unknown"), (5.0, 8.0), (600, 1000), 2, ("legume-rotation", "retain-soil-cover", "field-scouting"), rainfed_seasons=("kharif",)),
    CropPolicy("soybean", ("kharif",), ("black", "loam", "alluvial", "unknown"), (6.0, 7.5), (500, 900), 2, ("legume-rotation", "broad-bed-furrow", "retain-soil-cover"), rainfed_seasons=("kharif",)),
    CropPolicy("chickpea", ("rabi",), ("black", "alluvial", "loam", "unknown"), (6.0, 8.0), (300, 650), 2, ("legume-rotation", "reduced-disturbance", "field-scouting"), rainfed_seasons=("rabi",), sowing_tmax_max=34.0),
    CropPolicy("wheat", ("rabi",), ("black", "alluvial", "loam", "clay", "unknown"), (6.0, 7.8), (350, 650), 2, ("reduced-disturbance", "residue-management", "rainfall-timed-sowing"), sowing_tmax_max=31.0),
    CropPolicy("groundnut", ("kharif", "summer"), ("red", "sandy", "alluvial", "loam", "unknown"), (6.0, 7.5), (500, 900), 2, ("diverse-rotation", "retain-soil-cover", "drainage-check"), rainfed_seasons=("kharif",), sowing_tmax_max=38.0),
    CropPolicy("maize", ("kharif", "rabi"), ("black", "red", "alluvial", "loam", "unknown"), (5.8, 7.8), (500, 900), 2, ("legume-rotation", "retain-soil-cover", "field-scouting"), rainfed_seasons=("kharif",), sowing_tmax_max=36.0),
    CropPolicy("cotton", ("kharif",), ("black", "unknown"), (6.0, 8.0), (600, 1100), 2, ("diverse-rotation", "field-scouting", "water-budget"), rainfed_seasons=("kharif",)),
    CropPolicy("onion", ("kharif", "rabi", "summer"), ("black", "red", "loam", "alluvial", "unknown"), (6.0, 7.5), (400, 800), 2, ("raised-bed-planting", "drip-irrigation-check", "field-scouting"), sowing_tmax_max=35.0),
    CropPolicy("sugarcane", ("kharif", "rabi", "summer"), ("black", "alluvial", "clay", "loam", "unknown"), (6.0, 8.0), (1000, 2000), 3, ("trash-mulching", "drip-irrigation-budget", "intercropping-pulses"), sowing_tmax_max=40.0),
    CropPolicy("rice", ("kharif",), ("clay", "alluvial", "black", "unknown"), (5.5, 7.5), (900, 1800), 3, ("water-budget", "alternate-wetting-review", "residue-management"), rainfed_seasons=("kharif",), rainfed_min_normal_mm=1200.0),
)


WATER_RANK = {"rainfed": 1, "supplemental_irrigation": 2, "irrigated": 3}


def effective_water_need(policy: CropPolicy, season: str | None, district_profile: Any = None) -> int:
    """Water-access level the crop needs in this season and district (1 = rainfed is enough)."""
    if season in policy.rainfed_seasons:
        if policy.rainfed_min_normal_mm <= 0:
            return 1
        if district_profile and district_profile.normal_rainfall_mm >= policy.rainfed_min_normal_mm:
            return 1
    return policy.water_need


def rain_fit_score(policy: CropPolicy, season: str | None, rainfall_7d_mm: float | None) -> float | None:
    """Kharif sowing needs monsoon rain; rabi and summer crops are sown on stored moisture or
    irrigation, where only heavy rain is a problem."""
    if rainfall_7d_mm is None:
        return None
    if season == "kharif":
        target = min(policy.rainfall_range_mm[1] / 8, max(1.0, policy.rainfall_range_mm[0] / 12))
        return max(0.0, min(1.0, rainfall_7d_mm / target))
    return 0.6 if rainfall_7d_mm >= 50.0 else 1.0


def temperature_fit_score(policy: CropPolicy, mean_tmax: float | None) -> float | None:
    if mean_tmax is None:
        return None
    if mean_tmax <= policy.sowing_tmax_max:
        return 1.0
    if mean_tmax <= policy.sowing_tmax_max + 3:
        return 0.6
    return 0.3


def build_options(
    farm: Farm,
    soil: SoilTest | None,
    *,
    goal: str,
    season: str | None,
    rainfall_7d_mm: float | None,
) -> list[CropPracticeOption]:
    if goal == "manage_current_crop":
        if not farm.current_crop or farm.crop_status != "planted":
            raise ValueError("A planted current crop is required for management advice")
        policies = [policy for policy in CROP_POLICIES if policy.crop == normalize_crop(farm.current_crop)]
        if not policies:
            policies = [
                CropPolicy(
                    normalize_crop(farm.current_crop),
                    tuple([season] if season else []),
                    (farm.soil_type, "unknown"),
                    (0, 14),
                    (0, 10000),
                    WATER_RANK[farm.water_access],
                    ("retain-soil-cover", "field-scouting", "water-budget"),
                )
            ]
    else:
        if not season:
            raise ValueError("Season is required for crop planning")
        policies = list(CROP_POLICIES)

    result: list[CropPracticeOption] = []
    for policy in policies:
        rejections: list[str] = []
        dimensions: list[ScoreDimension] = []
        if goal == "crop_plan" and season not in policy.seasons:
            rejections.append(f"{policy.crop} is outside the configured {season} planting policy")
            climate_score = 0.0
        else:
            climate_score = 1.0
        dimensions.append(ScoreDimension(name="season_fit", score=climate_score, explanation="Configured crop-season eligibility"))

        need = effective_water_need(policy, season, get_district_profile(farm.district))
        water_score = min(1.0, WATER_RANK[farm.water_access] / need)
        if WATER_RANK[farm.water_access] < need:
            rejections.append("Water access is below the crop's configured minimum")
        dimensions.append(ScoreDimension(name="water_fit", score=water_score, explanation=f"Farm access {farm.water_access}; crop need level {need}"))

        if farm.soil_type not in policy.soil_types:
            soil_score: float | None = 0.0
            rejections.append(f"Confirmed soil type {farm.soil_type} is outside the configured range")
        elif farm.soil_type == "unknown":
            soil_score = None
        else:
            soil_score = 1.0
        if soil and soil.values.ph is not None:
            if not policy.ph_range[0] <= soil.values.ph <= policy.ph_range[1]:
                rejections.append(f"Confirmed soil pH {soil.values.ph:g} is outside {policy.ph_range[0]:g}–{policy.ph_range[1]:g}")
                soil_score = 0.0
            elif soil_score is None:
                soil_score = 0.8
        dimensions.append(ScoreDimension(name="soil_fit", score=soil_score, explanation="Uses confirmed soil type and pH only"))

        rain_score = rain_fit_score(policy, season, rainfall_7d_mm)
        dimensions.append(ScoreDimension(name="near_term_rain_context", score=rain_score, explanation="Seven-day forecast context; not seasonal rainfall"))

        previous = normalize_crop(farm.previous_crop or "")
        rotation_score = 1.0 if previous and previous != policy.crop else (0.4 if previous else None)
        if previous == policy.crop:
            rejections.append("Repeating the previous crop weakens rotation diversity; expert review required")
        dimensions.append(ScoreDimension(name="rotation_diversity", score=rotation_score, explanation="Compares farmer-confirmed previous crop"))

        scored = [item.score for item in dimensions if item.score is not None]
        coverage = len(scored) / len(dimensions)
        rank = sum(scored) / len(scored) if scored and not rejections else None
        result.append(
            CropPracticeOption(
                crop=policy.crop,
                practice_ids=list(policy.practice_ids),
                eligible=not rejections,
                rejection_reasons=rejections,
                dimensions=dimensions,
                evidence_coverage=coverage,
                rank_score=rank,
            )
        )
    return sorted(result, key=lambda item: item.rank_score if item.rank_score is not None else -1, reverse=True)


def normalize_crop(value: str) -> str:
    aliases = {
        "millet": "pearl_millet",
        "bajra": "pearl_millet",
        "jowar": "sorghum",
        "tur": "pigeon_pea",
        "arhar": "pigeon_pea",
        "gram": "chickpea",
        "harbara": "chickpea",
        "chana": "chickpea",
        "paddy": "rice",
        "bhat": "rice",
        "dhan": "rice",
        "soyabean": "soybean",
        "gahu": "wheat",
        "gehu": "wheat",
        "kanda": "onion",
        "pyaj": "onion",
        "oos": "sugarcane",
        "ganna": "sugarcane",
        "maka": "maize",
        "bhutta": "maize",
        "bhuimug": "groundnut",
        "mungfali": "groundnut",
        "kapas": "cotton",
        "kapus": "cotton",
    }
    cleaned = "_".join(value.strip().lower().split())
    return aliases.get(cleaned, cleaned)


def rainfall_total(evidence: list[dict[str, Any]]) -> float | None:
    """Forecast rain over the next 7 days from the newest weather snapshot."""
    return forecast_rain_total(evidence)


CROP_LOCALIZED_NAMES: dict[str, dict[str, str]] = {
    "pearl_millet": {"en-IN": "Pearl Millet (Bajra)", "hi-IN": "बाजरा (Bajra)", "mr-IN": "बाजरी (Bajra)", "te-IN": "సజ్జ (Bajra)", "kn-IN": "ಸಜ್ಜೆ (Bajra)"},
    "sorghum": {"en-IN": "Sorghum (Jowar)", "hi-IN": "ज्वार (Jowar)", "mr-IN": "ज्वारी (Jowar)", "te-IN": "జొన్న (Jowar)", "kn-IN": "ಜೋಳ (Jowar)"},
    "pigeon_pea": {"en-IN": "Pigeon Pea (Tur / Arhar)", "hi-IN": "अरहर / तूर (Tur)", "mr-IN": "तूर (Tur)", "te-IN": "కంది (Kandi)", "kn-IN": "ತೊಗರಿ (Togari)"},
    "soybean": {"en-IN": "Soybean", "hi-IN": "सोयाबीन (Soybean)", "mr-IN": "सोयाबीन (Soybean)", "te-IN": "సోయాబీన్ (Soybean)", "kn-IN": "ಸೋಯಾಬೀನ್ (Soybean)"},
    "chickpea": {"en-IN": "Chickpea (Gram / Harbara)", "hi-IN": "चना (Chana)", "mr-IN": "हरभरा (Harbara)", "te-IN": "శనగ (Sanaga)", "kn-IN": "ಕಡಲೆ (Kadale)"},
    "wheat": {"en-IN": "Wheat (Gahu)", "hi-IN": "गेहूँ (Wheat)", "mr-IN": "गहू (Wheat)", "te-IN": "గోధుమ (Wheat)", "kn-IN": "ಗೋಧಿ (Wheat)"},
    "groundnut": {"en-IN": "Groundnut (Bhuimug)", "hi-IN": "मूंगफली (Groundnut)", "mr-IN": "भुईमूग (Bhuimug)", "te-IN": "వేరుశనగ (Verusanaga)", "kn-IN": "ಕಡಲೆಕಾಯಿ (Kadalekayi)"},
    "maize": {"en-IN": "Maize (Makka)", "hi-IN": "मक्का (Makka)", "mr-IN": "मका (Makka)", "te-IN": "మొక్కజొన్న (Mokkajonna)", "kn-IN": "ಮೆಕ್ಕೆಜೋಳ (Mekkejola)"},
    "cotton": {"en-IN": "Cotton (Kapas)", "hi-IN": "कपास (Kapas)", "mr-IN": "कापूस (Kapas)", "te-IN": "పత్తి (Patti)", "kn-IN": "ಹತ್ತಿ (Hatti)"},
    "onion": {"en-IN": "Onion (Kanda)", "hi-IN": "प्याज (Pyaaz)", "mr-IN": "कांदा (Kanda)", "te-IN": "ఉల్లిపాయ (Ullipaya)", "kn-IN": "ಈರುಳ್ಳಿ (Eerulli)"},
    "sugarcane": {"en-IN": "Sugarcane (Oos)", "hi-IN": "गन्ना (Ganna)", "mr-IN": "ऊस (Oos)", "te-IN": "చెరకు (Cheraku)", "kn-IN": "ಕಬ್ಬು (Kabbu)"},
    "rice": {"en-IN": "Rice / Paddy (Bhat)", "hi-IN": "धान / चावल (Paddy)", "mr-IN": "भात (Paddy)", "te-IN": "వరి (Vari)", "kn-IN": "ಭತ್ತ (Bhatta)"},
}

PRACTICE_LOCALIZED_NAMES: dict[str, dict[str, str]] = {
    "diverse-rotation": {"en-IN": "Change crops each season", "hi-IN": "विविध फसल चक्र", "mr-IN": "विविध पीक फेरपालट", "te-IN": "వివిధ పంటల మార్పిడి", "kn-IN": "ವಿವಿಧ ಬೆಳೆ ಪರಿವರ್ತನೆ"},
    "retain-soil-cover": {"en-IN": "Leave crop residue on the soil", "hi-IN": "मल्चिंग व जैविक आच्छादन", "mr-IN": "सेंद्रिय आच्छादन (मल्चिंग)", "te-IN": "భూమిపై ఆచ్ఛాదన (మల్చింగ్)", "kn-IN": "ಮಲ್ಚಿಂಗ್ ಮತ್ತು ಹೊದಿಕೆ"},
    "rainfall-timed-sowing": {"en-IN": "Sow after good rain", "hi-IN": "वर्षा आधारित बुवाई", "mr-IN": "पावसावर आधारित अचूक पेरणी", "te-IN": "వర్ష ఆధారిత విత్తనం", "kn-IN": "ಮಳೆ ಆಧಾರಿತ ಬಿತ್ತನೆ"},
    "field-scouting": {"en-IN": "Check the field for pests every week", "hi-IN": "नियमित कीट निगरानी", "mr-IN": "नियमित शेत कीड पाहणी", "te-IN": "పొలం కీటకాల పర్యవేక్షణ", "kn-IN": "ಕೀಟಗಳ ನಿಯಮಿತ ಪರಿಶೀಲನೆ"},
    "legume-rotation": {"en-IN": "Grow a pulse in rotation", "hi-IN": "दलहनी फसल चक्र (नाइट्रोजन वृद्धि)", "mr-IN": "कडधान्य फेरपालट (नत्र स्थिरीकरण)", "te-IN": "నత్రజని స్థిరీకరణ పంట మార్పిడి", "kn-IN": "ಸಾರಜನಕ ಹೆಚ್ಚಿಸುವ ಬೆಳೆ ಪದ್ಧತಿ"},
    "broad-bed-furrow": {"en-IN": "Raised beds with furrows (BBF)", "hi-IN": "चौड़ा बेड और नाली (BBF) पद्धति", "mr-IN": "रुंद वरंबा व सरी (BBF) पद्धत", "te-IN": "విస్తృత బెడ్ మరియు ఫర్రో (BBF)", "kn-IN": "ಅಗಲವಾದ ಮಡಿ ಮತ್ತು ಸಾಲು (BBF)"},
    "reduced-disturbance": {"en-IN": "Plough less", "hi-IN": "शून्य / न्यूनतम जुताई", "mr-IN": "किमान मशागत व जमिनीचे रक्षण", "te-IN": "కనిష్ట దుక్కి పద్ధతి", "kn-IN": "ಕನಿಷ್ಠ ಉಳುಮೆ ಪದ್ಧತಿ"},
    "drainage-check": {"en-IN": "Drain extra water, save rainwater", "hi-IN": "जल संचयन एवं जल निकासी", "mr-IN": "पाणी निचरा व जलसंधारण", "te-IN": "నీటి నిల్వ మరియు పారుదల", "kn-IN": "ನೀರು ಹಿಂಗಿಸುವಿಕೆ ಮತ್ತು ಬಸಿದು ಹೋಗುವ ವ್ಯವಸ್ಥೆ"},
    "raised-bed-planting": {"en-IN": "Plant on raised beds", "hi-IN": "ऊंची क्यारियों पर रोपाई", "mr-IN": "गादी वाफ्यावर लागवड", "te-IN": "ఎత్తైన మడులపై నాటడం", "kn-IN": "ಎತ್ತರಿಸಿದ ಮಡಿಗಳಲ್ಲಿ ನಾಟಿ"},
    "drip-irrigation-check": {"en-IN": "Water with drip", "hi-IN": "ड्रिप से सिंचाई", "mr-IN": "ठिबकने पाणी", "te-IN": "డ్రిప్‌తో నీరు", "kn-IN": "ಹನಿ ನೀರಾವರಿ"},
    "drip-irrigation-budget": {"en-IN": "Drip irrigation and careful watering", "hi-IN": "ड्रिप सिंचाई और पानी की बचत", "mr-IN": "ठिबक सिंचन व पाण्याची बचत", "te-IN": "డ్రిప్ సాగు, నీటి పొదుపు", "kn-IN": "ಹನಿ ನೀರಾವರಿ, ನೀರಿನ ಉಳಿತಾಯ"},
    "trash-mulching": {"en-IN": "Spread cane trash as mulch", "hi-IN": "गन्ने की पत्तियों का आच्छादन", "mr-IN": "उसाच्या पाचटाचे आच्छादन", "te-IN": "చెరకు ఆకుల మల్చింగ్", "kn-IN": "ಕಬ್ಬಿನ ಸೋಗೆ ಹೊದಿಕೆ"},
    "intercropping-pulses": {"en-IN": "Grow a pulse between rows", "hi-IN": "कतारों के बीच दाल की फसल", "mr-IN": "ओळींमध्ये कडधान्य आंतरपीक", "te-IN": "వరుసల మధ్య పప్పు అంతర పంట", "kn-IN": "ಸಾಲುಗಳ ನಡುವೆ ಬೇಳೆ ಅಂತರ ಬೆಳೆ"},
    "alternate-wetting-review": {"en-IN": "Let the paddy dry between waterings", "hi-IN": "धान में बीच-बीच में पानी सूखने दें", "mr-IN": "भातात मधूनमधून पाणी सुकू द्या", "te-IN": "వరిలో మధ్యమధ్యలో నీరు ఆరనివ్వండి", "kn-IN": "ಭತ್ತದಲ್ಲಿ ನಡುನಡುವೆ ನೀರು ಒಣಗಲು ಬಿಡಿ"},
    "residue-management": {"en-IN": "Don't burn crop residue; mix or mulch it", "hi-IN": "फसल अवशेष न जलाएं; मिलाएं या ढकें", "mr-IN": "पिकाचे अवशेष जाळू नका; मिसळा किंवा आच्छादन करा", "te-IN": "పంట అవశేషాలు కాల్చవద్దు; కలపండి", "kn-IN": "ಬೆಳೆ ಉಳಿಕೆ ಸುಡಬೇಡಿ; ಬೆರೆಸಿ"},
    "water-budget": {"en-IN": "Drip irrigation and careful watering", "hi-IN": "सूक्ष्म सिंचाई एवं जल बजट", "mr-IN": "ठिबक सिंचन व पाणी नियोजन", "te-IN": "బిందు సేద్యం మరియు నీటి ప్రణాళిక", "kn-IN": "ಹನಿ ನೀರಾವರಿ ಮತ್ತು ನೀರಿನ ಬಳಕೆ ಯೋಜನೆ"},
}


REMEDIES: dict[str, dict[str, str]] = {
    "season": {
        "en-IN": "Plan this crop for its own season.",
        "hi-IN": "यह फसल उसके अपने मौसम में लगाएं।",
        "mr-IN": "हे पीक त्याच्या हंगामात घ्या.",
        "te-IN": "ఈ పంటను దాని సీజన్‌లో వేయండి.",
        "kn-IN": "ಈ ಬೆಳೆಯನ್ನು ಅದರ ಹಂಗಾಮಿನಲ್ಲಿ ಬೆಳೆಯಿರಿ.",
    },
    "water": {
        "en-IN": "Only grow this if you have a well, canal or drip line you can rely on.",
        "hi-IN": "यह फसल तभी लगाएं जब कुआं, नहर या ड्रिप पक्का हो।",
        "mr-IN": "विहीर, कालवा किंवा ठिबक खात्रीशीर असेल तरच हे पीक घ्या.",
        "te-IN": "బావి, కాలువ లేదా డ్రిప్ నమ్మకంగా ఉంటేనే ఈ పంట వేయండి.",
        "kn-IN": "ಬಾವಿ, ಕಾಲುವೆ ಅಥವಾ ಹನಿ ನೀರಾವರಿ ಖಚಿತವಿದ್ದರೆ ಮಾತ್ರ ಈ ಬೆಳೆ ಬೆಳೆಯಿರಿ.",
    },
    "soil": {
        "en-IN": "Add compost or farmyard manure, and get a soil test to fix the pH.",
        "hi-IN": "कंपोस्ट या गोबर खाद डालें, और pH ठीक करने के लिए मिट्टी जांच कराएं।",
        "mr-IN": "कंपोस्ट किंवा शेणखत टाका, आणि सामू सुधारण्यासाठी माती परीक्षण करा.",
        "te-IN": "కంపోస్ట్ లేదా పశువుల ఎరువు వేయండి, pH కోసం నేల పరీక్ష చేయించండి.",
        "kn-IN": "ಕಾಂಪೋಸ್ಟ್ ಅಥವಾ ಕೊಟ್ಟಿಗೆ ಗೊಬ್ಬರ ಹಾಕಿ, pH ಗಾಗಿ ಮಣ್ಣು ಪರೀಕ್ಷೆ ಮಾಡಿಸಿ.",
    },
    "rotation": {
        "en-IN": "Grow a pulse such as tur, gram or moong, or a cereal, before coming back to this crop.",
        "hi-IN": "इस फसल से पहले अरहर, चना, मूंग जैसी दाल या कोई अनाज लगाएं।",
        "mr-IN": "हे पीक पुन्हा घेण्यापूर्वी तूर, हरभरा, मूग असे कडधान्य किंवा तृणधान्य घ्या.",
        "te-IN": "మళ్లీ ఈ పంట వేసే ముందు కంది, శనగ, పెసర వంటి పప్పు లేదా ధాన్యం వేయండి.",
        "kn-IN": "ಮತ್ತೆ ಈ ಬೆಳೆಗೆ ಮುನ್ನ ತೊಗರಿ, ಕಡಲೆ, ಹೆಸರು ಅಂತಹ ಬೇಳೆ ಅಥವಾ ಧಾನ್ಯ ಬೆಳೆಯಿರಿ.",
    },
    "heat": {
        "en-IN": "Wait 1–2 weeks for cooler days before sowing.",
        "hi-IN": "बुवाई से पहले 1–2 हफ्ते ठंडे दिनों का इंतज़ार करें।",
        "mr-IN": "पेरणीपूर्वी १–२ आठवडे थंड दिवसांची वाट पाहा.",
        "te-IN": "విత్తే ముందు 1–2 వారాలు చల్లని రోజుల కోసం ఆగండి.",
        "kn-IN": "ಬಿತ್ತುವ ಮೊದಲು 1–2 ವಾರ ತಂಪು ದಿನಗಳಿಗಾಗಿ ಕಾಯಿರಿ.",
    },
    "heavy_rain": {
        "en-IN": "Sow once the heavy rain has passed and the field can be worked.",
        "hi-IN": "भारी बारिश रुकने और खेत तैयार होने के बाद बोएं।",
        "mr-IN": "मुसळधार पाऊस थांबून वाफसा आल्यावर पेरा.",
        "te-IN": "భారీ వర్షం తగ్గి పొలం సిద్ధమైన తర్వాత విత్తండి.",
        "kn-IN": "ಭಾರೀ ಮಳೆ ನಿಂತು ಹೊಲ ಸಿದ್ಧವಾದ ನಂತರ ಬಿತ್ತಿ.",
    },
    "dry": {
        "en-IN": "Don't sow into dry soil; wait for a good rain.",
        "hi-IN": "सूखी मिट्टी में न बोएं; अच्छी बारिश का इंतज़ार करें।",
        "mr-IN": "कोरड्या जमिनीत पेरू नका; चांगल्या पावसाची वाट पाहा.",
        "te-IN": "పొడి నేలలో విత్తవద్దు; మంచి వర్షం కోసం ఆగండి.",
        "kn-IN": "ಒಣ ಮಣ್ಣಿನಲ್ಲಿ ಬಿತ್ತಬೇಡಿ; ಒಳ್ಳೆಯ ಮಳೆಗಾಗಿ ಕಾಯಿರಿ.",
    },
}


def soil_ph(soil: SoilTest | None, district_profile: Any) -> tuple[float | None, str]:
    """Measured pH from the farmer's soil card, else the district baseline, else unknown."""
    if soil and soil.values.ph is not None:
        return soil.values.ph, "soil card"
    profile_ph = ((district_profile.soil_profile or {}).get("ph_typical") if district_profile else None)
    if isinstance(profile_ph, (int, float)):
        return float(profile_ph), "district baseline"
    return None, "unknown"


def _build_factor_breakdowns(
    policy: CropPolicy,
    farm: Farm,
    soil: SoilTest | None,
    season: str,
    rainfall_7d: float | None,
    previous: str,
    locale: str,
    district_profile: Any,
    mean_tmax: float | None = None,
) -> list[CropDecisionFactor]:
    factors: list[CropDecisionFactor] = []
    lang = locale if locale in {"en-IN", "hi-IN", "mr-IN", "te-IN", "kn-IN"} else "en-IN"

    # Factor 1: Season & Planting Window
    is_season_ok = season in policy.seasons
    season_status = "optimal" if is_season_ok else "rejected"
    season_data = f"Season: {season.title()} | Sowing Seasons: {', '.join(s.title() for s in policy.seasons)}"
    if is_season_ok:
        s_reasons = {
            "en-IN": f"Right season. This crop is normally sown in {season}.",
            "hi-IN": f"बुवाई का आदर्श समय। {policy.crop.replace('_', ' ').title()} {season} मौसम के लिए पूर्णतः उपयुक्त है।",
            "mr-IN": f"पेरणीसाठी योग्य हंगाम. {season} हंगामाच्या हवामानात हे पीक उत्तम येते.",
            "te-IN": f"విత్తడానికి అనుకూలమైన సమయం. {season} కాలానికి ఈ పంట చాలా అనుకూలం.",
            "kn-IN": f"ಬಿತ್ತನೆಗೆ ಸೂಕ್ತ ಸಮಯ. {season} ಹಂಗಾಮಿಗೆ ಈ ಬೆಳೆ ಅತ್ಯಂತ ಯೋಗ್ಯವಾಗಿದೆ.",
        }
    else:
        s_reasons = {
            "en-IN": f"Wrong season. This crop is sown in {', '.join(policy.seasons)}, not in {season}.",
            "hi-IN": f"मौसम अनुकूल नहीं है। यह फसल {', '.join(policy.seasons)} के लिए है, {season} में नहीं।",
            "mr-IN": f"हंगाम जुळत नाही. हे पीक {', '.join(policy.seasons)} साठी आहे, {season} मध्ये लावू नये.",
            "te-IN": f"సీజన్ అనుకూలం కాదు. ఇది {', '.join(policy.seasons)} కోసం నిర్దేశించబడింది.",
            "kn-IN": f"ಹಂಗಾಮು ಸರಿಹೊಂದುವುದಿಲ್ಲ. ಇದು {', '.join(policy.seasons)} ಗೆ ಸೂಕ್ತವಾಗಿದೆ.",
        }
    factors.append(
        CropDecisionFactor(
            factor_id="season",
            factor_name={"en-IN": "Season", "hi-IN": "हंगाम व बुवाई का समय", "mr-IN": "हंगाम व पेरणी कालावधी", "te-IN": "సీజన్ మరియు విత్తన సమయం", "kn-IN": "ಹಂಗಾಮು ಮತ್ತು ಬಿತ್ತನೆ ಸಮಯ"}[lang],
            status=season_status,
            data_used=season_data,
            reasoning=s_reasons[lang],
            remedy=None if is_season_ok else REMEDIES["season"][lang],
        )
    )

    # Factor 2: Water Access & Feasibility
    water_rank = WATER_RANK.get(farm.water_access, 1)
    need = effective_water_need(policy, season, district_profile)
    is_water_ok = water_rank >= need
    water_status = "optimal" if is_water_ok else "rejected"
    water_data = f"Farm Water: {farm.water_access.replace('_', ' ').title()} (Level {water_rank}) | Crop Need: Level {need} ({policy.rainfall_range_mm[0]}–{policy.rainfall_range_mm[1]}mm)"
    if is_water_ok:
        w_reasons = {
            "en-IN": f"Your water is enough. A {farm.water_access.replace('_', ' ')} field can meet this crop's need ({policy.rainfall_range_mm[0]}–{policy.rainfall_range_mm[1]} mm a season).",
            "hi-IN": f"पानी की पर्याप्तता सुनिश्चित। खेत की {farm.water_access} स्थिति फसल की जल आवश्यकता ({policy.rainfall_range_mm[0]}–{policy.rainfall_range_mm[1]} मिमी) को पूरा करती है।",
            "mr-IN": f"पाणी उपलब्धता योग्य. शेतातील {farm.water_access} पद्धतीनुसार या पिकाची पाण्याची गरज ({policy.rainfall_range_mm[0]}–{policy.rainfall_range_mm[1]} मिमी) पूर्ण होते.",
            "te-IN": f"నీటి లభ్యత సరిపోతుంది. పంట నీటి అవసరాలను ({policy.rainfall_range_mm[0]}–{policy.rainfall_range_mm[1]} మి.మీ) పొలం నీటి వసతి తీరుస్తుంది.",
            "kn-IN": f"ನೀರಿನ ಲಭ್ಯತೆ ಸೂಕ್ತವಾಗಿದೆ. ಬೆಳೆಯ ನೀರಿನ ಅಗತ್ಯವನ್ನು ({policy.rainfall_range_mm[0]}–{policy.rainfall_range_mm[1]} ಮಿ.ಮೀ) ತೋಟದ ಸೌಲಭ್ಯ ಪೂರೈಸುತ್ತದೆ.",
        }
    else:
        w_reasons = {
            "en-IN": f"Not enough water. This crop needs at least {policy.rainfall_range_mm[0]} mm a season and assured irrigation, but your field is {farm.water_access.replace('_', ' ')}.",
            "hi-IN": f"पानी की कमी का गंभीर जोखिम। इस फसल को स्तर {need} सिंचाई चाहिए, जबकि खेत {farm.water_access} है।",
            "mr-IN": f"पाण्याचा तुटवडा धोका. या पिकाला किमान {policy.rainfall_range_mm[0]} मिमी पाणी लागते, मात्र शेत {farm.water_access} आहे.",
            "te-IN": f"నీటి కొరత ప్రమాదం. పంటకు ఎక్కువ నీరు అవసరం, కానీ పొలం వర్షాధారితం/తక్కువ నీరు కలిగి ఉంది.",
            "kn-IN": f"ನೀರಿನ ಕೊರತೆಯ ಅಪಾಯ. ಈ ಬೆಳೆಗೆ ಹೆಚ್ಚಿನ ನೀರು ಬೇಕು, ಆದರೆ ಜಮೀನು ಮಳೆಯಾಶ್ರಿತವಾಗಿದೆ.",
        }
    factors.append(
        CropDecisionFactor(
            factor_id="water",
            factor_name={"en-IN": "Water", "hi-IN": "जल उपलब्धता एवं आवश्यकता", "mr-IN": "पाणी उपलब्धता व गरज", "te-IN": "నీటి లభ్యత మరియు అవసరం", "kn-IN": "ನೀರಿನ ಲಭ್ಯತೆ ಮತ್ತು ಅಗತ್ಯ"}[lang],
            status=water_status,
            data_used=water_data,
            reasoning=w_reasons[lang],
            remedy=None if is_water_ok else REMEDIES["water"][lang],
        )
    )

    # Factor 3: Soil Type & pH Match
    soil_compatible = farm.soil_type in policy.soil_types or farm.soil_type == "unknown"
    ph_val, ph_source = soil_ph(soil, district_profile)
    ph_ok = ph_val is None or policy.ph_range[0] <= ph_val <= policy.ph_range[1]
    soil_status = "optimal" if (soil_compatible and ph_ok) else ("compatible" if soil_compatible else "constrained")
    ph_label = f"{ph_val:.1f} ({ph_source})" if ph_val is not None else "not tested"
    soil_data = f"Soil: {farm.soil_type.title()} | pH: {ph_label} (Optimal: {policy.ph_range[0]}–{policy.ph_range[1]})"
    ph_val = ph_val if ph_val is not None else (policy.ph_range[0] + policy.ph_range[1]) / 2
    if soil_compatible and ph_ok:
        soil_reasons = {
            "en-IN": f"Your soil suits it. {farm.soil_type.title()} soil with pH {ph_val:.1f} is good for this crop.",
            "hi-IN": f"मिट्टी पूर्णतः अनुकूल। {farm.soil_type.title()} मिट्टी और pH {ph_val:.1f} जड़ों के उत्तम विकास में सहायक है।",
            "mr-IN": f"माती अत्यंत अनुकूल. {farm.soil_type.title()} माती आणि सामू (pH {ph_val:.1f}) मुळांच्या वाढीसाठी उत्तम आहे.",
            "te-IN": f"నేల చాలా అనుకూలం. {farm.soil_type.title()} నేల మరియు pH {ph_val:.1f} వేర్ల పెరుగుదలకు మంచిది.",
            "kn-IN": f"ಮಣ್ಣು ಅತ್ಯಂತ ಸೂಕ್ತವಾಗಿದೆ. {farm.soil_type.title()} ಮಣ್ಣು ಮತ್ತು pH {ph_val:.1f} ಬೇರುಗಳ ಸಮೃದ್ಧ ಬೆಳವಣಿಗೆಗೆ ಸಹಕಾರಿ.",
        }
    else:
        soil_reasons = {
            "en-IN": f"Your soil is not ideal. {farm.soil_type.title()} soil or pH {ph_val:.1f} may lower the yield unless you improve it.",
            "hi-IN": f"मिट्टी अनुकूलन सीमित। {farm.soil_type} मिट्टी या pH {ph_val:.1f} सुधार के बिना उपज कम कर सकता है।",
            "mr-IN": f"माती मर्यादित अनुकूल. {farm.soil_type} माती किंवा सामू सुधारल्याशिवाय उत्पादनावर परिणाम होऊ शकतो.",
            "te-IN": f"నేల పరిస్థితులు పరిమితం. తగిన జాగ్రత్తలు తీసుకోవడం అవసరం.",
            "kn-IN": f"ಮಣ್ಣಿನ ಪರಿಸ್ಥಿತಿ ಸೀಮಿತವಾಗಿದೆ. ಮಣ್ಣು ತಿದ್ದುಪಡಿ ಅಗತ್ಯ.",
        }
    factors.append(
        CropDecisionFactor(
            factor_id="soil",
            factor_name={"en-IN": "Soil and pH", "hi-IN": "मृदा प्रकार एवं pH सामू", "mr-IN": "मातीचा प्रकार व सामू (pH)", "te-IN": "నేల రకం మరియు pH", "kn-IN": "ಮಣ್ಣಿನ ವಿಧ ಮತ್ತು pH"}[lang],
            status=soil_status,
            data_used=soil_data,
            reasoning=soil_reasons[lang],
            remedy=None if (soil_compatible and ph_ok) else REMEDIES["soil"][lang],
        )
    )

    # Factor 4: 7-day rainfall and temperature forecast, judged for the season being planned
    rain_val = rainfall_7d or 0.0
    rain_score = rain_fit_score(policy, season, rainfall_7d)
    temp_score = temperature_fit_score(policy, mean_tmax)
    tmax_text = f"{mean_tmax:.0f}" if mean_tmax is not None else "--"
    weather_data = f"7-Day Rain Total: {rain_val:.1f} mm | Avg max temp: {tmax_text}°C (sowing limit {policy.sowing_tmax_max:.0f}°C)"
    rain_ok = rain_score is None or rain_score >= 0.8
    if temp_score is not None and temp_score < 1.0:
        w_status = "constrained" if temp_score < 0.6 else "compatible"
        wea_reasons = {
            "en-IN": f"Too warm for sowing now: average maximum {tmax_text}°C is above this crop's {policy.sowing_tmax_max:.0f}°C limit.",
            "hi-IN": f"अभी बुवाई के लिए अधिक गर्मी: औसत अधिकतम {tmax_text}°C इस फसल की {policy.sowing_tmax_max:.0f}°C सीमा से अधिक है।",
            "mr-IN": f"सध्या पेरणीसाठी जास्त उष्णता: सरासरी कमाल {tmax_text}°C या पिकाच्या {policy.sowing_tmax_max:.0f}°C मर्यादेपेक्षा जास्त आहे.",
            "te-IN": f"ఇప్పుడు విత్తడానికి ఎక్కువ వేడి: సగటు గరిష్ఠ {tmax_text}°C, ఈ పంట పరిమితి {policy.sowing_tmax_max:.0f}°C.",
            "kn-IN": f"ಈಗ ಬಿತ್ತನೆಗೆ ಹೆಚ್ಚು ಬಿಸಿ: ಸರಾಸರಿ ಗರಿಷ್ಠ {tmax_text}°C, ಈ ಬೆಳೆಯ ಮಿತಿ {policy.sowing_tmax_max:.0f}°C.",
        }
        w_remedy = REMEDIES["heat"][lang]
    elif season != "kharif":
        w_status = "optimal" if rain_ok else "compatible"
        if rain_ok:
            wea_reasons = {
                "en-IN": f"Weather suits {season} sowing: {rain_val:.1f} mm rain forecast and avg max {tmax_text}°C. Sow on stored soil moisture or with irrigation.",
                "hi-IN": f"{season} बुवाई के लिए मौसम अनुकूल: {rain_val:.1f} मिमी वर्षा अनुमान, औसत अधिकतम {tmax_text}°C। संचित नमी या सिंचाई पर बोएं।",
                "mr-IN": f"{season} पेरणीसाठी हवामान अनुकूल: {rain_val:.1f} मिमी पाऊस अंदाज, सरासरी कमाल {tmax_text}°C. जमिनीतील ओलाव्यावर किंवा सिंचनावर पेरा.",
                "te-IN": f"{season} విత్తనానికి వాతావరణం అనుకూలం: {rain_val:.1f} మి.మీ వర్షం, సగటు గరిష్ఠ {tmax_text}°C.",
                "kn-IN": f"{season} ಬಿತ್ತನೆಗೆ ಹವಾಮಾನ ಸೂಕ್ತ: {rain_val:.1f} ಮಿ.ಮೀ ಮಳೆ, ಸರಾಸರಿ ಗರಿಷ್ಠ {tmax_text}°C.",
            }
            w_remedy = None
        else:
            wea_reasons = {
                "en-IN": f"Heavy rain forecast ({rain_val:.1f} mm). Wait for the field to drain before sowing.",
                "hi-IN": f"भारी वर्षा का अनुमान ({rain_val:.1f} मिमी)। बुवाई से पहले खेत सूखने दें।",
                "mr-IN": f"जोरदार पावसाचा अंदाज ({rain_val:.1f} मिमी). पेरणीपूर्वी शेतातील पाणी निचरू द्या.",
                "te-IN": f"భారీ వర్ష సూచన ({rain_val:.1f} మి.మీ). పొలం ఆరిన తర్వాత విత్తండి.",
                "kn-IN": f"ಭಾರೀ ಮಳೆ ಮುನ್ಸೂಚನೆ ({rain_val:.1f} ಮಿ.ಮೀ). ಹೊಲ ಒಣಗಿದ ನಂತರ ಬಿತ್ತಿ.",
            }
            w_remedy = REMEDIES["heavy_rain"][lang]
    elif rain_val >= 25.0:
        w_status = "optimal"
        w_remedy = None
        wea_reasons = {
            "en-IN": f"Good rain expected ({rain_val:.1f} mm this week), enough moisture for the seed to sprout.",
            "hi-IN": f"अनुकूल मौसम पूर्वानुमान। 7 दिनों में {rain_val:.1f} मिमी वर्षा बीज अंकुरण के लिए पर्याप्त नमी देगी।",
            "mr-IN": f"अनुकूल हवामान अंदाज. पुढील ७ दिवसांतील {rain_val:.1f} मिमी पाऊस बियाण्यांच्या उगवणीसाठी उत्तम ओलावा देईल.",
            "te-IN": f"అనుకూల వాతావరణ సూచన. రాబోయే వర్షపాతం ({rain_val:.1f} మి.మీ) మొలకల రాకకు తగిన తేమను అందిస్తుంది.",
            "kn-IN": f"ಅನುಕೂಲಕರ ಹವಾಮಾನ ಮುನ್ಸೂಚನೆ. ಮುಂಬರುವ ಮಳೆ ({rain_val:.1f} ಮಿ.ಮೀ) ಮೊಳಕೆಯೊಡೆಯಲು ಅಗತ್ಯ ತೇವಾಂಶ ನೀಡುತ್ತದೆ.",
        }
    elif rain_val >= 10.0:
        w_status = "compatible"
        w_remedy = None
        wea_reasons = {
            "en-IN": f"Some rain expected ({rain_val:.1f} mm). Sow after the first good soaking rain.",
            "hi-IN": f"मध्यम वर्षा ({rain_val:.1f} मिमी)। पहली अच्छी बारिश के बाद बुवाई के लिए तैयार रहें।",
            "mr-IN": f"मध्यम पाऊस अंदाज ({rain_val:.1f} मिमी). पहिल्या चांगल्या पावसानंतर वाफसा झाल्यावर पेरणी करावी.",
            "te-IN": f"మితమైన వర్షపాతం ({rain_val:.1f} మి.మీ). తగిన తేమ చూసుకుని విత్తనం వేయండి.",
            "kn-IN": f"ಮಧ್ಯಮ ಮಳೆ ಮುನ್ಸೂಚನೆ ({rain_val:.1f} ಮಿ.ಮೀ). ಉತ್ತಮ ತೇವಾಂಶ ಖಚಿತಪಡಿಸಿಕೊಂಡು ಬಿತ್ತನೆ ಮಾಡಿ.",
        }
    else:
        w_status = "constrained"
        w_remedy = REMEDIES["dry"][lang]
        wea_reasons = {
            "en-IN": f"Dry week ahead ({rain_val:.1f} mm). Wait for rain, or water the field before sowing.",
            "hi-IN": f"शुष्क मौसम ({rain_val:.1f} मिमी)। बुवाई कुछ दिन टालें या पूर्व-सिंचाई की व्यवस्था करें।",
            "mr-IN": f"कोरडे हवामान ({rain_val:.1f} मिमी). पाऊस येईपर्यंत धूळवाफेवर पेरणी टाळावी किंवा संरक्षित सिंचन द्यावे.",
            "te-IN": f"పొడి వాతావరణం. వర్షం పడేవరకు విత్తనాలు వేయడం వాయిదా వేయండి.",
            "kn-IN": f"ಒಣ ಹವಾಮಾನ. ಮಳೆ ಬರುವವರೆಗೆ ಬಿತ್ತನೆ ಮುಂದೂಡಿ.",
        }
    factors.append(
        CropDecisionFactor(
            factor_id="weather",
            factor_name={"en-IN": "This week's weather", "hi-IN": "मौसम एवं वर्षा पूर्वानुमान", "mr-IN": "हवामान व पाऊस अंदाज", "te-IN": "వాతావరణం మరియు వర్ష సూచన", "kn-IN": "ಹವಾಮಾನ ಮತ್ತು ಮಳೆ ಮುನ್ಸೂಚನೆ"}[lang],
            status=w_status,
            data_used=weather_data,
            reasoning=wea_reasons[lang],
            remedy=w_remedy,
        )
    )

    # Factor 5: Crop Rotation & Soil Diversity
    if previous and previous == policy.crop:
        rot_status = "rejected"
        rot_data = f"Previous Crop: {previous.title()} | Proposed: {policy.crop.title()}"
        rot_reasons = {
            "en-IN": f"Same crop as last time. Growing {previous.replace('_', ' ')} again builds up pests and diseases and drains the same nutrients.",
            "hi-IN": f"लगातार एक ही फसल का नुकसान। {previous.title()} दोबारा लगाने से कीट-रोग बढ़ते हैं और पोषक तत्व घटते हैं।",
            "mr-IN": f"सलग तेच पीक घेण्याचा तोटा. {previous.title()} पुन्हा लावल्याने किडी-रोगांचा प्रादुर्भाव वाढतो व जमिनीचा कस घटतो.",
            "te-IN": f"ఒకే పంటను పునరావృతం చేయడం వల్ల తెగుళ్లు పెరిగి నేల సారం తగ్గుతుంది.",
            "kn-IN": f"ಅದೇ ಬೆಳೆಯನ್ನು ಪುನರಾವರ್ತಿಸುವುದರಿಂದ ಕೀಟಬಾಧೆ ಹೆಚ್ಚಾಗುತ್ತದೆ ಮತ್ತು ಮಣ್ಣಿನ ಫಲವತ್ತತೆ ಕಡಿಮೆಯಾಗುತ್ತದೆ.",
        }
    elif previous:
        rot_status = "optimal"
        rot_data = f"Previous Crop: {previous.title()} | Proposed: {policy.crop.title()}"
        rot_reasons = {
            "en-IN": f"Good change from {previous.replace('_', ' ')}. Switching crops breaks the pest and disease cycle and rests the soil.",
            "hi-IN": f"उत्कृष्ट फसल चक्र। {previous.title()} के बाद यह फसल लगाने से कीट चक्र टूटता है और मिट्टी की उर्वरता बढ़ती है।",
            "mr-IN": f"उत्तम पीक फेरपालट. {previous.title()} नंतर हे पीक घेतल्याने कीड-रोगांचे चक्र खंडित होते व जमिनीची सुपीकता वाढते.",
            "te-IN": f"మంచి పంట మార్పిడి. మునుపటి పంట తర్వాత ఇది వేయడం వల్ల తెగుళ్లు నివారింపబడి నేల సారవంతమవుతుంది.",
            "kn-IN": f"ಉತ್ತಮ ಬೆಳೆ ಪರಿವರ್ತನೆ. ಕೀಟಬಾಧೆ ತಡೆಯಲು ಮತ್ತು ಮಣ್ಣಿನ ಫಲವತ್ತತೆ ಕಾಪಾಡಲು ಸಹಕಾರಿ.",
        }
    else:
        rot_status = "compatible"
        rot_data = "Previous Crop: Not specified"
        rot_reasons = {
            "en-IN": "You did not enter a previous crop, so rotation was not checked.",
            "hi-IN": "नए खेत का नियोजन। किसी पिछले कीट या रोग का सीधा प्रभाव नहीं है।",
            "mr-IN": "नवीन पीक नियोजन. मागील पिकाचा कोणताही कीड प्रादुर्भाव नोंदवलेला नाही.",
            "te-IN": "తాజా పొలం ప్రణాళిక.",
            "kn-IN": "ಹೊಸ ಜಮೀನಿನ ಬೆಳೆ ಯೋಜನೆ.",
        }
    factors.append(
        CropDecisionFactor(
            factor_id="rotation",
            factor_name={"en-IN": "Last crop", "hi-IN": "फसल चक्र एवं कीट चक्र", "mr-IN": "पीक फेरपालट व कीड नियंत्रण", "te-IN": "పంట మార్పిడి మరియు తెగుళ్ల నియంత్రణ", "kn-IN": "ಬೆಳೆ ಪರಿವರ್ತನೆ ಮತ್ತು ಕೀಟ ನಿಯಂತ್ರಣ"}[lang],
            status=rot_status,
            data_used=rot_data,
            reasoning=rot_reasons[lang],
            remedy=REMEDIES["rotation"][lang] if rot_status == "rejected" else None,
        )
    )

    # Factor 6: Regional Agro-Climatic Fit
    reg_status = "optimal" if (district_profile and policy.crop in district_profile.primary_crops) else "compatible"
    dist_name = farm.district or "Regional Pack"
    reg_data = f"District: {dist_name}" + (f" | Zone: {district_profile.agro_climatic_zone}" if district_profile else "")
    if district_profile and policy.crop in district_profile.primary_crops:
        reg_reasons = {
            "en-IN": f"One of the main crops grown in {dist_name}.",
            "hi-IN": f"{dist_name} जिले की मुख्य फसलों में से एक।",
            "mr-IN": f"{dist_name} जिल्ह्यातील मुख्य पिकांपैकी एक.",
            "te-IN": f"{dist_name} జిల్లాలో ప్రధాన పంటల్లో ఒకటి.",
            "kn-IN": f"{dist_name} ಜಿಲ್ಲೆಯ ಪ್ರಮುಖ ಬೆಳೆಗಳಲ್ಲಿ ಒಂದು.",
        }
    else:
        reg_reasons = {
            "en-IN": f"Grown in {farm.state_name}, though not one of {dist_name}'s main crops.",
            "hi-IN": f"{farm.state_name} में उगाई जाती है, पर {dist_name} की मुख्य फसल नहीं।",
            "mr-IN": f"{farm.state_name} मध्ये घेतले जाते, पण {dist_name} चे मुख्य पीक नाही.",
            "te-IN": f"{farm.state_name}లో పండిస్తారు, కానీ {dist_name} ప్రధాన పంట కాదు.",
            "kn-IN": f"{farm.state_name} ನಲ್ಲಿ ಬೆಳೆಯುತ್ತಾರೆ, ಆದರೆ {dist_name} ನ ಪ್ರಮುಖ ಬೆಳೆ ಅಲ್ಲ.",
        }
    factors.append(
        CropDecisionFactor(
            factor_id="regional_fit",
            factor_name={"en-IN": "Grown in your district", "hi-IN": "क्षेत्रीय कृषि-जलवायु अनुकूलता", "mr-IN": "प्रादेशिक कृषी-हवामान अनुकूलता", "te-IN": "ప్రాంతీయ వ్యవసాయ-వాతావరణం", "kn-IN": "ಪ್ರಾದೇಶಿಕ ಕೃಷಿ-ಹವಾಮಾನ ಸೂಕ್ತತೆ"}[lang],
            status=reg_status,
            data_used=reg_data,
            reasoning=reg_reasons[lang],
            remedy=None,
        )
    )

    # Factor 7: Regenerative Practices
    practice_names = [
        PRACTICE_LOCALIZED_NAMES.get(pid, {}).get(lang, pid.replace("-", " ").title())
        for pid in policy.practice_ids
    ]
    prac_data = ", ".join(practice_names)
    prac_reasons = {
        "en-IN": f"Good practices for this crop: {prac_data}. They help keep moisture in the soil and cut input costs.",
        "hi-IN": f"अनुशंसित पुनर्योजी पद्धतियां: {prac_data}। मिट्टी की नमी संचित रखती हैं और खाद-कीटनाशक खर्च घटाती हैं।",
        "mr-IN": f"शिफारस केलेल्या शाश्वत पद्धती: {prac_data}. जमिनीतील ओलावा टिकवून ठेवतात आणि रासायनिक खतांचा खर्च कमी करतात.",
        "te-IN": f"సిఫార్సు చేయబడిన పద్ధతులు: {prac_data}. నేల తేమను కాపాడుతుంది.",
        "kn-IN": f"ಶಿಫಾರಸು ಮಾಡಿದ ಸುಸ್ಥಿರ ಪದ್ಧತಿಗಳು: {prac_data}. ಮಣ್ಣಿನ ತೇವಾಂಶ ಕಾಪಾಡುತ್ತದೆ.",
    }
    factors.append(
        CropDecisionFactor(
            factor_id="regenerative_practice",
            factor_name={"en-IN": "Good practices", "hi-IN": "पुनर्योजी कृषि पद्धतियां", "mr-IN": "शाश्वत सेंद्रिय कृषी पद्धती", "te-IN": "పునరుత్పాదక పద్ధతులు", "kn-IN": "ಸುಸ್ಥಿರ ಕೃಷಿ ಪದ್ಧತಿಗಳು"}[lang],
            status="optimal",
            data_used=prac_data,
            reasoning=prac_reasons[lang],
            remedy=None,
        )
    )

    return factors


def _sources_used(farm: Farm, soil: SoilTest | None, evidence: list[dict[str, Any]], district_profile: Any) -> list[dict[str, str]]:
    """Describe the data actually behind this result, not a fixed list."""
    sources: list[dict[str, str]] = []
    weather = latest_weather_snapshot(evidence)
    if weather:
        name = {"open_meteo": "Open-Meteo forecast (coordinate based)", "imd": "IMD district forecast"}.get(weather.get("provider", ""), str(weather.get("provider")))
        sources.append({"name": name, "type": "7-day rain and temperature forecast", "status": f"Fetched {str(weather.get('fetched_at', ''))[:16].replace('T', ' ')} UTC"})
    else:
        sources.append({"name": "Weather forecast", "type": "7-day rain and temperature forecast", "status": "Not available"})
    satellite = next((snap for snap in evidence if snap.get("kind") == "satellite_observation" and snap.get("mode") != "missing"), None)
    if satellite:
        sources.append({"name": "Sentinel-2 via Google Earth Engine", "type": "Crop vigour and moisture indices", "status": "Observed"})
    if soil:
        sources.append({"name": "Soil Health Card" if soil.source == "soil_card_confirmed" else "Soil test entered by farmer", "type": f"pH {soil.values.ph if soil.values.ph is not None else 'n/a'}", "status": "Farmer confirmed"})
    else:
        ph, ph_source = soil_ph(None, district_profile)
        sources.append({"name": "Soil type from farm profile", "type": f"{farm.soil_type.title()} soil, pH {ph if ph is not None else 'unknown'} ({ph_source})", "status": "Baseline, not lab tested"})
    if district_profile:
        sources.append({"name": "District agro-climatic profile", "type": f"{district_profile.district}: {district_profile.normal_rainfall_mm:.0f} mm normal rainfall, major crops", "status": "Reference data"})
    else:
        sources.append({"name": "District agro-climatic profile", "type": f"No profile for {farm.district}", "status": "Not available"})
    return sources


def generate_crop_recommendations(
    farm: Farm,
    soil: SoilTest | None,
    season: str | None,
    evidence: list[dict[str, Any]],
    locale: str = "en-IN",
) -> CropRecommendationResult:
    """Score every crop on season, water, soil, weather (rain + temperature) and rotation,
    with a factor-by-factor explanation in the farmer's language."""
    season = season or current_season()
    rain_7d = rainfall_total(evidence)
    mean_tmax = forecast_mean(evidence, "temp_max")
    district_profile = get_district_profile(farm.district)
    norm_previous = normalize_crop(farm.previous_crop or "")
    farm_water_rank = WATER_RANK.get(farm.water_access, 1)
    lang = locale if locale in {"en-IN", "hi-IN", "mr-IN", "te-IN", "kn-IN"} else "en-IN"

    eligible_options: list[CropPracticeOption] = []
    unsuitable_options: list[CropPracticeOption] = []

    for policy in CROP_POLICIES:
        rejections: list[str] = []
        dimensions: list[ScoreDimension] = []

        in_season = season in policy.seasons
        if not in_season:
            rejections.append(f"Outside configured {season} planting window")
        dimensions.append(ScoreDimension(name="season_fit", score=1.0 if in_season else 0.0, explanation="Crop-season eligibility"))

        need = effective_water_need(policy, season, district_profile)
        if farm_water_rank < need:
            rejections.append(f"Water access {farm.water_access} below crop demand Level {need} in {season}")
        dimensions.append(ScoreDimension(name="water_fit", score=min(1.0, farm_water_rank / need), explanation=f"Water access vs crop demand in {season}"))

        if farm.soil_type not in policy.soil_types:
            soil_score = 0.0
            rejections.append(f"Soil {farm.soil_type} outside crop tolerance")
        elif farm.soil_type == "unknown":
            soil_score = 0.5
        else:
            soil_score = 1.0
        ph, ph_source = soil_ph(soil, district_profile)
        if ph is not None and not policy.ph_range[0] <= ph <= policy.ph_range[1]:
            soil_score = max(0.0, soil_score - 0.3)
            # Only a measured pH rules a crop out; a district average only lowers the score.
            if ph_source == "soil card":
                rejections.append(f"pH {ph:.1f} outside optimal range {policy.ph_range[0]}–{policy.ph_range[1]}")
        dimensions.append(ScoreDimension(name="soil_fit", score=soil_score, explanation=f"Soil type and pH ({ph_source})"))

        dimensions.append(ScoreDimension(name="weather_forecast", score=rain_fit_score(policy, season, rain_7d), explanation=f"7-day rain judged for {season} sowing"))
        dimensions.append(ScoreDimension(name="temperature_fit", score=temperature_fit_score(policy, mean_tmax), explanation=f"Forecast avg max temperature vs {policy.sowing_tmax_max:.0f}°C sowing limit"))

        if norm_previous and norm_previous == policy.crop:
            rejections.append("Repeating identical previous crop risks monoculture disease buildup")
            rotation_score = 0.0
        elif norm_previous:
            rotation_score = 1.0
        else:
            rotation_score = 0.6
        dimensions.append(ScoreDimension(name="rotation_diversity", score=rotation_score, explanation="Rotation diversity"))

        regional = 1.0 if district_profile and policy.crop in district_profile.primary_crops else 0.7
        dimensions.append(ScoreDimension(name="regional_fit", score=regional, explanation="Major crop of the district"))

        factors = _build_factor_breakdowns(
            policy=policy, farm=farm, soil=soil, season=season, rainfall_7d=rain_7d,
            previous=norm_previous, locale=locale, district_profile=district_profile, mean_tmax=mean_tmax,
        )

        scored = [item.score for item in dimensions if item.score is not None]
        option = CropPracticeOption(
            crop=policy.crop,
            crop_name=CROP_LOCALIZED_NAMES.get(policy.crop, {}).get(lang, policy.crop.replace("_", " ").title()),
            practice_ids=list(policy.practice_ids),
            eligible=not rejections,
            rejection_reasons=rejections,
            dimensions=dimensions,
            evidence_coverage=len(scored) / len(dimensions),
            rank_score=round(sum(scored) / len(scored), 3) if scored and not rejections else None,
            factors=factors,
        )
        (eligible_options if option.eligible else unsuitable_options).append(option)

    eligible_options.sort(key=lambda item: item.rank_score or 0.0, reverse=True)

    reg_notes = district_profile.agronomic_notes if district_profile else f"No district profile for {farm.district}; state-level rules applied for {farm.state_name}."

    return CropRecommendationResult(
        farm_id=farm.id,
        farm_name=farm.name,
        district=farm.district,
        state_name=farm.state_name,
        season=season,
        suggested_season=current_season(),
        locale=locale,
        water_access=farm.water_access,
        soil_type=farm.soil_type,
        previous_crop=farm.previous_crop,
        rainfall_7d_forecast_mm=rain_7d,
        mean_max_temp_7d_c=mean_tmax,
        data_sources_used=_sources_used(farm, soil, evidence, district_profile),
        recommendations=eligible_options,
        unsuitable_crops=unsuitable_options,
        regional_notes=reg_notes,
    )
