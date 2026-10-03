#!/usr/bin/env python3
"""Find coordinates for each APMC market in data/market/agmarknet_market_monthly.csv with OpenStreetMap
Nominatim (one request per second, as its usage policy asks), so the app can show the distance to each
mandi and the transport cost. Writes data/market/apmc_locations.json as {"district|market": [lat, lon]}.

Usage: python services/api/scripts/geocode_apmc.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "data" / "market" / "agmarknet_market_monthly.csv"
TARGET = ROOT / "data" / "market" / "apmc_locations.json"
ALIASES = {"ahmednagar": "ahilyanagar", "ahmadnagar": "ahilyanagar"}


def town(market: str) -> str:
    name = re.sub(r"\(.*?\)|APMC|Sub Yard|Sub-Yard|Market|Yard", " ", market, flags=re.I)
    return " ".join(name.split())


def lookup(query: str) -> list[float] | None:
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "in"})
    request = urllib.request.Request(url, headers={"User-Agent": "KISANAI-C2C-Agricultural-Intelligence/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        rows = json.loads(response.read())
    return [round(float(rows[0]["lat"]), 5), round(float(rows[0]["lon"]), 5)] if rows else None


def main() -> None:
    with open(SOURCE, encoding="utf-8") as fh:
        pairs = sorted({(r["district"], r["market"].strip()) for r in csv.DictReader(line for line in fh if not line.startswith("#"))})
    found = json.loads(TARGET.read_text()) if TARGET.exists() else {}
    for district, market in pairs:
        key = f"{ALIASES.get(district.lower(), district.lower())}|{market}"
        if key in found:
            continue
        inner = re.search(r"\(([^)]+)\)", market)
        queries = ([f"{inner.group(1)}, {district}, Maharashtra"] if inner else []) + [f"{town(market)}, {district}, Maharashtra", f"{town(market)}, Maharashtra"]
        for query in queries:
            time.sleep(1.1)
            try:
                point = lookup(query)
            except Exception as exc:
                print(f"  {query}: {exc}", file=sys.stderr)
                point = None
            if point:
                found[key] = point
                print(f"{key} -> {point}", file=sys.stderr)
                break
        else:
            print(f"{key}: not found", file=sys.stderr)
    TARGET.write_text(json.dumps(found, indent=1, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
