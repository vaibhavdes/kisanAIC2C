"""Crop recommendation engine (regional-pack or global-baseline mode).

For every candidate crop the engine answers: can it be sown now or soon, will the climate over
its growing cycle suit it, can the farm supply its water, does the soil suit it, is it wise for
the local groundwater, and how regenerative is it after the previous crop. Every factor records
the data it used and whether that data was measured, farmer-provided, estimated, forecast or
satellite-derived.

Methods:
  * Temperature suitability over the crop cycle: FAO EcoCrop (Hijmans et al.) trapezoid on
    monthly mean temperature with the killing-temperature (frost) rule.
  * Water: seasonal balance - crop water use (monthly reference ET x crop factor) against
    effective rain, stored soil moisture carried over from the preceding wet months, and the
    farm's irrigation capacity.
  * Soil pH / texture / salinity from farm tests, the farmer's soil type or SoilGrids.
  * Sowing windows and regulations from the region's agronomy pack; outside pack regions the
    sowing month is chosen from climate suitability.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from .knowledge import crop_catalog, crop_name, find_district, normalize_crop, practice_name, season_for_month, window_dates
from .models import (
    CropOption, CropRecommendationResult, DataSource, DecisionFactor, Farm, LandProfile, PackRef, PracticeRef,
    SoilTest, SowingWindow,
)
from .operations import latest_snapshot, satellite_values
from .soil import effective_soil

HORIZON_DAYS = 60
IRRIGATION_CAPACITY_MM = {"rainfed": 0.0, "supplemental_irrigation": 150.0, "irrigated": 10_000.0}
STORAGE_MM = {"heavy": 150.0, "medium": 100.0, "light": 50.0}
CROP_FACTOR = {"cereal": 0.85, "millet": 0.75, "pulse": 0.75, "oilseed": 0.8, "fibre": 0.85, "sugar": 1.05,
               "tuber": 0.85, "vegetable": 0.85, "fodder": 0.9, "green_manure": 0.7}
CROP_NEUTRAL_PRACTICES = {"reduced-disturbance", "residue-retention", "field-scouting"}
RICE_EXTRA_MM = 250.0  # puddling and percolation losses on top of crop evapotranspiration
EFFECTIVE_RAIN = 0.8
GROUNDWATER_PENALTY = {
    ("high", "over_exploited"): 0.3, ("high", "critical"): 0.45, ("high", "semi_critical"): 0.7,
    ("medium", "over_exploited"): 0.75, ("medium", "critical"): 0.85,
}
GROUP_OF_PREVIOUS = {"pulse": "legume", "green_manure": "legume", "fodder": "other"}


# --- small numeric helpers ---------------------------------------------------------------

def trapezoid(value: float, abs_min: float | None, opt_min: float | None, opt_max: float | None, abs_max: float | None) -> float | None:
    if None in (abs_min, opt_min, opt_max, abs_max):
        return None
    if value <= abs_min or value >= abs_max:
        return 0.0
    if opt_min <= value <= opt_max:
        return 1.0
    if value < opt_min:
        return (value - abs_min) / max(opt_min - abs_min, 1e-6)
    return (abs_max - value) / max(abs_max - opt_max, 1e-6)


def cycle_month_weights(start: date, days: int) -> list[tuple[int, float]]:
    """(month, fraction of that month covered) for each calendar month the cycle touches."""
    weights: dict[tuple[int, int], int] = {}
    for offset in range(days):
        day = start + timedelta(days=offset)
        weights[(day.year, day.month)] = weights.get((day.year, day.month), 0) + 1
    out = []
    for (year, month), count in weights.items():
        out.append((month, count / calendar.monthrange(year, month)[1]))
    return out


def _status(score: float | None, blocking_below: float = 0.3) -> str:
    if score is None:
        return "info"
    if score < blocking_below:
        return "blocking"
    if score < 0.6:
        return "limiting"
    if score < 0.85:
        return "fair"
    return "good"


# --- engine ------------------------------------------------------------------------------

class RecommendationEngine:
    def __init__(
        self,
        farm: Farm,
        *,
        pack: dict[str, Any] | None,
        pack_ref: PackRef | None,
        land: LandProfile | None,
        soil_test: SoilTest | None,
        evidence: list[dict[str, Any]],
        locale: str = "en-IN",
        today: date | None = None,
    ):
        self.farm = farm
        self.pack = pack
        self.pack_ref = pack_ref
        self.land = land
        self.soil_test = soil_test
        self.evidence = evidence
        self.locale = locale
        self.today = today or date.today()
        self.soil = effective_soil(farm.soil_type, soil_test, land.soil if land else None, farm.country_code)
        self.district = find_district(pack, farm.district)
        self.groundwater = (self.district or {}).get("groundwater_category") or ((pack or {}).get("groundwater") or {}).get("category") or "unknown"
        self.previous = normalize_crop(farm.previous_crop) if farm.previous_crop else ""
        self.satellite = satellite_values(evidence)
        self.climate = {month.month: month for month in land.climate} if land else {}

    # public ---------------------------------------------------------------------------
    def run(self) -> CropRecommendationResult:
        catalog = crop_catalog()
        if self.pack:
            candidates = [(entry["crop_id"], entry) for entry in self.pack["crops"] if entry["crop_id"] in catalog]
        else:
            candidates = [(crop_id, None) for crop_id, crop in catalog.items() if crop["group"] not in {"green_manure", "fodder"}]

        options = [self._evaluate(crop_id, entry) for crop_id, entry in candidates]
        sow_now = sorted([o for o in options if o.eligible and o.sowing and o.sowing.status == "open"], key=lambda o: o.rank_score or 0, reverse=True)
        upcoming = sorted([o for o in options if o.eligible and o.sowing and o.sowing.status == "upcoming"],
                          key=lambda o: (o.sowing.days_until_start, -(o.rank_score or 0)))
        not_suitable = sorted([o for o in options if o not in sow_now and o not in upcoming], key=lambda o: o.suitability, reverse=True)

        notes: list[str] = []
        if not self.pack:
            notes.append("No regional agronomy pack is active for this location; sowing months come from climate suitability (global baseline). Local calendars and regulations may differ.")
        elif self.pack_ref and self.pack_ref.review_status != "reviewed":
            notes.append("The regional pack is curated from published packages of practices and is awaiting review by a state expert.")
        if not self.land:
            notes.append("Climate normals were unavailable, so seasonal temperature and water checks are limited.")

        return CropRecommendationResult(
            farm_id=self.farm.id, farm_name=self.farm.name, district=self.farm.district, state_name=self.farm.state_name,
            country_code=self.farm.country_code,
            subdivision_code=self.pack["region"]["subdivision_code"] if self.pack else None,
            locale=self.locale, generated_on=self.today, horizon_days=HORIZON_DAYS,
            knowledge_mode="regional_pack" if self.pack else "global_baseline",
            pack=self.pack_ref,
            context=self._context(),
            data_sources=self._sources(),
            sow_now=sow_now, upcoming=upcoming, not_suitable=not_suitable, notes=notes,
        )

    # evaluation -----------------------------------------------------------------------
    def _evaluate(self, crop_id: str, pack_entry: dict[str, Any] | None) -> CropOption:
        crop = crop_catalog()[crop_id]
        eco = crop["ecocrop"]
        factors: list[DecisionFactor] = []
        rejections: list[tuple[str, str]] = []

        sowing = self._sowing_window(crop, pack_entry)
        irrigated_only = bool(pack_entry) and self.farm.water_access == "rainfed" and all(w["irrigation_required"] for w in pack_entry["sowing_windows"])
        if irrigated_only:
            factors.append(DecisionFactor(id="sowing_window", status="blocking", source="regional", params={"needs_irrigation": True},
                                          message="Grown only with assured irrigation in this region; the farm is rainfed."))
            rejections.append(("needs_irrigation", "Grown only with assured irrigation in this region; the farm is rainfed."))
            return self._finish(crop_id, crop, factors, rejections, None, {}, None, None, None, None, None, None, None)
        if sowing is None:
            next_start = self._next_window_start(pack_entry)
            factors.append(DecisionFactor(id="sowing_window", status="blocking", source="regional" if pack_entry else "catalog",
                                          params={"next_start": next_start.isoformat() if next_start else None},
                                          message=f"Not a sowing time; next window opens {next_start:%d %b}." if next_start else "No suitable sowing time in the next 60 days."))
            rejections.append(("not_in_season", "Not a sowing window for this crop in the next 60 days."))
            start_date = next_start or self.today
        else:
            start_date = max(sowing.start, self.today)
            factors.append(DecisionFactor(
                id="sowing_window", status="good" if sowing.status == "open" else "info",
                source="regional" if sowing.source == "regional_pack" else "catalog",
                params={"start": sowing.start.isoformat(), "end": sowing.end.isoformat(), "status": sowing.status,
                        "days_until_start": sowing.days_until_start, "season": sowing.season, "label": sowing.label},
                message=(f"Sowing window open until {sowing.end:%d %b}." if sowing.status == "open"
                         else f"Sowing window opens {sowing.start:%d %b} (in {sowing.days_until_start} days).")))

        cycle = crop["cycle_days"]
        months = cycle_month_weights(start_date, cycle)

        temp_score = self._temperature(eco, months, factors)
        water_score, water = self._water(crop, eco, months, start_date, factors, sowing)
        ph_score = self._ph(eco, factors)
        texture_score = self._texture(eco, factors)
        salinity_score = self._salinity(eco, factors)
        gw_score = self._groundwater(crop, factors)
        rotation_score = self._rotation(crop_id, crop, factors)
        self._nutrients(crop, factors)
        self._field_state(factors, sowing)

        return self._finish(crop_id, crop, factors, rejections, sowing, water, temp_score, water_score, ph_score,
                            texture_score, salinity_score, gw_score, rotation_score)

    def _finish(self, crop_id, crop, factors, rejections, sowing, water, temp_score, water_score, ph_score,
                texture_score, salinity_score, gw_score, rotation_score) -> CropOption:
        measured_ph = self.soil["ph_source"] == "measured"
        for code, score, text in (
            ("temperature", temp_score, "Temperature over the growing cycle is outside the crop's tolerance."),
            ("water", water_score, "Rain, stored soil moisture and available irrigation cannot meet the crop's water need."),
            ("soil_ph", ph_score if measured_ph else None, "Measured soil pH is outside the crop's tolerance."),
        ):
            if score is not None and score < 0.3:
                rejections.append((code, text))
        if self.previous and self.previous == crop_id:
            rejections.append(("repeat_crop", "Same crop as last season; rotate to break pest and disease cycles."))

        limiting = [s for s in (temp_score, water_score, ph_score if measured_ph else None) if s is not None]
        secondary = [s for s in (texture_score, salinity_score, gw_score, rotation_score, None if measured_ph else ph_score) if s is not None]
        suitability = min(limiting) if limiting else 0.5
        if secondary:
            suitability = 0.75 * suitability + 0.25 * (sum(secondary) / len(secondary))
        suitability = round(max(0.0, min(1.0, suitability)), 3)
        regen = self._regenerative_score(crop_id, crop, gw_score)
        eligible = not rejections
        rank = round(0.75 * suitability + 0.25 * regen, 3) if eligible else None

        practices = self._practices(crop)
        measured_kinds = {"measured", "farmer", "forecast", "satellite", "regional"}
        coverage = round(sum(1 for f in factors if f.source in measured_kinds and f.status != "info") / max(1, sum(1 for f in factors if f.status != "info")), 2)

        return CropOption(
            crop=crop_id, crop_name=crop_name(crop_id, self.locale), scientific_name=crop["scientific_name"], group=crop["group"],
            eligible=eligible, suitability=suitability, regenerative_score=regen, rank_score=rank, sowing=sowing,
            water_need_mm=water.get("need"), water_available_mm=water.get("available"), irrigation_gap_mm=water.get("gap"),
            factors=factors, rejection_codes=[code for code, _ in rejections], rejection_reasons=[text for _, text in rejections],
            practices=practices, evidence_coverage=coverage,
        )

    def _sowing_window(self, crop: dict[str, Any], pack_entry: dict[str, Any] | None) -> SowingWindow | None:
        horizon = self.today + timedelta(days=HORIZON_DAYS)
        rainfed = self.farm.water_access == "rainfed"
        if pack_entry:
            regulation = next((r for r in (self.pack or {}).get("regulations", []) if r["crop_id"] == crop["id"]), None)
            best: SowingWindow | None = None
            for window in pack_entry["sowing_windows"]:
                if window["irrigation_required"] and rainfed:
                    continue
                start, end = window_dates(window, self.today)
                if regulation:
                    reg_start, _ = window_dates({"start": regulation["earliest_sowing"], "end": regulation["earliest_sowing"]}, start)
                    if reg_start.year == start.year and reg_start > start:
                        start = reg_start
                if start > horizon:
                    continue
                status = "open" if start <= self.today <= end else "upcoming"
                candidate = SowingWindow(season=window["season"], label=window.get("label"), start=start, end=end, status=status,
                                         days_until_start=max(0, (start - self.today).days),
                                         irrigation_required=window["irrigation_required"], source="regional_pack")
                if best is None or (candidate.status == "open" and best.status != "open") or (candidate.status == best.status and candidate.start < best.start):
                    best = candidate
            return best
        if not self.climate:
            return None
        # Global baseline: first start in the horizon whose cycle temperature suits the crop.
        for offset in (0, 15, 30, 45, 60):
            start = self.today + timedelta(days=offset)
            months = cycle_month_weights(start, crop["cycle_days"])
            score = self._temperature_score(crop["ecocrop"], months)
            if score is not None and score >= 0.6:
                end = start + timedelta(days=20)
                return SowingWindow(season=season_for_month(self.pack, start.month), label=None, start=start, end=end,
                                    status="open" if offset == 0 else "upcoming", days_until_start=offset,
                                    irrigation_required=False, source="climate_model")
        return None

    def _next_window_start(self, pack_entry: dict[str, Any] | None) -> date | None:
        if not pack_entry:
            return None
        rainfed = self.farm.water_access == "rainfed"
        starts = [window_dates(w, self.today)[0] for w in pack_entry["sowing_windows"] if not (w["irrigation_required"] and rainfed)]
        future = [start for start in starts if start > self.today]
        return min(future) if future else None

    def _temperature_score(self, eco: dict[str, Any], months: list[tuple[int, float]]) -> float | None:
        if not self.climate:
            return None
        scores = []
        for month, weight in months:
            clim = self.climate.get(month)
            if clim is None or weight < 0.3:
                continue
            score = trapezoid(clim.tmean_c, eco.get("tmin"), eco.get("topmn"), eco.get("topmx"), eco.get("tmax"))
            if score is None:
                return None
            if eco.get("ktmp") is not None and clim.tmin_c <= eco["ktmp"] + 4:
                score = 0.0
            scores.append(score)
        if not scores:
            return None
        if len(scores) > 7:
            # Long-duration crops (e.g. sugarcane) tolerate a slow-growth cool spell; frost months still score 0.
            return round(0.0 if 0.0 in scores and any(self._frost_months(eco, months)) else sum(scores) / len(scores), 3)
        return round(min(scores), 3)

    def _frost_months(self, eco: dict[str, Any], months: list[tuple[int, float]]) -> list[bool]:
        if eco.get("ktmp") is None:
            return [False]
        return [self.climate[m].tmin_c <= eco["ktmp"] + 4 for m, w in months if m in self.climate and w >= 0.3]

    def _temperature(self, eco, months, factors) -> float | None:
        score = self._temperature_score(eco, months)
        if score is None:
            factors.append(DecisionFactor(id="temperature", status="info", source="catalog", params={}, message="Climate normals unavailable."))
            return None
        temps = [self.climate[m].tmean_c for m, w in months if m in self.climate and w >= 0.3]
        frost = eco.get("ktmp") is not None and any(self.climate[m].tmin_c <= eco["ktmp"] + 4 for m, w in months if m in self.climate and w >= 0.3)
        factors.append(DecisionFactor(
            id="temperature", status=_status(score), score=score, source="estimated",
            params={"mean_min_c": min(temps), "mean_max_c": max(temps), "optimal_min_c": eco.get("topmn"), "optimal_max_c": eco.get("topmx"), "frost_risk": frost},
            message=f"Monthly mean temperature {min(temps):.0f}-{max(temps):.0f} C over the cycle; crop optimum {eco.get('topmn'):g}-{eco.get('topmx'):g} C" + (" (frost risk)." if frost else ".")))
        return score

    def _water(self, crop, eco, months, start, factors, sowing) -> tuple[float | None, dict[str, float]]:
        if not self.climate:
            factors.append(DecisionFactor(id="water", status="info", source="catalog", params={}, message="Climate normals unavailable."))
            return None, {}
        kc = CROP_FACTOR.get(crop["group"], 0.8) * (1.25 if crop["id"] == "rice" else 1.0)
        if any(self.climate[m].pet_mm is None for m, _ in months if m in self.climate):
            factors.append(DecisionFactor(id="water", status="info", source="catalog", params={}, message="Evapotranspiration normals unavailable."))
            return None, {}
        pet_total = sum(self.climate[m].pet_mm * w for m, w in months if m in self.climate)
        need = pet_total * kc + (RICE_EXTRA_MM if crop["id"] == "rice" else 0.0)
        rain = sum(self.climate[m].precip_mm * w for m, w in months if m in self.climate)
        # Stored moisture: surplus of the two months before sowing, capped by soil storage.
        texture = self.soil["texture"] or "medium"
        prior = [((start.month - k - 1) % 12) + 1 for k in range(2)]
        surplus = sum(max(0.0, self.climate[m].precip_mm - (self.climate[m].pet_mm or 0.0)) for m in prior if m in self.climate)
        stored = min(STORAGE_MM.get(texture, 100.0), surplus)
        capacity = IRRIGATION_CAPACITY_MM[self.farm.water_access]
        available_natural = rain * EFFECTIVE_RAIN + stored
        gap = max(0.0, need - available_natural)
        supplied = available_natural + min(gap, capacity)
        score = round(min(1.0, supplied / max(need, 1.0)), 3)
        excess = eco.get("rmax") is not None and rain > eco["rmax"] and crop["id"] != "rice"
        if excess and texture == "heavy":
            score = min(score, 0.5)
        details = {"need": round(need), "available": round(available_natural), "gap": round(gap)}
        if self.farm.water_access == "rainfed" and gap > 0:
            message = f"Needs about {details['need']} mm; rain and stored soil moisture give about {details['available']} mm (rainfed gap {details['gap']} mm)."
        elif gap > 0:
            message = f"Needs about {details['need']} mm; about {details['gap']} mm must come from irrigation."
        else:
            message = f"Expected rain and stored soil moisture (~{details['available']} mm) cover the crop's ~{details['need']} mm need."
        if excess:
            message += " Seasonal rain exceeds the crop's tolerance - waterlogging risk."
        factors.append(DecisionFactor(id="water", status=_status(score), score=score, source="estimated",
                                      params={**details, "stored_soil_moisture_mm": round(stored), "seasonal_rain_mm": round(rain),
                                              "water_access": self.farm.water_access, "excess_rain": excess},
                                      message=message))
        return score, details

    def _ph(self, eco, factors) -> float | None:
        ph = self.soil["ph"]
        if ph is None:
            return None
        score = trapezoid(ph, eco.get("phmin"), eco.get("phopmn"), eco.get("phopmx"), eco.get("phmax"))
        if score is None:
            return None
        score = round(score, 3)
        source = "measured" if self.soil["ph_source"] == "measured" else "estimated"
        status = _status(score) if source == "measured" else ("limiting" if score < 0.6 else _status(score))
        factors.append(DecisionFactor(id="soil_ph", status=status, score=score, source=source,
                                      params={"ph": ph, "optimal_min": eco.get("phopmn"), "optimal_max": eco.get("phopmx")},
                                      message=f"Soil pH {ph:.1f} ({'soil test' if source == 'measured' else 'SoilGrids estimate'}); crop optimum {eco.get('phopmn'):g}-{eco.get('phopmx'):g}."))
        return score

    def _texture(self, eco, factors) -> float | None:
        texture = self.soil["texture"]
        optimal, absolute = eco.get("texture_optimal") or [], eco.get("texture_absolute") or []
        if not texture or not (optimal or absolute):
            return None
        score = 1.0 if texture in optimal or "wide" in optimal else 0.7 if texture in absolute or "wide" in absolute else 0.4
        factors.append(DecisionFactor(id="soil_texture", status=_status(score), score=score,
                                      source="farmer" if self.soil["texture_source"] == "farmer" else "estimated",
                                      params={"texture": texture, "preferred": optimal},
                                      message=f"{texture.title()} soil; crop prefers {', '.join(optimal) or 'a range of'} soils."))
        return score

    def _salinity(self, eco, factors) -> float | None:
        ec = self.soil["ec_ds_m"]
        if ec is None or ec < 4:
            return None
        tolerant = "medium" in str(eco.get("salinity_optimal") or "") or "high" in str(eco.get("salinity_optimal") or "")
        score = 0.6 if tolerant else 0.3
        factors.append(DecisionFactor(id="salinity", status=_status(score), score=score, source="measured",
                                      params={"ec_ds_m": ec}, message=f"Soil EC {ec:g} dS/m is saline for this crop."))
        return score

    def _groundwater(self, crop, factors) -> float | None:
        water_class = crop["traits"]["water_class"]
        if self.farm.water_access == "rainfed" or self.groundwater in ("unknown", "safe"):
            return None
        penalty = GROUNDWATER_PENALTY.get((water_class, self.groundwater))
        if penalty is None:
            return None
        factors.append(DecisionFactor(id="groundwater", status=_status(penalty), score=penalty, source="regional",
                                      params={"category": self.groundwater, "water_class": water_class, "scope": "district" if self.district else "state"},
                                      message=f"Groundwater here is {self.groundwater.replace('_', '-')}; this is a {water_class}-water crop."))
        return penalty

    def _rotation(self, crop_id, crop, factors) -> float | None:
        if not self.previous:
            return None
        previous = crop_catalog().get(self.previous)
        prev_legume = bool(previous and previous["traits"]["n_fixing"])
        this_legume = crop["traits"]["n_fixing"]
        if self.previous == crop_id:
            score, code = 0.2, "repeat"
        elif prev_legume and not this_legume:
            score, code = 1.0, "after_legume"
        elif this_legume and not prev_legume:
            score, code = 1.0, "legume_break"
        elif previous and previous["group"] == crop["group"]:
            score, code = 0.6, "same_group"
        else:
            score, code = 0.85, "diverse"
        factors.append(DecisionFactor(id="rotation", status=_status(score), score=score, source="farmer",
                                      params={"previous_crop": self.previous, "previous_name": crop_name(self.previous, self.locale), "pattern": code},
                                      message={"repeat": "Same crop as last season - pest and disease carry-over.",
                                               "after_legume": "Follows a legume - benefits from residual nitrogen.",
                                               "legume_break": "A legume after a non-legume - rebuilds soil nitrogen and breaks pest cycles.",
                                               "same_group": "Same crop family as last season - limited rotation benefit.",
                                               "diverse": "Different crop family from last season - good diversity."}[code]))
        return score

    def _nutrients(self, crop, factors) -> None:
        if not self.soil["has_test"]:
            return
        n_rating, oc_rating = self.soil["nitrogen_rating"], self.soil["oc_rating"]
        if n_rating == "low":
            legume = crop["traits"]["n_fixing"]
            factors.append(DecisionFactor(id="nitrogen", status="good" if legume else "fair", source="measured",
                                          params={"rating": "low", "legume": legume},
                                          message="Soil nitrogen is low - " + ("this legume fixes its own nitrogen." if legume else "add compost/FYM or grow a legume first.")))
        if oc_rating == "low" and self.soil["oc_source"] == "measured":
            factors.append(DecisionFactor(id="organic_carbon", status="info", source="measured", params={"rating": "low"},
                                          message="Organic carbon is low - retain residue and add compost or green manure."))

    def _field_state(self, factors, sowing) -> None:
        if not self.satellite or sowing is None or sowing.status != "open" or self.farm.crop_status == "planted":
            return
        ndvi = self.satellite.get("ndvi")
        ndmi = self.satellite.get("ndmi")
        if isinstance(ndvi, (int, float)) and ndvi >= 0.45:
            factors.append(DecisionFactor(id="field_state", status="info", source="satellite", params={"ndvi": ndvi},
                                          message=f"Satellite shows active green cover (NDVI {ndvi:.2f}) - clear the standing crop or weeds before sowing."))
        elif isinstance(ndmi, (int, float)) and ndmi >= 0.1 and self.farm.water_access == "rainfed":
            factors.append(DecisionFactor(id="field_state", status="good", source="satellite", params={"ndmi": ndmi},
                                          message=f"Satellite moisture index (NDMI {ndmi:.2f}) suggests residual moisture for sowing."))

    def _regenerative_score(self, crop_id: str, crop: dict[str, Any], gw_score: float | None) -> float:
        traits = crop["traits"]
        nfix = 1.0 if traits["n_fixing"] else 0.4
        water = {"low": 1.0, "medium": 0.7, "high": 0.3}[traits["water_class"]]
        if gw_score is not None:
            water = min(water, gw_score)
        residue = {"high": 1.0, "medium": 0.7, "low": 0.4}[traits["residue"]]
        previous = crop_catalog().get(self.previous) if self.previous else None
        if not self.previous:
            diversity = 0.7
        elif self.previous == crop_id:
            diversity = 0.2
        elif previous and previous["group"] == crop["group"]:
            diversity = 0.6
        else:
            diversity = 1.0
        return round(0.3 * nfix + 0.3 * water + 0.2 * residue + 0.2 * diversity, 3)

    def _practices(self, crop: dict[str, Any]) -> list[PracticeRef]:
        priority = (self.pack or {}).get("priority_practices", [])
        ids = list(crop.get("practices", []))
        # Region-wide priority practices that suit any field crop (e.g. no-till in Paraná).
        ids += [pid for pid in priority if pid in CROP_NEUTRAL_PRACTICES]
        if self.soil["oc_rating"] == "low" and self.soil["oc_source"] == "measured":
            ids.append("compost-fym")
        # Broad bed and furrow is for heavy, waterlogging-prone soils, and only where the regional pack recommends it.
        ids = [pid for pid in ids if pid != "broad-bed-furrow" or "broad-bed-furrow" in priority]
        if self.soil["texture"] == "heavy" and crop["group"] in {"oilseed", "pulse", "fibre"} and "broad-bed-furrow" in priority:
            ids.append("broad-bed-furrow")
        ordered = [pid for pid in ids if pid in priority] + [pid for pid in ids if pid not in priority]
        seen: list[str] = []
        for pid in ordered:
            if pid not in seen:
                seen.append(pid)
        return [PracticeRef(id=pid, name=practice_name(pid, self.locale)) for pid in seen[:4]]

    # context --------------------------------------------------------------------------
    def _context(self) -> dict[str, Any]:
        annual = round(sum(m.precip_mm for m in self.land.climate)) if self.land else None
        return {
            "today": self.today.isoformat(),
            "season_now": season_for_month(self.pack, self.today.month),
            "water_access": self.farm.water_access,
            "previous_crop": self.previous or None,
            "previous_crop_name": crop_name(self.previous, self.locale) if self.previous else None,
            "soil_texture": self.soil["texture"], "soil_texture_source": self.soil["texture_source"],
            "soil_ph": self.soil["ph"], "soil_ph_source": self.soil["ph_source"],
            "soil_test": self.soil["test_source"],
            "groundwater_category": self.groundwater,
            "groundwater_scope": "district" if self.district and self.district.get("groundwater_category") else "state" if self.pack else None,
            "annual_rain_mm": annual,
            "district_normal_rain_mm": (self.district or {}).get("normal_rainfall_mm"),
            "district_note": (self.district or {}).get("note"),
            "land_cover": (self.land.land_cover or {}).get("label") if self.land else None,
            "field_ndvi": self.satellite.get("ndvi"), "field_ndmi": self.satellite.get("ndmi"),
            "satellite_observed_at": self.satellite.get("observed_at"),
        }

    def _sources(self) -> list[DataSource]:
        sources: list[DataSource] = []
        weather = latest_snapshot(self.evidence, "weather_forecast", "open_meteo")
        sources.append(DataSource(id="forecast", name="Open-Meteo 7-day forecast", kind="forecast",
                                  status="live" if weather else "unavailable", as_of=str(weather.get("fetched_at"))[:16] if weather else None))
        if self.land:
            sources.append(DataSource(id="climate", name="WorldClim 1960-1990 normals" if self.land.climate_source == "worldclim_1_4" else "Open-Meteo ERA5 2015-2024 normals",
                                      kind="estimated", status="estimated", detail=self.land.climate_period))
            sources.append(DataSource(id="soil_model", name="ISRIC SoilGrids 2.0", kind="estimated",
                                      status="estimated" if self.land.soil else "unavailable"))
        else:
            sources.append(DataSource(id="climate", name="Climate normals", kind="estimated", status="unavailable"))
        sources.append(DataSource(id="soil_test", name="Soil test report", kind="measured",
                                  status="live" if self.soil_test else "not_provided",
                                  as_of=self.soil_test.sample_date.isoformat() if self.soil_test and self.soil_test.sample_date else None))
        sat = latest_snapshot(self.evidence, "satellite_observation")
        sources.append(DataSource(id="satellite", name="Sentinel-2 (Earth Engine)", kind="satellite",
                                  status="live" if sat else "unavailable", as_of=str(sat.get("observed_at"))[:10] if sat and sat.get("observed_at") else None))
        if self.pack_ref:
            sources.append(DataSource(id="pack", name=f"{self.pack_ref.name} agronomy pack v{self.pack_ref.pack_version}", kind="regional",
                                      status="live", detail=self.pack_ref.review_status))
        sources.append(DataSource(id="crop_catalog", name="FAO EcoCrop crop requirements", kind="catalog", status="live"))
        return sources


def top_options(result: CropRecommendationResult, limit: int = 3) -> list[CropOption]:
    ranked = result.sow_now + result.upcoming
    return ranked[:limit]
