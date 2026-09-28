#!/usr/bin/env python3
"""Build data/crops/global_crop_catalog.json from the FAO EcoCrop database.

Source: FAO EcoCrop (https://gaez.fao.org/pages/ecocrop), distributed as EcoCrop_DB.csv in
https://github.com/OpenCLIM/ecocrop (Open Government Licence v3.0).

The EcoCrop parameters (temperature, rainfall, pH, texture, drainage, salinity, killing
temperature, crop cycle) are copied verbatim. Local names, a typical crop duration used for
seasonal water budgeting, and regenerative traits are curated in CURATED below.

Usage:
    python3 services/api/scripts/build_crop_catalog.py --ecocrop /path/to/EcoCrop_DB.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "data" / "crops" / "global_crop_catalog.json"

# group: cereal | millet | pulse | oilseed | fibre | sugar | tuber | vegetable | fodder | green_manure
# water_class: low | medium | high (seasonal irrigation demand relative to other field crops)
# residue: low | medium | high (surface cover / biomass returned after harvest)
CURATED: dict[str, dict] = {
    "wheat": {"sci": "Triticum aestivum", "group": "cereal", "cycle_days": 130, "water_class": "medium", "n_fixing": False, "residue": "high",
              "names": {"en": "Wheat", "hi": "गेहूँ", "mr": "गहू", "te": "గోధుమ", "kn": "ಗೋಧಿ", "pt": "Trigo", "ru": "Пшеница", "zh": "小麦"},
              "aliases": ["gahu", "gehu", "gehun", "kanak"], "practices": ["reduced-disturbance", "residue-retention", "rainfall-timed-sowing"]},
    "rice": {"sci": "Oryza sativa", "group": "cereal", "cycle_days": 120, "water_class": "high", "n_fixing": False, "residue": "high",
             "names": {"en": "Rice (Paddy)", "hi": "धान", "mr": "भात", "te": "వరి", "kn": "ಭತ್ತ", "pt": "Arroz", "ru": "Рис", "zh": "水稻"},
             "aliases": ["paddy", "dhan", "bhat", "chawal"], "practices": ["direct-seeded-rice", "alternate-wetting-drying", "green-manure", "residue-retention"]},
    "maize": {"sci": "Zea mays", "group": "cereal", "cycle_days": 110, "water_class": "medium", "n_fixing": False, "residue": "high",
              "names": {"en": "Maize", "hi": "मक्का", "mr": "मका", "te": "మొక్కజొన్న", "kn": "ಮೆಕ್ಕೆಜೋಳ", "pt": "Milho", "ru": "Кукуруза", "zh": "玉米"},
              "aliases": ["corn", "maka", "makka", "makai", "bhutta"], "practices": ["legume-rotation", "intercropping-pulses", "residue-retention", "field-scouting"]},
    "sorghum": {"sci": "Sorghum bicolor", "group": "millet", "cycle_days": 110, "water_class": "low", "n_fixing": False, "residue": "high",
                "names": {"en": "Sorghum (Jowar)", "hi": "ज्वार", "mr": "ज्वारी", "te": "జొన్న", "kn": "ಜೋಳ", "pt": "Sorgo", "ru": "Сорго", "zh": "高粱"},
                "aliases": ["jowar", "jwari", "jola"], "practices": ["intercropping-pulses", "residue-retention", "rainfall-timed-sowing"]},
    "pearl_millet": {"sci": "Pennisetum glaucum", "group": "millet", "cycle_days": 85, "water_class": "low", "n_fixing": False, "residue": "medium",
                     "names": {"en": "Pearl Millet (Bajra)", "hi": "बाजरा", "mr": "बाजरी", "te": "సజ్జ", "kn": "ಸಜ್ಜೆ", "pt": "Milheto", "ru": "Жемчужное просо", "zh": "珍珠粟"},
                     "aliases": ["bajra", "bajri", "millet", "sajje"], "practices": ["intercropping-pulses", "residue-retention", "rainfall-timed-sowing"]},
    "finger_millet": {"sci": "Eleusine coracana ssp. coracana", "group": "millet", "cycle_days": 110, "water_class": "low", "n_fixing": False, "residue": "medium",
                      "names": {"en": "Finger Millet (Ragi)", "hi": "रागी", "mr": "नाचणी", "te": "రాగి", "kn": "ರಾಗಿ", "pt": "Painço-de-dedo", "ru": "Дагусса", "zh": "龙爪稷"},
                      "aliases": ["ragi", "nachni", "nagli", "mandua"], "practices": ["intercropping-pulses", "compost-fym", "rainfall-timed-sowing"]},
    "foxtail_millet": {"sci": "Setaria italica", "group": "millet", "cycle_days": 90, "water_class": "low", "n_fixing": False, "residue": "medium",
                       "names": {"en": "Foxtail Millet", "hi": "कंगनी", "mr": "राळा", "te": "కొర్ర", "kn": "ನವಣೆ", "pt": "Painço-italiano", "ru": "Чумиза", "zh": "谷子"},
                       "aliases": ["kangni", "rala", "korra", "navane"], "practices": ["intercropping-pulses", "rainfall-timed-sowing"]},
    "barley": {"sci": "Hordeum vulgare", "group": "cereal", "cycle_days": 120, "water_class": "low", "n_fixing": False, "residue": "high",
               "names": {"en": "Barley", "hi": "जौ", "mr": "सातू", "te": "బార్లీ", "kn": "ಬಾರ್ಲಿ", "pt": "Cevada", "ru": "Ячмень", "zh": "大麦"},
               "aliases": ["jau", "jav", "satu"], "practices": ["reduced-disturbance", "residue-retention"]},
    "oats": {"sci": "Avena sativa", "group": "fodder", "cycle_days": 120, "water_class": "medium", "n_fixing": False, "residue": "high",
             "names": {"en": "Oats", "hi": "जई", "mr": "ओट", "te": "ఓట్స్", "kn": "ಓಟ್ಸ್", "pt": "Aveia", "ru": "Овёс", "zh": "燕麦"},
             "aliases": ["jai", "oat"], "practices": ["residue-retention", "reduced-disturbance"]},
    "teff": {"sci": "Eragrostis tef", "group": "cereal", "cycle_days": 100, "water_class": "low", "n_fixing": False, "residue": "medium",
             "names": {"en": "Teff", "hi": "टेफ", "mr": "टेफ", "te": "టెఫ్", "kn": "ಟೆಫ್", "pt": "Teff", "ru": "Тэфф", "zh": "苔麸"},
             "aliases": ["tef"], "practices": ["reduced-disturbance", "rainfall-timed-sowing"]},
    "chickpea": {"sci": "Cicer arietinum", "group": "pulse", "cycle_days": 110, "water_class": "low", "n_fixing": True, "residue": "low",
                 "names": {"en": "Chickpea (Gram)", "hi": "चना", "mr": "हरभरा", "te": "శనగ", "kn": "ಕಡಲೆ", "pt": "Grão-de-bico", "ru": "Нут", "zh": "鹰嘴豆"},
                 "aliases": ["gram", "chana", "harbara", "bengal_gram"], "practices": ["rhizobium-inoculation", "reduced-disturbance", "field-scouting"]},
    "pigeon_pea": {"sci": "Cajanus cajan", "group": "pulse", "cycle_days": 170, "water_class": "low", "n_fixing": True, "residue": "high",
                   "names": {"en": "Pigeon Pea (Tur/Arhar)", "hi": "अरहर", "mr": "तूर", "te": "కంది", "kn": "ತೊಗರಿ", "pt": "Feijão-guandu", "ru": "Каянус", "zh": "木豆"},
                   "aliases": ["tur", "toor", "arhar", "pigeonpea", "togari", "kandi"], "practices": ["intercropping-pulses", "rhizobium-inoculation", "broad-bed-furrow"]},
    "green_gram": {"sci": "Vigna radiata", "group": "pulse", "cycle_days": 70, "water_class": "low", "n_fixing": True, "residue": "medium",
                   "names": {"en": "Green Gram (Moong)", "hi": "मूंग", "mr": "मूग", "te": "పెసర", "kn": "ಹೆಸರು", "pt": "Feijão-mungo", "ru": "Маш", "zh": "绿豆"},
                   "aliases": ["moong", "mung", "mug", "mungbean", "pesara"], "practices": ["rhizobium-inoculation", "legume-rotation", "residue-retention"]},
    "black_gram": {"sci": "Vigna mungo", "group": "pulse", "cycle_days": 80, "water_class": "low", "n_fixing": True, "residue": "medium",
                   "names": {"en": "Black Gram (Urad)", "hi": "उड़द", "mr": "उडीद", "te": "మినుము", "kn": "ಉದ್ದು", "pt": "Feijão-urd", "ru": "Урд", "zh": "黑吉豆"},
                   "aliases": ["urad", "udid", "urd", "minumu"], "practices": ["rhizobium-inoculation", "legume-rotation"]},
    "lentil": {"sci": "Lens culinaris", "group": "pulse", "cycle_days": 115, "water_class": "low", "n_fixing": True, "residue": "low",
               "names": {"en": "Lentil (Masoor)", "hi": "मसूर", "mr": "मसूर", "te": "మసూర్", "kn": "ಮಸೂರ್", "pt": "Lentilha", "ru": "Чечевица", "zh": "小扁豆"},
               "aliases": ["masoor", "masur"], "practices": ["rhizobium-inoculation", "reduced-disturbance"]},
    "dry_bean": {"sci": "Phaseolus vulgaris", "group": "pulse", "cycle_days": 95, "water_class": "medium", "n_fixing": True, "residue": "low",
                 "names": {"en": "Common Bean (Rajma)", "hi": "राजमा", "mr": "राजमा", "te": "రాజ్మా", "kn": "ರಾಜ್ಮಾ", "pt": "Feijão", "ru": "Фасоль", "zh": "菜豆"},
                 "aliases": ["rajma", "kidney_bean", "bean", "feijao"], "practices": ["rhizobium-inoculation", "legume-rotation"]},
    "cowpea": {"sci": "Vigna unguiculata", "group": "pulse", "cycle_days": 80, "water_class": "low", "n_fixing": True, "residue": "medium",
               "names": {"en": "Cowpea", "hi": "लोबिया", "mr": "चवळी", "te": "అలసంద", "kn": "ಅಲಸಂದೆ", "pt": "Feijão-caupi", "ru": "Вигна", "zh": "豇豆"},
               "aliases": ["lobia", "chavali", "chawli", "alasande"], "practices": ["rhizobium-inoculation", "legume-rotation", "residue-retention"]},
    "field_pea": {"sci": "Pisum sativum", "group": "pulse", "cycle_days": 100, "water_class": "low", "n_fixing": True, "residue": "low",
                  "names": {"en": "Field Pea (Matar)", "hi": "मटर", "mr": "वाटाणा", "te": "బఠాణీ", "kn": "ಬಟಾಣಿ", "pt": "Ervilha", "ru": "Горох", "zh": "豌豆"},
                  "aliases": ["pea", "matar", "vatana"], "practices": ["rhizobium-inoculation", "reduced-disturbance"]},
    "cluster_bean": {"sci": "Cyamopsis tetragonoloba", "group": "pulse", "cycle_days": 100, "water_class": "low", "n_fixing": True, "residue": "medium",
                     "names": {"en": "Cluster Bean (Guar)", "hi": "ग्वार", "mr": "गवार", "te": "గోరుచిక్కుడు", "kn": "ಗೋರಿಕಾಯಿ", "pt": "Guar", "ru": "Гуар", "zh": "瓜尔豆"},
                     "aliases": ["guar", "gavar"], "practices": ["rhizobium-inoculation", "legume-rotation"]},
    "soybean": {"sci": "Glycine max", "group": "oilseed", "cycle_days": 100, "water_class": "medium", "n_fixing": True, "residue": "medium",
                "names": {"en": "Soybean", "hi": "सोयाबीन", "mr": "सोयाबीन", "te": "సోయాబీన్", "kn": "ಸೋಯಾಬೀನ್", "pt": "Soja", "ru": "Соя", "zh": "大豆"},
                "aliases": ["soyabean", "soya", "soja"], "practices": ["broad-bed-furrow", "rhizobium-inoculation", "intercropping-pulses"]},
    "groundnut": {"sci": "Arachis hypogaea", "group": "oilseed", "cycle_days": 115, "water_class": "medium", "n_fixing": True, "residue": "medium",
                  "names": {"en": "Groundnut", "hi": "मूंगफली", "mr": "भुईमूग", "te": "వేరుశనగ", "kn": "ಕಡಲೆಕಾಯಿ", "pt": "Amendoim", "ru": "Арахис", "zh": "花生"},
                  "aliases": ["peanut", "bhuimug", "mungfali", "moongphali"], "practices": ["rhizobium-inoculation", "residue-retention", "drainage-check"]},
    "mustard": {"sci": "Brassica juncea", "group": "oilseed", "cycle_days": 125, "water_class": "low", "n_fixing": False, "residue": "medium",
                "names": {"en": "Indian Mustard (Rai)", "hi": "सरसों", "mr": "मोहरी", "te": "ఆవాలు", "kn": "ಸಾಸಿವೆ", "pt": "Mostarda", "ru": "Горчица сарептская", "zh": "芥菜型油菜"},
                "aliases": ["sarson", "rai", "raya", "mohri"], "practices": ["reduced-disturbance", "field-scouting"]},
    "rapeseed_canola": {"sci": "Brassica napus", "group": "oilseed", "cycle_days": 150, "water_class": "medium", "n_fixing": False, "residue": "medium",
                        "names": {"en": "Rapeseed / Canola", "hi": "गोभी सरसों", "mr": "कॅनोला", "te": "కనోలా", "kn": "ಕ್ಯಾನೋಲಾ", "pt": "Canola", "ru": "Рапс", "zh": "甘蓝型油菜"},
                        "aliases": ["canola", "rapeseed", "gobhi_sarson"], "practices": ["reduced-disturbance", "residue-retention"]},
    "sunflower": {"sci": "Helianthus annuus", "group": "oilseed", "cycle_days": 100, "water_class": "medium", "n_fixing": False, "residue": "medium",
                  "names": {"en": "Sunflower", "hi": "सूरजमुखी", "mr": "सूर्यफूल", "te": "పొద్దుతిరుగుడు", "kn": "ಸೂರ್ಯಕಾಂತಿ", "pt": "Girassol", "ru": "Подсолнечник", "zh": "向日葵"},
                  "aliases": ["surajmukhi", "suryaphool"], "practices": ["legume-rotation", "residue-retention"]},
    "sesame": {"sci": "Sesamum indicum", "group": "oilseed", "cycle_days": 90, "water_class": "low", "n_fixing": False, "residue": "low",
               "names": {"en": "Sesame (Til)", "hi": "तिल", "mr": "तीळ", "te": "నువ్వులు", "kn": "ಎಳ್ಳು", "pt": "Gergelim", "ru": "Кунжут", "zh": "芝麻"},
               "aliases": ["til", "teel", "gingelly"], "practices": ["intercropping-pulses", "drainage-check"]},
    "safflower": {"sci": "Carthamus tinctorius", "group": "oilseed", "cycle_days": 130, "water_class": "low", "n_fixing": False, "residue": "medium",
                  "names": {"en": "Safflower", "hi": "कुसुम", "mr": "करडई", "te": "కుసుమ", "kn": "ಕುಸುಬೆ", "pt": "Cártamo", "ru": "Сафлор", "zh": "红花"},
                  "aliases": ["kardai", "kusum"], "practices": ["reduced-disturbance", "rainfall-timed-sowing"]},
    "cotton": {"sci": "Gossypium hirsutum", "group": "fibre", "cycle_days": 170, "water_class": "medium", "n_fixing": False, "residue": "medium",
               "names": {"en": "Cotton", "hi": "कपास", "mr": "कापूस", "te": "పత్తి", "kn": "ಹತ್ತಿ", "pt": "Algodão", "ru": "Хлопчатник", "zh": "棉花"},
               "aliases": ["kapas", "kapus", "narma"], "practices": ["intercropping-pulses", "field-scouting", "broad-bed-furrow"]},
    "sugarcane": {"sci": "Saccharum officinarum", "group": "sugar", "cycle_days": 330, "water_class": "high", "n_fixing": False, "residue": "high",
                  "names": {"en": "Sugarcane", "hi": "गन्ना", "mr": "ऊस", "te": "చెరకు", "kn": "ಕಬ್ಬು", "pt": "Cana-de-açúcar", "ru": "Сахарный тростник", "zh": "甘蔗"},
                  "aliases": ["oos", "us", "ganna", "ikh", "kabbu"], "practices": ["trash-mulching", "drip-irrigation", "intercropping-pulses"]},
    "potato": {"sci": "Solanum tuberosum", "group": "tuber", "cycle_days": 100, "water_class": "medium", "n_fixing": False, "residue": "low",
               "names": {"en": "Potato", "hi": "आलू", "mr": "बटाटा", "te": "బంగాళదుంప", "kn": "ಆಲೂಗಡ್ಡೆ", "pt": "Batata", "ru": "Картофель", "zh": "马铃薯"},
               "aliases": ["aloo", "alu", "batata"], "practices": ["compost-fym", "field-scouting", "drip-irrigation"]},
    "cassava": {"sci": "Manihot esculenta", "group": "tuber", "cycle_days": 300, "water_class": "low", "n_fixing": False, "residue": "medium",
                "names": {"en": "Cassava (Tapioca)", "hi": "कसावा", "mr": "कसावा", "te": "కర్రపెండలం", "kn": "ಮರಗೆಣಸು", "pt": "Mandioca", "ru": "Маниок", "zh": "木薯"},
                "aliases": ["tapioca", "mandioca", "manioc"], "practices": ["intercropping-pulses", "residue-retention"]},
    "sweet_potato": {"sci": "Ipomoea batatas", "group": "tuber", "cycle_days": 120, "water_class": "low", "n_fixing": False, "residue": "medium",
                     "names": {"en": "Sweet Potato", "hi": "शकरकंद", "mr": "रताळे", "te": "చిలగడదుంప", "kn": "ಸಿಹಿ ಗೆಣಸು", "pt": "Batata-doce", "ru": "Батат", "zh": "甘薯"},
                     "aliases": ["shakarkand", "ratale"], "practices": ["compost-fym", "residue-retention"]},
    "onion": {"sci": "Allium cepa", "group": "vegetable", "cycle_days": 130, "water_class": "medium", "n_fixing": False, "residue": "low",
              "names": {"en": "Onion", "hi": "प्याज", "mr": "कांदा", "te": "ఉల్లిపాయ", "kn": "ಈರುಳ್ಳಿ", "pt": "Cebola", "ru": "Лук репчатый", "zh": "洋葱"},
              "aliases": ["kanda", "pyaj", "pyaz"], "practices": ["raised-bed-planting", "drip-irrigation", "field-scouting"]},
    "tomato": {"sci": "Lycopersicon esculentum", "group": "vegetable", "cycle_days": 120, "water_class": "medium", "n_fixing": False, "residue": "low",
               "names": {"en": "Tomato", "hi": "टमाटर", "mr": "टोमॅटो", "te": "టమాటా", "kn": "ಟೊಮೆಟೊ", "pt": "Tomate", "ru": "Томат", "zh": "番茄"},
               "aliases": ["tamatar"], "practices": ["raised-bed-planting", "drip-irrigation", "field-scouting"]},
    "berseem": {"sci": "Trifolium alexandrinum", "group": "fodder", "cycle_days": 180, "water_class": "medium", "n_fixing": True, "residue": "medium",
                "names": {"en": "Berseem (Egyptian Clover)", "hi": "बरसीम", "mr": "बरसीम", "te": "బర్సీమ్", "kn": "ಬರ್ಸೀಮ್", "pt": "Trevo-de-alexandria", "ru": "Клевер александрийский", "zh": "埃及三叶草"},
                "aliases": ["egyptian_clover"], "practices": ["legume-rotation", "reduced-disturbance"]},
    "dhaincha": {"sci": "Sesbania bispinosa", "group": "green_manure", "cycle_days": 50, "water_class": "low", "n_fixing": True, "residue": "high",
                 "names": {"en": "Dhaincha (Green Manure)", "hi": "ढैंचा", "mr": "धैंचा", "te": "జీలుగ", "kn": "ಡಯಾಂಚ", "pt": "Sesbânia", "ru": "Сесбания", "zh": "田菁"},
                 "aliases": ["sesbania", "dhaincha"], "practices": ["green-manure"]},
    "sunn_hemp": {"sci": "Crotalaria juncea", "group": "green_manure", "cycle_days": 50, "water_class": "low", "n_fixing": True, "residue": "high",
                  "names": {"en": "Sunn Hemp (Green Manure)", "hi": "सनई", "mr": "ताग", "te": "జనుము", "kn": "ಸೆಣಬು", "pt": "Crotalária", "ru": "Кроталярия", "zh": "菽麻"},
                  "aliases": ["sanai", "sunhemp", "taag"], "practices": ["green-manure"]},
}

NUMERIC = ["TOPMN", "TOPMX", "TMIN", "TMAX", "ROPMN", "ROPMX", "RMIN", "RMAX", "PHOPMN", "PHOPMX", "PHMIN", "PHMAX", "KTMP", "GMIN", "GMAX"]


def _num(value: str) -> float | None:
    value = (value or "").strip()
    if not value or value.upper() == "NA":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _text(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def build(ecocrop_csv: Path) -> dict:
    with ecocrop_csv.open(encoding="latin-1", newline="") as handle:
        rows = {row["ScientificName"].strip(): row for row in csv.DictReader(handle)}
    crops = []
    for crop_id, meta in CURATED.items():
        row = rows.get(meta["sci"])
        if row is None:
            raise SystemExit(f"EcoCrop record not found for {meta['sci']}")
        eco = {key.lower(): _num(row[key]) for key in NUMERIC}
        eco.update({
            "texture_optimal": _text(row.get("TEXT", "")),
            "texture_absolute": _text(row.get("TEXTR", "")),
            "drainage_optimal": row.get("DRA", "").strip() or None,
            "salinity_optimal": row.get("SAL", "").strip() or None,
            "ecoport_code": row.get("EcoPortCode", "").strip() or None,
        })
        crops.append({
            "id": crop_id,
            "scientific_name": meta["sci"],
            "group": meta["group"],
            "names": meta["names"],
            "aliases": meta["aliases"],
            "cycle_days": meta["cycle_days"],
            "traits": {"n_fixing": meta["n_fixing"], "water_class": meta["water_class"], "residue": meta["residue"]},
            "practices": meta["practices"],
            "ecocrop": eco,
        })
    return {
        "version": "1.0.0",
        "sources": [
            {"name": "FAO EcoCrop database", "url": "https://gaez.fao.org/pages/ecocrop",
             "distribution": "https://github.com/OpenCLIM/ecocrop (EcoCrop_DB.csv, Open Government Licence v3.0)",
             "fields": "temperature, rainfall, pH, texture, drainage, salinity, killing temperature, crop cycle"},
            {"name": "KISANAI curation", "fields": "local names, typical duration (cycle_days), water class, N-fixing, residue, practice links"},
        ],
        "crops": crops,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ecocrop", required=True, type=Path, help="Path to EcoCrop_DB.csv")
    args = parser.parse_args()
    catalog = build(args.ecocrop)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(catalog['crops'])} crops to {OUTPUT}")


if __name__ == "__main__":
    main()
