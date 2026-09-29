#!/usr/bin/env python3
"""Build the regional agronomy packs in data/packs/ and validate them against the contract.

Sowing windows come from the official sources listed in each pack (state university packages
of practice in India, the CONAB planting calendar and MAPA/ADAPAR regulations in Brazil).
Packs are marked `curated_pending_review` until a regional expert reviews them in the app.

India's groundwater category is the state-level CGWB assessment; where no comparable official
category exists the pack says "unknown". District values are added only with a cited source.

Usage:
    python3 services/api/scripts/build_agronomy_packs.py
"""

from __future__ import annotations

import json
import requests
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
CATALOG = json.loads((ROOT / "data" / "crops" / "global_crop_catalog.json").read_text())
SCI = {crop["id"]: crop["scientific_name"] for crop in CATALOG["crops"]}
SCHEMA = json.loads((ROOT / "contracts" / "agronomy-pack.schema.json").read_text())

INDIA_SEASONS = [
    {"id": "kharif", "months": [6, 7, 8, 9, 10]},
    {"id": "rabi", "months": [10, 11, 12, 1, 2, 3]},
    {"id": "zaid", "months": [3, 4, 5, 6]},
]



def window(season: str, start: str, end: str, irrigated: bool = False, label: str | None = None) -> dict:
    item = {"season": season, "start": start, "end": end, "irrigation_required": irrigated}
    if label:
        item["label"] = label
    return item


def crop(crop_id: str, windows: list[dict], note: str | None = None) -> dict:
    item = {"crop_id": crop_id, "scientific_name": SCI[crop_id], "sowing_windows": windows}
    if note:
        item["note"] = note
    return item


MAHARASHTRA = {
    "schema_version": "1.0.0",
    "pack_id": "pack_in_maharashtra",
    "pack_version": 1,
    "region": {"country_code": "IN", "subdivision_code": "IN-MH", "name": "Maharashtra",
               "agro_climatic_zones": ["Western Plateau and Hills Region (Planning Commission zone 9)"]},
    "license": "CC-BY-4.0",
    "review": {"status": "curated_pending_review", "reviewer": None, "reviewed_at": None,
               "note": "Sowing windows curated from Maharashtra SAU packages of practices; awaiting state expert review."},
    "sources": [
        {"title": "Vasantrao Naik Marathwada Krishi Vidyapeeth, Parbhani - Package of Practices", "url": "https://vnmkv.ac.in/"},
        {"title": "Dr. Panjabrao Deshmukh Krishi Vidyapeeth, Akola - Package of Practices", "url": "https://www.pdkv.ac.in/"},
        {"title": "Mahatma Phule Krishi Vidyapeeth, Rahuri - Package of Practices", "url": "https://mpkv.ac.in/"},
        {"title": "IMD district rainfall normals (1991-2020)", "url": "https://mausam.imd.gov.in/"},
        {"title": "CGWB Dynamic Ground Water Resources of India", "url": "https://cgwb.gov.in/"},
    ],
    "seasons": INDIA_SEASONS,
    "groundwater": {"category": "safe", "scope": "district",
                    "note": "State average is safe, but several Marathwada and western Maharashtra blocks are semi-critical or over-exploited; check the local CGWB block category.",
                    "source": "CGWB Dynamic Ground Water Resources of India"},
    "crops": [
        crop("soybean", [window("kharif", "06-15", "07-15")], "Sow after 75-100 mm cumulative monsoon rain."),
        crop("cotton", [window("kharif", "06-15", "07-10"), window("kharif", "05-20", "06-10", True, "pre-monsoon irrigated")]),
        crop("pigeon_pea", [window("kharif", "06-15", "07-15")]),
        crop("sorghum", [window("kharif", "06-15", "07-10"), window("rabi", "09-15", "10-15", label="rabi on residual moisture")]),
        crop("pearl_millet", [window("kharif", "06-15", "07-15")]),
        crop("maize", [window("kharif", "06-15", "07-15"), window("rabi", "10-15", "11-15", True)]),
        crop("green_gram", [window("kharif", "06-15", "07-10")]),
        crop("black_gram", [window("kharif", "06-15", "07-10")]),
        crop("cowpea", [window("kharif", "06-15", "07-15")]),
        crop("groundnut", [window("kharif", "06-15", "07-15"), window("zaid", "01-15", "02-15", True, "summer irrigated")]),
        crop("sesame", [window("kharif", "06-15", "07-15")]),
        crop("finger_millet", [window("kharif", "06-15", "07-15")], "Mainly Konkan and western ghat districts."),
        crop("rice", [window("kharif", "06-15", "07-31")], "Rainfed transplanted rice in Konkan and eastern Vidarbha."),
        crop("sunflower", [window("kharif", "06-15", "07-15"), window("rabi", "10-01", "10-31")]),
        crop("chickpea", [window("rabi", "09-25", "10-20", label="rainfed on residual moisture"), window("rabi", "10-15", "11-15", True)]),
        crop("safflower", [window("rabi", "09-20", "10-20", label="rainfed on residual moisture")]),
        crop("wheat", [window("rabi", "11-01", "11-30", True, "timely irrigated"), window("rabi", "12-01", "12-15", True, "late sown")]),
        crop("onion", [window("kharif", "06-15", "07-31", label="kharif transplanting"), window("rabi", "11-15", "01-15", True, "rabi transplanting")]),
        crop("sugarcane", [window("kharif", "07-01", "08-15", True, "adsali"), window("rabi", "10-01", "11-15", True, "pre-seasonal"),
                           window("zaid", "01-01", "02-28", True, "suru")]),
        crop("dhaincha", [window("zaid", "05-25", "06-30", label="green manure before kharif")]),
        crop("sunn_hemp", [window("zaid", "05-25", "06-30", label="green manure before kharif")]),
    ],
    "districts": [],
    "priority_practices": ["broad-bed-furrow", "intercropping-pulses", "residue-retention", "rainfall-timed-sowing", "drip-irrigation"],
    "regulations": [],
}

