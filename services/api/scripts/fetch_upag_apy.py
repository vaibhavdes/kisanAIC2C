#!/usr/bin/env python3
"""Download district crop area, production and yield (APY) from UPAg, the Ministry of Agriculture's
Unified Portal for Agricultural Statistics, and save the rows the market model needs.

Source: "Complete APY Dataset (District Level)", https://upag.gov.in/dash-reports/desdistrictwisecompletedatasetreport
(Directorate of Economics & Statistics, DA&FW; final estimates). The report is a Plotly Dash page with no
public API, so this script sends the same request the page sends when "Apply" is pressed. The report
returns at most three crop years per request.

Writes:
  data/market/upag_apy_district.csv   one row per state, district, crop, season and crop year (default: Maharashtra)
  data/market/upag_all_india_yield.csv  area-weighted all-India yield per crop and year (used to turn the
                                        CACP cost per quintal into a cost per hectare)

Usage: python services/api/scripts/fetch_upag_apy.py [--state Maharashtra] [--from-year 2013] [--to-year 2024]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "market"
DASH = "https://dash.upag.gov.in"
SEARCH = "?t=&stateID=0&"

# UPAg crop name -> KISANAI crop id
CROPS = {
    "Rice": "rice", "Wheat": "wheat", "Maize": "maize", "Jowar": "sorghum", "Bajra": "pearl_millet",
    "Tur": "pigeon_pea", "Gram": "chickpea", "Groundnut": "groundnut", "Soybean": "soybean",
    "Cotton": "cotton", "Sugarcane": "sugarcane",
}
# UPAg reports cotton production in bales of 170 kg (the column is labelled tonnes); its yield is lint kg/ha.
PRODUCTION_UNIT = {"cotton": "bales_170kg"}


def fetch_years(from_year: int, to_year: int) -> list[dict]:
    outputs = [
        {"id": "ddcd-reports-data-store", "property": "data"},
        {"id": "ddcd-report-suffix-title", "property": "children"},
        {"id": "ddcd-report-notification3", "property": "children"},
        {"id": "ddcd-report-notification1", "property": "children"},
        {"id": "ddcd-report-notification2", "property": "children"},
    ]
    filters = {
        "checkbox": False, "cropcategory": ["Food Grains", "Oilseeds", "Commercial Crops"], "crop": ["All"],
        "fromyear": str(from_year), "toyear": str(to_year), "uom": "Actual", "metric": ["Area", "Production", "Yield"],
    }
    body = {
        "output": ".." + "...".join(f"{o['id']}.{o['property']}" for o in outputs) + "..",
        "outputs": outputs,
        "inputs": [{"id": "ddcd-report-filters-store", "property": "data", "value": filters}],
        "state": [{"id": "url", "property": "search", "value": SEARCH}],
        "changedPropIds": ["ddcd-report-filters-store.data"],
    }
    request = urllib.request.Request(
        DASH + "/_dash-update-component", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "KISANAI-C2C data loader",
                 "Referer": DASH + "/desdistrictwisecompletedatasetreport" + SEARCH},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        payload = json.loads(response.read())
    return payload["response"]["ddcd-reports-data-store"]["data"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="Maharashtra")
    parser.add_argument("--from-year", type=int, default=2013)
    parser.add_argument("--to-year", type=int, default=2024)
    args = parser.parse_args()

    district_rows: dict[tuple, dict] = {}
    # all-India: crop, year -> [sum(area), sum(yield*area)] over district "Total" rows
    india: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0])
    year = args.from_year
    while year <= args.to_year:
        last = min(year + 2, args.to_year)
        print(f"UPAg {year}-{last} ...", file=sys.stderr)
        rows = fetch_years(year, last)
        cells: dict[tuple, dict] = defaultdict(dict)
        for row in rows:
            crop_id = CROPS.get(row["Crop"])
            if not crop_id:
                continue
            key = (row["State"], row["District"], crop_id, row["Season"], int(row["Crop Year Code"]))
            cells[key][row["Metric"]] = row["Value"]
        for (state, district, crop_id, season, crop_year), metrics in cells.items():
            area, production, yld = metrics.get("Area"), metrics.get("Production"), metrics.get("Yield")
            if season == "Total" and area and yld:
                india[(crop_id, crop_year)][0] += area
                india[(crop_id, crop_year)][1] += yld * area
            if state != args.state or season == "Total":
                continue
            district_rows[(district, crop_id, season, crop_year)] = {
                "state": state, "district": district, "crop": crop_id, "season": season.lower(), "crop_year": crop_year,
                "area_ha": round(area, 2) if area is not None else "",
                "production": round(production, 2) if production is not None else "",
                "production_unit": PRODUCTION_UNIT.get(crop_id, "tonnes"),
                "yield_kg_ha": round(yld, 1) if yld is not None else "",
            }
        year = last + 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["state", "district", "crop", "season", "crop_year", "area_ha", "production", "production_unit", "yield_kg_ha"]
    with open(OUT_DIR / "upag_apy_district.csv", "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# Source: UPAg Complete APY Dataset (District Level), DES DA&FW, final estimates. Downloaded {date.today()}.\n")
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(district_rows.values(), key=lambda r: (r["district"], r["crop"], r["season"], r["crop_year"])))
    with open(OUT_DIR / "upag_all_india_yield.csv", "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# Area-weighted all-India yield from UPAg district totals (all seasons). Downloaded {date.today()}.\n")
        writer = csv.writer(fh)
        writer.writerow(["crop", "crop_year", "area_ha", "yield_kg_ha"])
        for (crop_id, crop_year), (area, weighted) in sorted(india.items()):
            writer.writerow([crop_id, crop_year, round(area, 1), round(weighted / area, 1)])
    print(f"{len(district_rows)} district rows, {len(india)} all-India crop-years", file=sys.stderr)


if __name__ == "__main__":
    main()
