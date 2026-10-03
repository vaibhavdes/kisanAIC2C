"""Market economics for crop choice: past mandi prices, the expected price at harvest, how many nearby
farmers are planting the same crop, and a yield/price/profit simulation for the farmer's own field.

Data (data/market/, refreshed with services/api/scripts/fetch_*.py):
  agmarknet_district_monthly.csv  AGMARKNET monthly average modal price per district (Rs/quintal)
  agmarknet_market_monthly.csv    AGMARKNET monthly modal price and arrivals per APMC market
  upag_apy_district.csv           UPAg district area, production and yield per crop and season
  upag_all_india_yield.csv        all-India yield (turns the CACP cost per quintal into a cost per hectare)
  reference.json                  MSP history, CACP cost of production, labelled estimates for gaps
"""
from __future__ import annotations

import csv
import json
import math
import random
import statistics
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Iterable

from .settings import PROJECT_ROOT

DATA = PROJECT_ROOT / "data" / "market"

# When each crop is sown and sold in Maharashtra, per season (months, 1 = January). The harvest window is
# the months most of the crop reaches the mandi; `offset` is the year of the first harvest month relative
# to the sowing year. Source: MPKV/VNMKV crop calendars as used in the crop agronomy catalog.
CALENDAR: dict[tuple[str, str], dict[str, Any]] = {
    ("soybean", "kharif"): {"sow": 6, "harvest": (10, 11, 12), "offset": 0},
    ("cotton", "kharif"): {"sow": 6, "harvest": (11, 12, 1), "offset": 0},
    ("pigeon_pea", "kharif"): {"sow": 6, "harvest": (1, 2, 3), "offset": 1},
    ("sorghum", "kharif"): {"sow": 6, "harvest": (10, 11, 12), "offset": 0},
    ("sorghum", "rabi"): {"sow": 10, "harvest": (2, 3, 4), "offset": 1},
    ("pearl_millet", "kharif"): {"sow": 6, "harvest": (9, 10, 11), "offset": 0},
    ("pearl_millet", "summer"): {"sow": 2, "harvest": (5, 6), "offset": 0},
    ("maize", "kharif"): {"sow": 6, "harvest": (10, 11, 12), "offset": 0},
    ("maize", "rabi"): {"sow": 10, "harvest": (2, 3, 4), "offset": 1},
    ("groundnut", "kharif"): {"sow": 6, "harvest": (10, 11), "offset": 0},
    ("groundnut", "summer"): {"sow": 2, "harvest": (5, 6), "offset": 0},
    ("rice", "kharif"): {"sow": 6, "harvest": (11, 12, 1), "offset": 0},
    ("chickpea", "rabi"): {"sow": 10, "harvest": (2, 3, 4), "offset": 1},
    ("wheat", "rabi"): {"sow": 11, "harvest": (3, 4, 5), "offset": 1},
    ("onion", "kharif"): {"sow": 7, "harvest": (10, 11, 12), "offset": 0},
    ("onion", "rabi"): {"sow": 11, "harvest": (3, 4, 5), "offset": 1},
    ("onion", "summer"): {"sow": 2, "harvest": (5, 6), "offset": 0},
    ("tomato", "kharif"): {"sow": 6, "harvest": (9, 10, 11), "offset": 0},
    ("tomato", "rabi"): {"sow": 10, "harvest": (1, 2, 3), "offset": 1},
    ("tomato", "summer"): {"sow": 2, "harvest": (5, 6), "offset": 0},
    ("potato", "kharif"): {"sow": 6, "harvest": (9, 10), "offset": 0},
    ("potato", "rabi"): {"sow": 11, "harvest": (2, 3), "offset": 1},
    ("sugarcane", "kharif"): {"sow": 7, "harvest": (11, 12, 1, 2, 3), "offset": 1},
    ("sugarcane", "rabi"): {"sow": 10, "harvest": (11, 12, 1, 2, 3), "offset": 1},
    ("sugarcane", "summer"): {"sow": 2, "harvest": (11, 12, 1, 2, 3), "offset": 1},
}
# Crops that keep for months after harvest, so selling later is an option.
STORABLE = {"potato", "onion", "pigeon_pea", "chickpea", "wheat", "soybean", "cotton", "maize", "sorghum", "pearl_millet", "groundnut"}
# Mill-sold at the Fair and Remunerative Price, not through mandis.
FRP_CROPS = {"sugarcane"}