PUNJAB = {
    "schema_version": "1.0.0",
    "pack_id": "pack_in_punjab",
    "pack_version": 1,
    "region": {"country_code": "IN", "subdivision_code": "IN-PB", "name": "Punjab",
               "agro_climatic_zones": ["Trans-Gangetic Plains Region (Planning Commission zone 6)"]},
    "license": "CC-BY-4.0",
    "review": {"status": "curated_pending_review", "reviewer": None, "reviewed_at": None,
               "note": "Sowing windows curated from PAU Package of Practices; awaiting state expert review."},
    "sources": [
        {"title": "Punjab Agricultural University - Package of Practices for Crops of Punjab (Kharif and Rabi)", "url": "https://www.pau.edu/"},
        {"title": "The Punjab Preservation of Subsoil Water Act, 2009", "url": "https://agri.punjab.gov.in/"},
        {"title": "CGWB Dynamic Ground Water Resources of India", "url": "https://cgwb.gov.in/"},
    ],
    "seasons": INDIA_SEASONS,
    "groundwater": {"category": "over_exploited", "scope": "state",
                    "note": "Punjab extracts more groundwater than is recharged state-wide; most blocks are over-exploited. Water-intensive crops should use DSR, AWD or be diversified.",
                    "source": "CGWB Dynamic Ground Water Resources of India"},
    "crops": [
        crop("wheat", [window("rabi", "10-25", "11-15", True, "timely"), window("rabi", "11-16", "12-15", True, "late sown")]),
        crop("rice", [window("kharif", "06-15", "07-10", True, "transplanting")], "Direct-seeded rice can be sown 1-15 June."),
        crop("maize", [window("kharif", "06-01", "06-30", True)]),
        crop("cotton", [window("kharif", "04-15", "05-15", True)]),
        crop("pigeon_pea", [window("kharif", "05-20", "06-15", True)]),
        crop("green_gram", [window("zaid", "03-20", "04-10", True, "summer moong"), window("kharif", "07-01", "07-20")]),
        crop("black_gram", [window("kharif", "07-01", "07-20")]),
        crop("mustard", [window("rabi", "10-10", "10-31", True)]),
        crop("rapeseed_canola", [window("rabi", "10-10", "10-31", True, "gobhi sarson")]),
        crop("chickpea", [window("rabi", "10-10", "10-31")]),
        crop("lentil", [window("rabi", "10-25", "11-15")]),
        crop("field_pea", [window("rabi", "10-15", "11-15", True)]),
        crop("barley", [window("rabi", "10-15", "11-15", True)]),
        crop("potato", [window("rabi", "09-25", "10-31", True)]),
        crop("sugarcane", [window("rabi", "09-20", "10-20", True, "autumn"), window("zaid", "02-15", "03-31", True, "spring")]),
        crop("sunflower", [window("zaid", "01-15", "02-15", True, "spring")]),
        crop("berseem", [window("rabi", "09-25", "10-15", True)]),
        crop("oats", [window("rabi", "10-10", "11-15", True, "fodder")]),
        crop("dhaincha", [window("zaid", "04-20", "05-31", True, "green manure before paddy")]),
    ],
    "districts": [],
    "priority_practices": ["direct-seeded-rice", "alternate-wetting-drying", "residue-retention", "reduced-disturbance", "green-manure", "legume-rotation"],
    "regulations": [
        {"crop_id": "rice", "earliest_sowing": "06-15",
         "text": "Paddy transplanting is not permitted before the date notified each year under the Punjab Preservation of Subsoil Water Act, 2009 (mid-June in recent years).",
         "source": "The Punjab Preservation of Subsoil Water Act, 2009"},
    ],
}

