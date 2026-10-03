#!/usr/bin/env python3
"""Download monthly wholesale (mandi) prices and arrivals from AGMARKNET 2.0 (Directorate of Marketing &
Inspection, Ministry of Agriculture) for the crops KISANAI recommends.

AGMARKNET's "Price Trend" reports are served without a key from https://api.agmarknet.gov.in/v1/price-trend/.
Each monthly report row holds the month asked for, the month before and the same month a year earlier, so
asking for every second month covers every month.

  District mode (default): average modal price per district and month, for the whole state.
    -> data/market/agmarknet_district_monthly.csv
  Market mode (--markets Yavatmal,Nashik): modal price and arrivals per APMC market and month.
    -> data/market/agmarknet_market_monthly.csv (rows for the named districts are replaced)

Usage:
  python services/api/scripts/fetch_agmarknet_prices.py [--from 2014-01] [--to 2026-09]
  python services/api/scripts/fetch_agmarknet_prices.py --markets Yavatmal,Nashik --from 2020-01
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "market"
API = "https://api.agmarknet.gov.in/v1"
STATE_IDS = {"Maharashtra": 20}
# KISANAI crop id -> AGMARKNET commodity id. Sugarcane is sold to mills at the FRP, not in mandis.
COMMODITIES = {
    "soybean": 13, "cotton": 15, "pigeon_pea": 45, "chickpea": 6, "wheat": 1, "sorghum": 5,
    "pearl_millet": 28, "onion": 23, "rice": 2, "maize": 4, "groundnut": 10, "tomato": 65, "potato": 24,
}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]


def get(path: str, params: dict) -> dict:
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(5):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "KISANAI-C2C data loader"})
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except Exception as exc:  # the service returns 500 on bursts; back off and retry
            if attempt == 4:
                print(f"  failed {url}: {exc}", file=sys.stderr)
                return {}
            time.sleep(5 * (attempt + 1) ** 2)  # AGMARKNET answers 429 when asked too often
    return {}


def months_between(start: str, end: str) -> list[tuple[int, int]]:
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def shifted(year: int, month: int, by: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + by
    return index // 12, index % 12 + 1


def parse_rows(payload: dict, year: int, month: int, prefix: str, place_key: str) -> list[tuple[str, int, int, float]]:
    """(place, year, month, value) for the asked month, the month before and the same month a year earlier."""
    wanted = {
        f"{prefix}_{MONTHS[month - 1]}_{year}": (year, month),
        f"{prefix}_{MONTHS[shifted(year, month, -1)[1] - 1]}_{shifted(year, month, -1)[0]}": shifted(year, month, -1),
        f"{prefix}_{MONTHS[month - 1]}_{year - 1}": (year - 1, month),
    }
    out = []
    for row in payload.get("rows") or []:
        place = str(row.get(place_key) or "").strip()
        for column, (y, m) in wanted.items():
            value = row.get(column)
            if place and isinstance(value, (int, float)) and value > 0:
                out.append((place, y, m, float(value)))
    return out


def fetch_district(state: str, start: str, end: str, fill_gaps: bool = False) -> None:
    state_id = STATE_IDS[state]
    # Every second month: each report also carries the month before it.
    plan = [(c, y, m) for c in COMMODITIES for (y, m) in months_between(start, end)[1::2] + [tuple(map(int, end.split("-")))]]
    plan = list(dict.fromkeys(plan))
    if fill_gaps:  # only months for which no district of the state has a price yet
        have = set()
        path = OUT_DIR / "agmarknet_district_monthly.csv"
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                have = {(r["crop"], int(r["year"]), int(r["month"])) for r in csv.DictReader(line for line in fh if not line.startswith("#"))}
        plan = list(dict.fromkeys((c, y, m) for c in COMMODITIES for (y, m) in months_between(start, end) if (c, y, m) not in have))
        print(f"  {len(plan)} missing crop-months", file=sys.stderr)
    found: dict[tuple, float] = {}
    path = OUT_DIR / "agmarknet_district_monthly.csv"
    if path.exists():  # merge: keep earlier rows, newer downloads replace the same month
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(line for line in fh if not line.startswith("#")):
                found[(row["district"], row["crop"], int(row["year"]), int(row["month"]))] = float(row["modal_price_rs_qtl"])

    def task(item):
        crop, y, m = item
        payload = get("price-trend/wholesale-prices-monthly", {
            "report_mode": "Districtwise", "commodity": COMMODITIES[crop], "year": y, "month": m, "state": state_id})
        return crop, parse_rows(payload, y, m, "prices", "district")

    with ThreadPoolExecutor(max_workers=2) as pool:
        for i, (crop, rows) in enumerate(pool.map(task, plan), 1):
            for place, y, m, value in rows:
                found[(place, crop, y, m)] = value
            if i % 50 == 0:
                print(f"  {i}/{len(plan)} reports", file=sys.stderr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "agmarknet_district_monthly.csv", "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# Source: AGMARKNET 2.0 Price Trend, district-wise wholesale prices monthly analysis (Rs/quintal, "
                 f"average of daily modal prices). State {state}. Downloaded {date.today()}.\n")
        writer = csv.writer(fh)
        writer.writerow(["state", "district", "crop", "year", "month", "modal_price_rs_qtl"])
        for (place, crop, y, m), value in sorted(found.items()):
            writer.writerow([state, place, crop, y, m, round(value, 2)])
    print(f"{len(found)} district-month prices written", file=sys.stderr)


def district_ids(state_id: int) -> dict[str, int]:
    payload = get("location/state", {"page_size": 100})
    for state in payload.get("states", []):
        if state.get("id") == state_id:
            return {d["district_name"].strip().lower(): d["id"] for d in state.get("districts", [])}
    return {}


def fetch_markets(state: str, districts: list[str], start: str, end: str) -> None:
    state_id = STATE_IDS[state]
    ids = district_ids(state_id)
    aliases = {"amravati": "amarawati", "gondia": "gondiya", "chhatrapati sambhajinagar": "chattrapati sambhajinagar"}
    found: dict[tuple, dict] = {}
    plan = []
    for name in districts:
        did = ids.get(aliases.get(name.lower(), name.lower()))
        if not did:
            print(f"  unknown AGMARKNET district: {name}", file=sys.stderr)
            continue
        for crop in COMMODITIES:
            for (y, m) in list(dict.fromkeys(months_between(start, end)[1::2] + [tuple(map(int, end.split("-")))])):
                plan.append((name, did, crop, y, m))

    def task(item):
        name, did, crop, y, m = item
        params = {"report_mode": "Marketwise", "commodity": COMMODITIES[crop], "year": y, "month": m,
                  "state": state_id, "district": did}
        prices = parse_rows(get("price-trend/wholesale-prices-monthly", params), y, m, "prices", "market")
        arrivals = parse_rows(get("price-trend/wholesale-arrivals-monthly", params), y, m, "arrivals", "market")
        return name, crop, prices, arrivals

    with ThreadPoolExecutor(max_workers=6) as pool:
        for i, (name, crop, prices, arrivals) in enumerate(pool.map(task, plan), 1):
            for market, y, m, value in prices:
                found.setdefault((name, market, crop, y, m), {})["price"] = value
            for market, y, m, value in arrivals:
                found.setdefault((name, market, crop, y, m), {})["arrivals"] = value
            if i % 50 == 0:
                print(f"  {i}/{len(plan)} reports", file=sys.stderr)

    path = OUT_DIR / "agmarknet_market_monthly.csv"
    keep = []
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            keep = [row for row in csv.DictReader(line for line in fh if not line.startswith("#"))
                    if row["district"].lower() not in {d.lower() for d in districts} or row["crop"] not in COMMODITIES]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# Source: AGMARKNET 2.0 Price Trend, market-wise wholesale prices (Rs/quintal) and arrivals "
                 f"(tonnes) monthly analysis. State {state}. Downloaded {date.today()}.\n")
        writer = csv.DictWriter(fh, fieldnames=["state", "district", "market", "crop", "year", "month",
                                                "modal_price_rs_qtl", "arrivals_t"])
        writer.writeheader()
        writer.writerows(keep)
        for (name, market, crop, y, m), values in sorted(found.items()):
            writer.writerow({"state": state, "district": name, "market": market, "crop": crop, "year": y, "month": m,
                             "modal_price_rs_qtl": round(values["price"], 2) if "price" in values else "",
                             "arrivals_t": round(values["arrivals"], 2) if "arrivals" in values else ""})
    print(f"{len(found)} market-month rows written for {', '.join(districts)}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="Maharashtra")
    parser.add_argument("--from", dest="start", default="2014-01")
    today = date.today()
    last = shifted(today.year, today.month, -1)
    parser.add_argument("--to", dest="end", default=f"{last[0]}-{last[1]:02d}")
    parser.add_argument("--fill-gaps", action="store_true", help="fetch only months with no price yet")
    parser.add_argument("--crops", help="comma-separated crop ids to fetch (default: all)")
    parser.add_argument("--markets", help="comma-separated districts for market (APMC) level prices and arrivals")
    args = parser.parse_args()
    if args.crops:
        for crop in list(COMMODITIES):
            if crop not in args.crops.split(","):
                COMMODITIES.pop(crop)
    if args.markets:
        fetch_markets(args.state, [d.strip() for d in args.markets.split(",") if d.strip()], args.start, args.end)
    else:
        fetch_district(args.state, args.start, args.end, args.fill_gaps)


if __name__ == "__main__":
    main()