DISTRICT_ALIASES = {
    "ahmednagar": "ahilyanagar", "ahmadnagar": "ahilyanagar", "osmanabad": "dharashiv", "aurangabad": "chhatrapati sambhajinagar",
    "chattrapati sambhajinagar": "chhatrapati sambhajinagar", "amarawati": "amravati", "gondiya": "gondia", "pune city": "pune",
}

PRIOR_FLEXIBILITY = -0.4  # % change in price per 1% more local supply, used until the data says otherwise
# Starting values by crop group (price flexibility of perishables is high, MSP-backed grains low).
PRIOR_BY_CROP = {"tomato": -1.0, "potato": -0.6, "onion": -0.9, "pigeon_pea": -0.45, "chickpea": -0.4, "soybean": -0.35, "groundnut": -0.35, "cotton": -0.3,
                 "maize": -0.3, "sorghum": -0.25, "pearl_millet": -0.25, "wheat": -0.2, "rice": -0.2}


def norm_district(name: str | None) -> str:
    key = " ".join((name or "").lower().replace("district", "").split())
    return DISTRICT_ALIASES.get(key, key)


def _csv(name: str) -> list[dict[str, str]]:
    path = DATA / name
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(line for line in fh if not line.startswith("#")))


@lru_cache
def reference() -> dict[str, Any]:
    path = DATA / "reference.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@lru_cache
def district_prices() -> dict[tuple[str, str], dict[tuple[int, int], float]]:
    out: dict[tuple[str, str], dict[tuple[int, int], float]] = {}
    for row in _csv("agmarknet_district_monthly.csv"):
        out.setdefault((norm_district(row["district"]), row["crop"]), {})[(int(row["year"]), int(row["month"]))] = float(row["modal_price_rs_qtl"])
    return out


@lru_cache
def market_rows() -> dict[tuple[str, str], dict[str, dict[tuple[int, int], tuple[float | None, float | None]]]]:
    out: dict[tuple[str, str], dict[str, dict[tuple[int, int], tuple[float | None, float | None]]]] = {}
    for row in _csv("agmarknet_market_monthly.csv"):
        price = float(row["modal_price_rs_qtl"]) if row.get("modal_price_rs_qtl") else None
        arrivals = float(row["arrivals_t"]) if row.get("arrivals_t") else None
        markets = out.setdefault((norm_district(row["district"]), row["crop"]), {})
        markets.setdefault(row["market"].strip(), {})[(int(row["year"]), int(row["month"]))] = (price, arrivals)
    return out


@lru_cache
def apy() -> dict[tuple[str, str, str], dict[int, tuple[float, float]]]:
    """(district, crop, season) -> {crop year: (area ha, yield kg/ha)}."""
    out: dict[tuple[str, str, str], dict[int, tuple[float, float]]] = {}
    for row in _csv("upag_apy_district.csv"):
        if not row.get("area_ha") or not row.get("yield_kg_ha"):
            continue
        area, yld = float(row["area_ha"]), float(row["yield_kg_ha"])
        if area > 0 and yld > 0:
            out.setdefault((norm_district(row["district"]), row["crop"], row["season"]), {})[int(row["crop_year"])] = (area, yld)
    # Maharashtra Agriculture Department rows fill only years UPAg has not published yet (2025-26 provisional).
    for row in _csv("state_apy_district.csv"):
        area, yld = float(row["area_ha"] or 0), float(row["yield_kg_ha"] or 0)
        key = (norm_district(row["district"]), row["crop"], row["season"])
        if area > 0 and yld > 0 and int(row["crop_year"]) not in out.get(key, {}):
            out.setdefault(key, {})[int(row["crop_year"])] = (area, yld)
            PROVISIONAL.add((*key, int(row["crop_year"])))
    return out