UTTAR_PRADESH = {
    "schema_version": "1.0.0",
    "pack_id": "pack_in_uttar_pradesh",
    "pack_version": 1,
    "region": {"country_code": "IN", "subdivision_code": "IN-UP", "name": "Uttar Pradesh",
               "agro_climatic_zones": ["Upper Gangetic Plains Region (zone 5)", "Middle Gangetic Plains Region (zone 4)", "Central Plateau and Hills (Bundelkhand, zone 8)"]},
    "license": "CC-BY-4.0",
    "review": {"status": "curated_pending_review", "reviewer": None, "reviewed_at": None,
               "note": "Sowing windows curated from UP Department of Agriculture and SAU packages of practices; awaiting state expert review."},
    "sources": [
        {"title": "Department of Agriculture, Uttar Pradesh - Kharif and Rabi packages of practices", "url": "https://upagriculture.com/"},
        {"title": "Chandra Shekhar Azad University of Agriculture and Technology, Kanpur", "url": "https://csauk.ac.in/"},
        {"title": "CGWB Dynamic Ground Water Resources of India", "url": "https://cgwb.gov.in/"},
    ],
    "seasons": INDIA_SEASONS,
    "groundwater": {"category": "semi_critical", "scope": "state",
                    "note": "State-average extraction is near the semi-critical threshold; many western UP blocks are over-exploited while eastern UP is largely safe.",
                    "source": "CGWB Dynamic Ground Water Resources of India"},
    "crops": [
        crop("rice", [window("kharif", "06-20", "07-20", True, "transplanting")]),
        crop("wheat", [window("rabi", "11-01", "11-25", True, "timely"), window("rabi", "12-01", "12-25", True, "late sown")]),
        crop("mustard", [window("rabi", "10-01", "10-25")]),
        crop("chickpea", [window("rabi", "10-15", "11-15")]),
        crop("lentil", [window("rabi", "10-15", "11-15")]),
        crop("field_pea", [window("rabi", "10-15", "11-15")]),
        crop("barley", [window("rabi", "11-01", "11-25")]),
        crop("pigeon_pea", [window("kharif", "06-15", "07-15")]),
        crop("maize", [window("kharif", "06-15", "07-15")]),
        crop("pearl_millet", [window("kharif", "07-01", "07-25")]),
        crop("sorghum", [window("kharif", "06-25", "07-15")]),
        crop("green_gram", [window("zaid", "03-10", "04-10", True, "zaid"), window("kharif", "07-01", "07-20")]),
        crop("black_gram", [window("zaid", "03-10", "04-10", True, "zaid"), window("kharif", "07-01", "07-20")]),
        crop("groundnut", [window("kharif", "06-15", "07-15")], "Mainly Bundelkhand and western UP light soils."),
        crop("sesame", [window("kharif", "07-01", "07-20")]),
        crop("sugarcane", [window("zaid", "02-15", "03-31", True, "spring"), window("rabi", "10-01", "10-31", True, "autumn")]),
        crop("potato", [window("rabi", "10-01", "10-31", True)]),
        crop("berseem", [window("rabi", "10-01", "10-31", True)]),
        crop("dhaincha", [window("zaid", "04-15", "05-31", True, "green manure before paddy")]),
    ],
    "districts": [],
    "priority_practices": ["reduced-disturbance", "green-manure", "legume-rotation", "residue-retention", "intercropping-pulses"],
    "regulations": [],
}


# Paraná soybean sowing regions (MAPA Portaria 1.579/2026, ADAPAR 2026/27). ADAPAR describes each region by
# geography; municipalities are assigned through their IBGE mesoregion.
PARANA_SOY_REGIONS = {
    "Região 2 (Norte, Noroeste, Centro-Oeste, Oeste)": (["Noroeste Paranaense", "Norte Central Paranaense", "Norte Pioneiro Paranaense",
                                                         "Centro Ocidental Paranaense", "Oeste Paranaense"], "09-01", "12-31"),
    "Região 3 (Sudoeste)": (["Sudoeste Paranaense"], "09-11", "01-10"),
    "Região 1 (Sul, Leste, Campos Gerais, Litoral)": (["Centro Oriental Paranaense", "Centro-Sul Paranaense", "Sudeste Paranaense",
                                                       "Metropolitana de Curitiba"], "09-20", "01-20"),
}
IBGE_MUNICIPALITIES = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/41/municipios"


