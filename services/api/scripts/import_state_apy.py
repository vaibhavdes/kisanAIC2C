#!/usr/bin/env python3
"""Import Maharashtra Agriculture Department district APY rows (Pune, Ahilyanagar) from the research
pack's `recent_history.new_district_apy` into data/market/state_apy_district.csv.

Source PDFs: https://krishi.maharashtra.gov.in/Site/Upload/GR/DISTRICTWISE%20APY-2023-24.pdf (final advance
estimates) and the 2025-26 third advance estimates (provisional). The market model uses a state row only for a
crop year that UPAg does not have yet (2025-26 today), so UPAg stays the series of record.

Usage: python services/api/scripts/import_state_apy.py /path/to/kisanai-claude-combined-pack-v2.json.txt
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "data" / "market" / "state_apy_district.csv"
CROPS = {"rice_paddy": "rice", "jowar": "sorghum", "bajra": "pearl_millet", "tur": "pigeon_pea", "chickpea": "chickpea",
         "wheat": "wheat", "maize": "maize", "groundnut": "groundnut", "soybean": "soybean", "cotton": "cotton", "sugarcane": "sugarcane"}


def main(path: str) -> None:
    pack = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = []
    for r in pack["recent_history"]["new_district_apy"]:
        crop = CROPS.get(r["crop_id"])
        if not crop or not r.get("area_ha") or not r.get("yield_kg_per_ha"):
            continue
        season = "kharif" if r["season"] == "unspecified" else r["season"]  # sugarcane is reported without a season
        rows.append({
            "state": "Maharashtra", "district": r["source_district"], "crop": crop, "season": season,
            "crop_year": int(r["agricultural_year"][:4]), "area_ha": r["area_ha"], "production": r.get("production_tonnes") or "",
            "production_unit": "bales_170kg" if crop == "cotton" else "tonnes", "yield_kg_ha": r["yield_kg_per_ha"],
            "estimate_status": r["estimate_status"], "source_url": r["source_url"],
        })
    with open(TARGET, "w", newline="", encoding="utf-8") as fh:
        fh.write("# Source: Maharashtra Agriculture Department district-wise APY (krishi.maharashtra.gov.in); 2025-26 rows are "
                 "third advance estimates (provisional). Imported from the KISANAI research pack.\n")
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["district"], r["crop"], r["season"], r["crop_year"])))
    print(f"{len(rows)} rows -> {TARGET}")


if __name__ == "__main__":
    main(sys.argv[1])