PROVISIONAL: set[tuple[str, str, str, int]] = set()


@lru_cache
def india_yield() -> dict[str, tuple[int, float]]:
    """crop -> (latest crop year, all-India yield kg/ha)."""
    out: dict[str, tuple[int, float]] = {}
    for row in _csv("upag_all_india_yield.csv"):
        year = int(row["crop_year"])
        if row["crop"] not in out or year > out[row["crop"]][0]:
            out[row["crop"]] = (year, float(row["yield_kg_ha"]))
    return out


def covered_districts() -> set[str]:
    from .settings import get_settings
    return {norm_district(d) for d in get_settings().market_districts.split(",") if d.strip()}


def is_covered(district: str | None) -> bool:
    return norm_district(district) in covered_districts()


# ---------------------------------------------------------------- calendar


def season_calendar(crop: str, season: str) -> dict[str, Any] | None:
    return CALENDAR.get((crop, season))


def next_sowing_year(season: str, crop: str, today: date | None = None) -> int:
    """Year of the next sowing of this crop in this season (this year if its sowing month is still ahead,
    or less than a month past)."""
    today = today or date.today()
    cal = season_calendar(crop, season) or {"sow": 6}
    return today.year if today.month <= cal["sow"] + 1 else today.year + 1


def harvest_months(crop: str, season: str, sow_year: int) -> list[tuple[int, int]]:
    """(year, month) of the harvest window for a crop sown in `sow_year`."""
    cal = season_calendar(crop, season)
    if not cal:
        return []
    year = sow_year + cal["offset"]
    out, previous = [], None
    for month in cal["harvest"]:
        if previous is not None and month < previous:
            year += 1
        out.append((year, month))
        previous = month
    return out


# ---------------------------------------------------------------- prices


