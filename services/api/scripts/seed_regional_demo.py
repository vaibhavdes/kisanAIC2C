#!/usr/bin/env python3
"""Sample neighbour farms and crop plans for the "farmers near you" demo (Pune and Ahilyanagar).

- Haveli taluka, around Wagholi: sample farms (stored with listed=false, so they never appear in anyone's
  farm list) placed in 13 villages, each with a crop plan per season. The village mix follows the area:
  peri-urban villages (Wagholi, Kesnand, Lonikand, Bakori, Perne...) grow onion, vegetables, wheat and
  rabi jowar; villages near the Yeshwant sugar factory belt (Loni Kalbhor, Uruli Kanchan, Theur) grow more
  sugarcane. Onion is above its usual share this rabi, so the crowding warning shows.
- Other talukas of both districts: anonymous crop plans following each district's UPAg crop shares.

Everything is marked source="demo" and owner "demo-neighbour"; the app says how many sample entries a count
includes. The store follows STORE_PROVIDER / SQLITE_PATH / FIRESTORE_DATABASE like the app.

Usage: STORE_PROVIDER=sqlite SQLITE_PATH=work/local/ag02.sqlite3 PYTHONPATH=services/api/src \\
       python services/api/scripts/seed_regional_demo.py [--remove]
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import UTC, datetime

from kisanai_c2c import market as m
from kisanai_c2c.market_service import plan_year
from kisanai_c2c.settings import get_settings
from kisanai_c2c.store import get_store

OWNER = "demo-neighbour"
ACRE = 0.40468564224
# Village -> (sample farms, crop mix key). Centres are looked up on OpenStreetMap.
# Village -> (centre lat, lon from OpenStreetMap, sample farms, crop mix key).
HAVELI = {
    "Wagholi": (18.5806, 73.9833, 30, "periurban"),
    "Lonikand": (18.5946, 74.0322, 22, "periurban"),
    "Kesnand": (18.5727, 74.0219, 22, "periurban"),
}
MIX = {
    "periurban": {
        "rabi": {"onion": 32, "wheat": 18, "sorghum": 14, "tomato": 12, "chickpea": 9, "maize": 7, "potato": 4, "sugarcane": 4},
        "kharif": {"pearl_millet": 22, "soybean": 16, "tomato": 18, "onion": 12, "maize": 12, "groundnut": 8, "sugarcane": 6, "potato": 6},
        "summer": {"onion": 30, "tomato": 28, "groundnut": 20, "maize": 14, "pearl_millet": 8},
    },
    "cane": {
        "rabi": {"sugarcane": 34, "onion": 20, "wheat": 16, "sorghum": 12, "tomato": 8, "chickpea": 6, "maize": 4},
        "kharif": {"sugarcane": 34, "pearl_millet": 16, "soybean": 14, "tomato": 12, "maize": 12, "groundnut": 6, "onion": 6},
        "summer": {"sugarcane": 30, "onion": 25, "tomato": 20, "groundnut": 15, "maize": 10},
    },
}
WATER = ["irrigated", "supplemental_irrigation", "supplemental_irrigation", "rainfed"]
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
    now = datetime.now(UTC).isoformat()
    if args.remove:
        for collection in ("crop_plans", "farms"):
            for doc in store.list(collection, filters={"owner_subject": OWNER}, limit=500):
                store.delete(collection, doc["id"])
        print("removed sample neighbours")
        return

    farms = plans = 0
    for village, (lat0, lon0, count, mix_key) in HAVELI.items():
        centre = (lat0, lon0)
        for i in range(count):
            # Spread fields 0.4-2.2 km around the village centre.
            angle, dist = rng.uniform(0, 2 * math.pi), rng.uniform(0.3, 1.6)
            lat = centre[0] + dist / 111.0 * math.cos(angle)
            lon = centre[1] + dist / (111.0 * math.cos(math.radians(centre[0]))) * math.sin(angle)
            acres = round(rng.choice([0.5, 0.75, 1, 1, 1.5, 2, 2, 2.5, 3, 4, 5]), 2)
            farm_id = f"nbr_haveli_{village.lower().replace(' ', '_')}_{i}"
            season_crops = {s: rng.choices(list(MIX[mix_key][s]), list(MIX[mix_key][s].values()))[0] for s in ("kharif", "rabi", "summer")}
            store.put("farms", farm_id, {
                "id": farm_id, "name": f"{village} farm {i + 1}", "country_code": "IN", "state_code": "MH", "state_name": "Maharashtra",
                "district": "Pune", "taluka": "Haveli", "village": village, "pincode": None, "boundary_coordinates": [],
                "area_value": acres, "area_unit": "acre", "area_ha": round(acres * ACRE, 4),
                "location": {"latitude": round(lat, 5), "longitude": round(lon, 5), "source": "imported", "confirmed": True},
                "water_access": "irrigated" if season_crops["rabi"] == "sugarcane" else rng.choice(WATER), "soil_type": "black",
                "current_crop": season_crops["kharif"], "previous_crop": season_crops["summer"], "crop_status": "harvested",
                "owner_subject": OWNER, "node_id": node, "version": 1, "listed": False, "source": "demo",
                "created_at": now, "updated_at": now,
            })
            farms += 1
            for season, crop in season_crops.items():
                year = plan_year(season)
                store.put("crop_plans", f"{farm_id}_{season}_{year}", {
                    "id": f"{farm_id}_{season}_{year}", "farm_id": farm_id, "node_id": node, "district": "pune", "taluka": "Haveli",
                    "village": village, "lat": round(lat, 3), "lon": round(lon, 3), "crop": crop, "season": season, "year": year,
                    "area_ha": round(acres * ACRE, 3), "source": "demo", "owner_subject": OWNER, "created_at": now,
                })
                plans += 1

    for season in ("kharif", "rabi", "summer"):
        year = plan_year(season)
        for district, talukas in TALUKAS.items():
            shares = district_mix(district, season)
            for taluka in talukas:
                for i in range(args.per_taluka if shares else 0):
                    doc_id = f"demo_{district}_{taluka.lower()}_{season}_{year}_{i}"
                    store.put("crop_plans", doc_id, {
                        "id": doc_id, "farm_id": doc_id, "node_id": node, "district": district, "taluka": taluka, "village": None,
                        "crop": rng.choices(list(shares), list(shares.values()))[0], "season": season, "year": year,
                        "area_ha": round(rng.uniform(0.3, 2.5), 2), "source": "demo", "owner_subject": OWNER, "created_at": now,
                    })
                    plans += 1
    print(f"wrote {farms} sample neighbour farms and {plans} crop plans")


if __name__ == "__main__":
    main()
