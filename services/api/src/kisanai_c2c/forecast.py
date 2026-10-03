"""Forecasts used by the market model, with their own back-tests.

Price: classical multiplicative decomposition of the monthly district mandi series, as used for
agricultural price outlooks (e.g. seasonal indices in AGMARKNET/NHRDF price analyses):
  - seasonal index s[m]: average of price / centred 12-month mean for each calendar month;
  - level: average of the last three de-seasonalised prices;
  - drift: least-squares slope of log de-seasonalised price over the last 36 months, halved (damped)
    and capped at +/-15 % a year;
  forecast(month t) = level x exp(drift x months ahead) x s[t].
Only data before the forecast date is used, so the back-test (forecast made at sowing time for each past
harvest, compared with what the mandi actually paid) is out-of-sample.

Yield: damped linear trend over the district's yearly yields (outlier years removed), back-tested by
forecasting each of the last years from the years before it.
"""
from __future__ import annotations

import math
import statistics
from typing import Iterable

Month = tuple[int, int]


def _i(m: Month) -> int:
    return m[0] * 12 + m[1] - 1


def _m(i: int) -> Month:
    return i // 12, i % 12 + 1


def seasonal_index(series: dict[Month, float], before: Month, years: int = 6) -> dict[int, float]:
    start = _i(before) - years * 12
    keys = sorted(k for k in series if start <= _i(k) < _i(before))
    ratios: dict[int, list[float]] = {}
    for k in keys:
        window = [series[_m(j)] for j in range(_i(k) - 6, _i(k) + 6) if _m(j) in series and _i(_m(j)) < _i(before)]
        if len(window) >= 8:
            ratios.setdefault(k[1], []).append(series[k] / (sum(window) / len(window)))
    index = {month: sum(v) / len(v) for month, v in ratios.items() if len(v) >= 2}
    if not index:
        return {}
    mean = sum(index.values()) / len(index)
    return {month: value / mean for month, value in index.items()}


def price_forecast_at(series: dict[Month, float], origin: Month, targets: Iterable[Month]) -> dict | None:
    """Forecast the average price over `targets` using only months before `origin`."""
    targets = list(targets)
    history = sorted(k for k in series if _i(k) < _i(origin))
    if len(history) < 18 or not targets:
        return None
    s = seasonal_index(series, origin)
    deseason = {k: series[k] / s.get(k[1], 1.0) for k in history}
    recent = [k for k in history if _i(origin) - _i(k) <= 6][-3:]
    if not recent:
        return None
    level = sum(deseason[k] for k in recent) / len(recent)
    window = [k for k in history if _i(origin) - _i(k) <= 36]
    slope = 0.0
    if len(window) >= 12:
        xs = [_i(k) for k in window]
        ys = [math.log(deseason[k]) for k in window]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        var = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var if var else 0.0
    slope = max(-0.15 / 12, min(0.15 / 12, 0.5 * slope))
    last = _i(recent[-1])
    path = {t: level * math.exp(slope * (_i(t) - last)) * s.get(t[1], 1.0) for t in targets}
    return {"value": sum(path.values()) / len(path), "level": level, "drift_per_year": slope * 12,
            "seasonal": {t[1]: round(s.get(t[1], 1.0), 3) for t in targets}, "path": path}


def price_backtest(series: dict[Month, float], windows: list[tuple[str, Month, list[Month]]]) -> dict:
    """windows: (label, forecast origin, harvest months). Returns per-season errors, MAPE and log-RMSE."""
    rows = []
    for label, origin, months in windows:
        actual = [series[k] for k in months if k in series]
        if len(actual) < max(1, len(months) // 2):
            continue
        fc = price_forecast_at(series, origin, months)
        if not fc:
            continue
        a = sum(actual) / len(actual)
        rows.append({"season": label, "forecast": round(fc["value"]), "actual": round(a), "error": round(fc["value"] / a - 1, 3)})
    if not rows:
        return {"seasons": [], "mape": None, "log_rmse": None}
    mape = sum(abs(r["error"]) for r in rows) / len(rows)
    rmse = math.sqrt(sum(math.log(1 + r["error"]) ** 2 for r in rows) / len(rows))
    return {"seasons": rows, "mape": round(mape, 3), "log_rmse": round(rmse, 3)}


def _trend(points: list[tuple[int, float]]) -> tuple[float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    var = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var if var else 0.0
    return slope, my - slope * mx


def yield_forecast_at(points: list[tuple[int, float]], target_year: int) -> float | None:
    """Damped trend: mean of the last three years plus half the fitted trend, kept within 70-130 % of the median."""
    pts = sorted(p for p in points if p[0] < target_year)[-10:]
    if len(pts) < 3:
        return None
    recent = pts[-3:]
    base = sum(p[1] for p in recent) / 3
    centre = sum(p[0] for p in recent) / 3
    slope, _ = _trend(pts) if len(pts) >= 5 else (0.0, 0.0)
    value = base + 0.5 * slope * (target_year - centre)
    mid = statistics.median(p[1] for p in pts)
    return max(0.7 * mid, min(1.3 * mid, value))


def yield_forecast(years: dict[int, float], target_year: int) -> dict | None:
    if not years:
        return None
    mid = statistics.median(years.values())
    clean = sorted((y, v) for y, v in years.items() if 0.33 * mid <= v <= 2.5 * mid)
    value = yield_forecast_at(clean, target_year)
    if value is None:
        return None
    tests = []
    for year, actual in clean[-4:]:
        fc = yield_forecast_at([p for p in clean if p[0] < year], year)
        if fc:
            tests.append({"year": year, "forecast": round(fc), "actual": round(actual), "error": round(fc / actual - 1, 3)})
    slope, intercept = _trend(clean[-10:]) if len(clean) >= 5 else (0.0, statistics.mean(v for _, v in clean))
    errors = [t["error"] for t in tests]
    return {
        "value": value, "history": [{"year": y, "kg_ha": round(v)} for y, v in clean],
        "trend_per_year": round(slope, 1), "backtest": tests,
        "mape": round(sum(abs(e) for e in errors) / len(errors), 3) if errors else None,
        "rmse_rel": round(math.sqrt(sum(e * e for e in errors) / len(errors)), 3) if errors else None,
    }