def _window_mean(series: dict[tuple[int, int], float], months: Iterable[tuple[int, int]]) -> float | None:
    values = [series[m] for m in months if m in series]
    return sum(values) / len(values) if len(values) >= max(1, len(list(months)) // 2) else None


def msp_for(crop: str, year: int) -> float | None:
    history = (reference().get("msp_history") or {}).get(crop) or {}
    if str(year) in history:
        return float(history[str(year)])
    years = sorted(int(y) for y in history if y.isdigit() and int(y) <= year)
    return float(history[str(years[-1])]) if years else None


def past_harvest_prices(district: str, crop: str, season: str, seasons: int = 5, today: date | None = None) -> list[dict[str, Any]]:
    """Average district mandi price in each of the last completed harvest windows, newest first."""
    today = today or date.today()
    series = district_prices().get((norm_district(district), crop), {})
    out = []
    sow_year = next_sowing_year(season, crop, today) - 1
    while len(out) < seasons and sow_year >= 2013:
        window = harvest_months(crop, season, sow_year)
        if window and window[-1] < (today.year, today.month):
            price = _window_mean(series, window)
            if price is not None:
                sell_year = window[0][0]
                out.append({
                    "sow_year": sow_year, "label": _season_label(season, sow_year), "price": round(price, 0),
                    "months": [f"{y}-{m:02d}" for y, m in window], "msp": msp_for(crop, sell_year),
                })
        sow_year -= 1
    return out


def _season_label(season: str, sow_year: int) -> str:
    return f"{season.title()} {sow_year}" if season != "rabi" else f"Rabi {sow_year}-{str(sow_year + 1)[-2:]}"


def monthly_profile(district: str, crop: str, years: int = 5, today: date | None = None) -> list[dict[str, Any]]:
    """Average price per calendar month over recent years, relative to the yearly mean (1.0 = average)."""
    today = today or date.today()
    series = district_prices().get((norm_district(district), crop), {})
    ratios: dict[int, list[float]] = {}
    for year in range(today.year - years, today.year):
        values = {m: series[(year, m)] for m in range(1, 13) if (year, m) in series}
        if len(values) < 8:
            continue
        mean = sum(values.values()) / len(values)
        for month, value in values.items():
            ratios.setdefault(month, []).append(value / mean)
    return [{"month": m, "index": round(sum(ratios[m]) / len(ratios[m]), 3)} for m in sorted(ratios)]


def recent_prices(district: str, crop: str, months: int = 24) -> list[dict[str, Any]]:
    series = district_prices().get((norm_district(district), crop), {})
    keys = sorted(series)[-months:]
    return [{"month": f"{y}-{m:02d}", "price": round(series[(y, m)], 0)} for y, m in keys]


@lru_cache
def price_flexibility(crop: str, season: str) -> dict[str, float]:
    """How much the harvest price moved with district production, estimated across every district and
    year in the data: log(price / district median) on log(production / district median), shrunk towards
    PRIOR_FLEXIBILITY when there are few points."""
    xs, ys = [], []
    infl = reference().get("price_inflation_per_year", 0.04)
    for (district, c, s), years in apy().items():
        if c != crop or s != season:
            continue
        series = district_prices().get((district, crop), {})
        points = []
        for year, (area, yld) in years.items():
            price = _window_mean(series, harvest_months(crop, season, year))
            if price:
                window_year = harvest_months(crop, season, year)[0][0]
                points.append((math.log(area * yld), math.log(price / (1 + infl) ** (window_year - 2013))))
        if len(points) < 4:
            continue
        mx = statistics.median(p[0] for p in points)
        my = statistics.median(p[1] for p in points)
        xs += [p[0] - mx for p in points]
        ys += [p[1] - my for p in points]
    prior = PRIOR_BY_CROP.get(crop, PRIOR_FLEXIBILITY)
    n = len(xs)
    if n < 8:
        return {"value": prior, "points": n, "estimated": 0.0, "prior": prior}
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    var = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / var if var else prior
    # District output barely moves prices that are set nationally, so the district estimate is weak
    # evidence about crowding at the local mandi; it is given at most half the weight.
    weight = min(0.5, n / (n + 40))
    value = max(-1.5, min(0.0, weight * slope + (1 - weight) * prior))
    return {"value": round(value, 3), "points": n, "estimated": round(slope, 3), "prior": prior}


# ---------------------------------------------------------------- regional supply


def apy_trend(district: str, crop: str, season: str) -> dict[str, Any] | None:
    """Latest district area for this crop against the average of the five years before it."""
    years = apy().get((norm_district(district), crop, season))
    if not years:
        return None
    latest = max(years)
    before = [years[y][0] for y in range(latest - 5, latest) if y in years]
    if not before:
        return None
    avg = sum(before) / len(before)
    total_latest = sum(v[latest][0] for (d, c, s), v in apy().items() if d == norm_district(district) and s == season and latest in v)
    return {
        "latest_year": latest, "area_ha": round(years[latest][0]), "avg_area_ha": round(avg),
        "change": round(years[latest][0] / avg - 1, 3),
        "district_share": round(years[latest][0] / total_latest, 3) if total_latest else None,
    }


def crowding(district: str, crop: str, season: str, plans: list[dict[str, Any]], taluka: str | None = None) -> dict[str, Any]:
    """How crowded this crop looks this season: nearby KISANAI farmers' plans compared with the district's
    usual crop mix (UPAg), and the district's latest area trend."""
    trend = apy_trend(district, crop, season)
    def count(items):
        return len(items), sum(1 for p in items if p.get("crop") == crop)
    district_total, district_same = count(plans)
    taluka_items = [p for p in plans if taluka and (p.get("taluka") or "").lower() == taluka.lower()]
    taluka_total, taluka_same = count(taluka_items)
    usual_share = (trend or {}).get("district_share") or ((reference().get("estimates") or {}).get(crop) or {}).get("usual_share")
    # Platform signal: share of nearby plans for this crop vs its usual share of the district's area.
    x_platform, weight = 0.0, 0.0
    total, same = (taluka_total, taluka_same) if taluka_total >= 10 else (district_total, district_same)
    if total and usual_share:
        share = (same + 0.5) / (total + 1)
        x_platform = math.log(share / max(usual_share, 0.01))
        weight = total / (total + 15)
    x_trend = math.log(1 + trend["change"]) if trend else 0.0
    # Capped: a handful of plans should nudge the outlook, not swing it.
    supply = max(-0.4, min(0.4, weight * x_platform + (1 - weight) * 0.5 * x_trend))
    level = "high" if supply > 0.15 else "low" if supply < -0.15 else "normal"
    demo = sum(1 for p in plans if p.get("source") == "demo")
    return {
        "level": level, "supply_shift": round(supply, 3), "platform_weight": round(weight, 2),
        "taluka": taluka, "taluka_farms": taluka_total, "taluka_same_crop": taluka_same,
        "district_farms": district_total, "district_same_crop": district_same, "sample_entries": demo,
        "usual_share": usual_share, "apy_trend": trend,
    }


# ---------------------------------------------------------------- outlook and simulation


@dataclass
class Assumptions:
    area_ha: float
    price_override: float | None = None
    cost_per_ha_override: float | None = None
    yield_override_kg_ha: float | None = None
    use_msp_floor: bool = False
    distance_km: float | None = None
    transport_rs_per_qtl_km: float | None = None


def price_forecast(district: str, crop: str, season: str, lookback: int, supply_shift: float, today: date | None = None) -> dict[str, Any] | None:
    today = today or date.today()
    sow_year = next_sowing_year(season, crop, today)
    window = harvest_months(crop, season, sow_year)
    if crop in FRP_CROPS:
        frp = msp_for(crop, window[0][0]) if window else None
        return None if frp is None else {
            "expected": frp, "low": frp, "high": frp, "sigma": 0.0, "basis": "frp", "sell_months": [f"{y}-{m:02d}" for y, m in window],
            "msp": frp, "flexibility": {"value": 0.0, "points": 0, "estimated": 0.0}, "past": [], "below_msp_seasons": 0,
        }
    past = past_harvest_prices(district, crop, season, max(lookback, 6), today)
    if not past:
        return None
    from .forecast import price_backtest, price_forecast_at
    series = district_prices().get((norm_district(district), crop), {})
    sell_year = window[0][0]
    infl = reference().get("price_inflation_per_year", 0.04)
    model = price_forecast_at(series, (today.year, today.month), window)
    if model:
        base, method = model["value"], "seasonal_decomposition"
    else:  # too little monthly history: inflation-adjusted average of past harvest prices
        adjusted = [p["price"] * (1 + infl) ** (sell_year - int(p["months"][0][:4])) for p in past]
        base, method = 0.5 * adjusted[0] + 0.5 * statistics.median(adjusted[:lookback]), "past_harvest_average"
    # Back-test: forecast each of the last six harvests as if standing at its sowing month.
    cal = season_calendar(crop, season)
    windows = [(p["label"], (p["sow_year"], cal["sow"]), [tuple(map(int, k.split("-"))) for k in p["months"]]) for p in past[:6]]
    backtest = price_backtest(series, windows)
    if backtest["log_rmse"] is not None and len(backtest["seasons"]) >= 3:
        sigma = max(0.08, min(0.6, backtest["log_rmse"]))
    else:
        logs = [math.log(p["price"]) for p in past]
        sigma = max(0.08, min(0.6, statistics.pstdev(logs))) if len(logs) >= 3 else 0.2
    flex = price_flexibility(crop, season)
    expected = base * math.exp(flex["value"] * supply_shift)
    msp = msp_for(crop, sell_year)
    below = sum(1 for p in past[:lookback] if p.get("msp") and p["price"] < p["msp"])
    path = [{"month": f"{y}-{m:02d}", "price": round(v * math.exp(flex["value"] * supply_shift))}
            for (y, m), v in sorted((model or {}).get("path", {}).items())]
    return {
        "expected": round(expected), "low": round(expected * math.exp(-1.2816 * sigma)), "high": round(expected * math.exp(1.2816 * sigma)),
        "sigma": round(sigma, 3), "basis": "mandi", "method": method, "sell_months": [f"{y}-{m:02d}" for y, m in window],
        "base_before_crowding": round(base), "drift_per_year": round((model or {}).get("drift_per_year", 0.0), 3),
        "seasonal": (model or {}).get("seasonal"), "path": path, "backtest": backtest,
        "msp": msp, "flexibility": flex, "past": past[:lookback], "below_msp_seasons": below, "inflation_per_year": infl,
    }


def yield_model(district: str, crop: str, season: str, water_access: str, soil_score: float | None, dryspell: str | None,
                target_year: int | None = None) -> dict[str, Any] | None:
    """Expected yield (kg/ha of what is sold) and its spread, from the district's recent years."""
    ref = reference()
    years = apy().get((norm_district(district), crop, season))
    if not years and crop in FRP_CROPS:  # UPAg records sugarcane under one season
        years = next((v for (d, c, _s), v in apy().items() if d == norm_district(district) and c == crop), None)
    estimate = (ref.get("estimates") or {}).get(crop)
    trend = None
    if years:
        from .forecast import yield_forecast
        target = target_year or max(years) + 1
        trend = yield_forecast({y: v[1] for y, v in years.items()}, target)
        values = [h["kg_ha"] for h in trend["history"][-6:]] if trend else [v[1] for v in years.values()]
        mean = trend["value"] if trend else statistics.median(values)
        # Spread: the back-test error when there is one, else the year-to-year variation.
        cv = (trend or {}).get("rmse_rel") or (statistics.pstdev(values) / statistics.mean(values) if len(values) >= 3 else 0.2)
        provisional = any((norm_district(district), crop, season, y) in PROVISIONAL for y in years)
        source = f"District yield trend {min(years)}-{str(max(years) + 1)[-2:]} (UPAg" + (", 2025-26 State provisional)" if provisional else ")")
        is_estimate = False
    elif estimate and estimate.get("yield_kg_ha"):
        mean, cv, source, is_estimate = float(estimate["yield_kg_ha"]), float(estimate.get("yield_cv", 0.25)), estimate.get("yield_note", "Reference estimate"), True
    else:
        return None
    if crop == "cotton":
        mean /= ref.get("ginning_outturn", 0.34)  # lint -> kapas
    # The district average mixes irrigated and rainfed fields.
    water_factor = {"rainfed": 0.9, "supplemental_irrigation": 1.0, "irrigated": 1.12}.get(water_access, 1.0)
    soil_factor = 0.85 + 0.15 * soil_score if soil_score is not None else 1.0
    cv = max(0.1, min(0.5, cv)) * (1.3 if dryspell == "high" else 1.0)
    history = None
    if trend:
        scale = 1 / ref.get("ginning_outturn", 0.34) if crop == "cotton" else 1.0
        history = [{"year": h["year"], "kg_ha": round(h["kg_ha"] * scale)} for h in trend["history"]]
    return {"kg_ha": round(mean * water_factor * soil_factor), "district_kg_ha": round(mean), "cv": round(cv, 3),
            "water_factor": water_factor, "soil_factor": round(soil_factor, 3), "source": source, "estimate": is_estimate,
            "method": "damped_trend" if trend else "reference", "history": history,
            "trend_per_year": (trend or {}).get("trend_per_year"), "backtest": (trend or {}).get("backtest"), "mape": (trend or {}).get("mape")}


def cost_per_ha(crop: str) -> dict[str, Any] | None:
    ref = reference()
    cost = (ref.get("cost_a2fl_rs_qtl") or {}).get(crop)
    if cost:
        year, kg_ha = india_yield().get(crop, (None, None))
        if kg_ha:
            if crop == "cotton":
                kg_ha /= ref.get("ginning_outturn", 0.34)
            return {"rs_ha": round(cost["value"] * kg_ha / 100), "rs_qtl": cost["value"], "basis": f"CACP A2+FL cost, {cost['year']}",
                    "yield_year": year, "estimate": False}
    estimate = (ref.get("estimates") or {}).get(crop) or {}
    if estimate.get("cost_rs_ha"):
        return {"rs_ha": float(estimate["cost_rs_ha"]), "rs_qtl": None, "basis": estimate.get("cost_note", "Reference estimate"), "estimate": True}
    return None


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def simulate(price: dict[str, Any], yld: dict[str, Any], cost: dict[str, Any] | None, a: Assumptions, runs: int = 2000, seed: int = 7) -> dict[str, Any]:
    """Monte Carlo of production, revenue, cost and profit for the farmer's area."""
    rng = random.Random(seed)
    yield_mean = a.yield_override_kg_ha or yld["kg_ha"]
    yield_sigma = math.sqrt(math.log(1 + yld["cv"] ** 2))
    price_mean = a.price_override or price["expected"]
    price_sigma = 0.0 if a.price_override else price["sigma"]
    floor = price.get("msp") if a.use_msp_floor else None
    cost_ha = a.cost_per_ha_override if a.cost_per_ha_override is not None else (cost or {}).get("rs_ha")
    rate = a.transport_rs_per_qtl_km if a.transport_rs_per_qtl_km is not None else reference().get("transport_rs_per_qtl_km", 0.6)
    transport_qtl = (a.distance_km or 0) * rate
    production, revenue, profit, prices = [], [], [], []
    for _ in range(runs):
        y = yield_mean * math.exp(yield_sigma * rng.gauss(0, 1) - yield_sigma ** 2 / 2)
        p = price_mean * math.exp(price_sigma * rng.gauss(0, 1) - price_sigma ** 2 / 2)
        if floor:
            p = max(p, floor)
        qtl = y * a.area_ha / 100
        rev = qtl * (p - transport_qtl)
        production.append(qtl)
        revenue.append(rev)
        prices.append(p)
        if cost_ha is not None:
            profit.append(rev - cost_ha * a.area_ha)

    def band(values):
        return {"p10": round(_percentile(values, 0.1)), "p50": round(_percentile(values, 0.5)), "p90": round(_percentile(values, 0.9))}

    total_cost = round(cost_ha * a.area_ha) if cost_ha is not None else None
    expected_qtl = yield_mean * a.area_ha / 100
    result = {
        "runs": runs, "area_ha": round(a.area_ha, 3),
        "production_qtl": {k: round(v / 1, 1) for k, v in {q: _percentile(production, x) for q, x in (("p10", .1), ("p50", .5), ("p90", .9))}.items()},
        "price_rs_qtl": band(prices), "revenue_rs": band(revenue), "cost_rs": total_cost,
        "profit_rs": band(profit) if profit else None,
        "loss_probability": round(sum(1 for v in profit if v < 0) / len(profit), 3) if profit else None,
        "breakeven_price_rs_qtl": round(total_cost / expected_qtl + transport_qtl) if total_cost is not None and expected_qtl else None,
        "transport_rs_qtl": round(transport_qtl, 1),
        "inputs": {"yield_kg_ha": round(yield_mean), "price_rs_qtl": round(price_mean), "cost_rs_ha": cost_ha, "msp_floor": floor},
    }
    if profit:
        low, high = _percentile(profit, 0.02), _percentile(profit, 0.98)
        step = (high - low) / 12 or 1
        bins = [0] * 12
        for v in profit:
            bins[min(11, max(0, int((v - low) / step)))] += 1
        result["histogram"] = [{"from": round(low + i * step), "to": round(low + (i + 1) * step), "share": round(c / len(profit), 3)} for i, c in enumerate(bins)]
    return result


def best_sell_month(district: str, crop: str, season: str) -> dict[str, Any] | None:
    """For storable crops: the month within six months of harvest that has paid best on average."""
    if crop not in STORABLE:
        return None
    cal = season_calendar(crop, season)
    profile = {p["month"]: p["index"] for p in monthly_profile(district, crop)}
    if not cal or not profile:
        return None
    first = cal["harvest"][0]
    candidates = [((first - 1 + k) % 12) + 1 for k in range(0, 7)]
    harvest_index = sum(profile.get(m, 1.0) for m in cal["harvest"]) / len(cal["harvest"])
    best = max((m for m in candidates if m in profile), key=lambda m: profile[m], default=None)
    if best is None:
        return None
    return {"month": best, "gain_vs_harvest": round(profile[best] / harvest_index - 1, 3)}
