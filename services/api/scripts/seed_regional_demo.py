#!/usr/bin/env python3
"""Adds sample crop plans for villages and talukas of Pune and Ahilyanagar, so the "farmers near you"
signal can be shown before real farmers have planned.

- Haveli taluka (Wagholi and the villages around it) gets per-village plans with the crop mix typical of
  Pune's peri-urban belt: onion, vegetables, wheat and rabi jowar in rabi; bajra, soybean and vegetables in
  kharif. Onion is pushed above its usual share in rabi so crowding is visible.
- Other talukas follow each district's crop shares in UPAg.

Every entry is stored with source="demo" and owner "demo-regional-sample"; the app reports how many sample
entries a count includes. Only crop_plans are written (never farms). The target store follows
STORE_PROVIDER / SQLITE_PATH / FIRESTORE_DATABASE like the app.

Usage: STORE_PROVIDER=sqlite SQLITE_PATH=work/local/ag02.sqlite3 PYTHONPATH=services/api/src \
       python services/api/scripts/seed_regional_demo.py [--remove]
"""
from __future__ import annotations

import argparse
import random
from datetime import UTC, datetime

from kisanai_c2c import market as m
from kisanai_c2c.market_service import plan_year
from kisanai_c2c.settings import get_settings
from kisanai_c2c.store import get_store

OWNER = "demo-regional-sample"
# Villages of Haveli taluka around Wagholi, with how many sample farmers each gets.
HAVELI_VILLAGES = {
    "Wagholi": 10, "Lonikand": 7, "Kesnand": 7, "Bakori": 6, "Perne": 6, "Avhalwadi": 5, "Bhavadi": 5,
    "Wade Bolhai": 6, "Manjri Budruk": 6, "Loni Kalbhor": 7, "Uruli Kanchan": 7, "Theur": 6, "Phulgaon": 5,
}
# Typical peri-urban Haveli mix (weights), by season.
HAVELI_MIX = {
    "rabi": {"onion": 30, "wheat": 18, "sorghum": 14, "tomato": 12, "chickpea": 10, "maize": 8, "potato": 4, "sugarcane": 4},
    "kharif": {"pearl_millet": 22, "soybean": 18, "tomato": 16, "onion": 12, "maize": 12, "groundnut": 8, "sugarcane": 6, "potato": 6},
    "summer": {"onion": 30, "tomato": 25, "groundnut": 20, "maize": 15, "pearl_millet": 10},
}
TALUKAS = {
    "pune": ["Baramati", "Indapur", "Junnar", "Shirur", "Daund", "Purandar", "Khed"],
    "ahilyanagar": ["Rahuri", "Sangamner", "Shrirampur", "Kopargaon", "Shevgaon", "Pathardi", "Rahata", "Nevasa"],
}
PUSH = {("pune", "rabi"): {"onion": 2.0}, ("ahilyanagar", "rabi"): {"onion": 2.0, "chickpea": 1.4},
        ("pune", "kharif"): {"soybean": 1.6}, ("ahilyanagar", "kharif"): {"soybean": 1.6}}


def district_mix(district: str, season: str) -> dict[str, float]:
    shares = {c: (m.apy_trend(district, c, season) or {}).get("district_share") or 0
              for (d, c, s) in m.apy() if d == district and s == season}
    for crop, estimate in (m.reference().get("estimates") or {}).items():
        if m.season_calendar(crop, season):
            shares[crop] = shares.get(crop) or estimate.get("usual_share", 0)
    for crop, factor in PUSH.get((district, season), {}).items():
        shares[crop] = shares.get(crop, 0.05) * factor
    return {c: w for c, w in shares.items() if w > 0 and m.season_calendar(c, season)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-taluka", type=int, default=6)
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    store, node = get_store(), get_settings().node_id
    rng = random.Random(42)
    written = 0

    def put(doc_id, district, taluka, village, crop, season, year):
        nonlocal written
        if args.remove:
            store.delete("crop_plans", doc_id)
            return
        store.put("crop_plans", doc_id, {
            "id": doc_id, "farm_id": doc_id, "node_id": node, "district": district, "taluka": taluka, "village": village,
            "crop": crop, "season": season, "year": year, "area_ha": round(rng.uniform(0.3, 2.5), 2), "source": "demo",
            "owner_subject": OWNER, "created_at": datetime.now(UTC).isoformat(),
        })
        written += 1

    for season in ("kharif", "rabi", "summer"):
        year = plan_year(season)
        mix = HAVELI_MIX[season]
        for village, count in HAVELI_VILLAGES.items():
            for i in range(count):
                crop = rng.choices(list(mix), list(mix.values()))[0]
                put(f"demo_pune_haveli_{village.lower().replace(' ', '_')}_{season}_{year}_{i}", "pune", "Haveli", village, crop, season, year)
        for district, talukas in TALUKAS.items():
            shares = district_mix(district, season)
            if not shares:
                continue
            for taluka in talukas:
                for i in range(args.per_taluka):
                    crop = rng.choices(list(shares), list(shares.values()))[0]
                    put(f"demo_{district}_{taluka.lower()}_{season}_{year}_{i}", district, taluka, None, crop, season, year)
    print("removed" if args.remove else f"wrote {written}", "sample crop plans")


if __name__ == "__main__":
    main()