def parana_districts() -> list[dict]:
    """Every Paraná municipality (IBGE register) with its legal soybean sowing window."""
    municipalities = requests.get(IBGE_MUNICIPALITIES, timeout=30).json()
    by_meso = {meso: (name, start, end) for name, (mesos, start, end) in PARANA_SOY_REGIONS.items() for meso in mesos}
    out = []
    for item in sorted(municipalities, key=lambda m: m["nome"]):
        meso = item["microrregiao"]["mesorregiao"]["nome"]
        region, start, end = by_meso[meso]
        out.append({"name": item["nome"], "subdivision": meso, "region_note": region,
                    "sowing_overrides": [{"crop_id": "soybean", "sowing_windows": [window("safra", start, end)],
                                          "note": f"Legal soybean sowing for {region} after the sanitary break (vazio sanitário)."}]})
    return out


PARANA = {
    "schema_version": "1.0.0",
    "pack_id": "pack_br_parana",
    "pack_version": 1,
    "region": {"country_code": "BR", "subdivision_code": "BR-PR", "name": "Paraná"},
    "license": "CC-BY-4.0",
    "review": {"status": "curated_pending_review", "reviewer": None, "reviewed_at": None,
               "note": "Planting months from the CONAB state planting calendar; soybean dates follow the MAPA/ADAPAR sanitary-break "
                       "regulation. Awaiting review by a Paraná agronomist (IDR-Paraná / EMBRAPA)."},
    "sources": [
        {"title": "CONAB - Calendário de plantio e colheita de grãos no Brasil (Paraná rows)",
         "url": "https://www.gov.br/conab/pt-br/acesso-a-informacao/institucional/publicacoes/arquivos-de-paginas/calendariozplantiozezcolheitazjunz2022.pdf"},
        {"title": "IBGE - Localidades API (municipalities of Paraná and their mesoregions)",
         "url": IBGE_MUNICIPALITIES},
        {"title": "ADAPAR - Períodos do vazio sanitário da soja, safra 2026/2027 (MAPA Portaria nº 1.579/2026)",
         "url": "https://www.adapar.pr.gov.br/Noticia/Periodos-do-vazio-sanitario-da-Soja-para-safra-de-20262027-comecam-em-junho"},
    ],
    # Southern-hemisphere seasons: summer crop (safra), second crop after soybean (safrinha) and winter crops (inverno).
    "seasons": [{"id": "safra", "months": [8, 9, 10, 11, 12, 1]}, {"id": "safrinha", "months": [1, 2, 3, 4]},
                {"id": "inverno", "months": [4, 5, 6, 7, 8]}],
    "groundwater": {"category": "unknown", "scope": "state",
                    "note": "No state groundwater stress category is published in the same form as India's CGWB assessment."},
    "crops": [
        crop("soybean", [window("safra", "09-20", "12-31")],
             "Statewide fallback 20 Sep-31 Dec; each municipality carries its own legal window (see districts)."),
        crop("maize", [window("safra", "09-11", "12-31", label="1st crop"), window("safrinha", "01-01", "04-30", label="2nd crop (safrinha)")]),
        crop("dry_bean", [window("safra", "08-01", "11-30", label="1st crop (wet season)"), window("safrinha", "01-01", "03-31", label="2nd crop (dry season)")]),
        crop("wheat", [window("inverno", "04-01", "07-31")]),
        crop("oats", [window("inverno", "04-01", "07-31")], "Black oat is also the main winter cover crop for no-till."),
        crop("barley", [window("inverno", "05-01", "07-31")]),
        crop("rapeseed_canola", [window("inverno", "04-01", "06-30")]),
    ],
    "districts": parana_districts(),
    "priority_practices": ["reduced-disturbance", "residue-retention", "rhizobium-inoculation", "legume-rotation", "green-manure", "field-scouting"],
    "regulations": [
        {"crop_id": "soybean", "earliest_sowing": "09-01",
         "text": "Soybean sanitary break (vazio sanitário) against Asian soybean rust: sowing is allowed 1 Sep-31 Dec (Region 2: North, "
                 "Northwest, Centre-West, West), 11 Sep-10 Jan (Region 3: Southwest) and 20 Sep-20 Jan (Region 1: South, East, Campos Gerais, coast).",
         "source": "MAPA Portaria nº 1.579/2026; ADAPAR"},
    ],
}


def main() -> None:
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    out_dir = ROOT / "data" / "packs"
    out_dir.mkdir(parents=True, exist_ok=True)
    for pack in (MAHARASHTRA, PUNJAB, UTTAR_PRADESH, PARANA):
        errors = list(validator.iter_errors(pack))
        if errors:
            raise SystemExit(f"{pack['pack_id']}: " + "; ".join(error.message for error in errors[:5]))
        path = out_dir / f"{pack['region']['subdivision_code']}.json"
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)} ({len(pack['crops'])} crops, {len(pack.get('districts', []))} districts)")


if __name__ == "__main__":
    main()
