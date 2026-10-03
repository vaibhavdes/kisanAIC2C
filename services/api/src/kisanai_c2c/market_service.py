"""Joins the market model (market.py) to farms: crop plans for the crowding signal, the per-crop market
outlook, the profit simulation and the economic part of the crop ranking."""
from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime
from typing import Any

from . import market as m
from .models import CropDecisionFactor, CropPlanCreate, Farm, SimulationRequest
from .providers.market_live import MarketLive
from .settings import PROJECT_ROOT

SOW_MONTH = {"kharif": 6, "rabi": 10, "summer": 2}
OUTLOOK_TTL = 600  # seconds an outlook is reused; a new crop plan in the district changes the key
_outlooks: dict[tuple, tuple[float, dict[str, Any]]] = {}
LANGS = {"en-IN", "hi-IN", "mr-IN", "te-IN", "kn-IN"}


def plan_year(season: str, today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month <= SOW_MONTH[season] + 1 else today.year + 1


def apmc_locations() -> dict[str, list[float]]:
    path = PROJECT_ROOT / "data" / "market" / "apmc_locations.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


class MarketService:
    def __init__(self, store: Any, settings: Any):
        self.store = store
        self.settings = settings
        self.live = MarketLive(settings, store)

    # ------------------------------------------------------------ crop plans
    def save_plan(self, farm: Farm, payload: CropPlanCreate, source: str = "farmer") -> dict[str, Any]:
        from .domain import normalize_crop
        year = plan_year(payload.season)
        doc = {
            "id": f"{farm.id}_{payload.season}_{year}", "farm_id": farm.id, "node_id": farm.node_id,
            "district": m.norm_district(farm.district), "taluka": (farm.taluka or "").strip() or None,
            "village": (farm.village or "").strip() or None,
            "crop": normalize_crop(payload.crop), "season": payload.season, "year": year,
            "area_ha": payload.area_ha or farm.area_ha, "source": source,
            "created_at": datetime.now(UTC).isoformat(), "owner_subject": farm.owner_subject,
        }
        self.store.put("crop_plans", doc["id"], doc)
        return doc

    def plans(self, farm: Farm, season: str) -> list[dict[str, Any]]:
        year = plan_year(season)
        rows = self.store.list("crop_plans", filters={"district": m.norm_district(farm.district), "season": season, "year": year}, limit=500)
        return [r for r in rows if r.get("node_id") in (None, farm.node_id)]

    def my_plan(self, farm: Farm, season: str) -> dict[str, Any] | None:
        return self.store.get("crop_plans", f"{farm.id}_{season}_{plan_year(season)}")

    def regional_mix(self, farm: Farm, season: str) -> dict[str, Any]:
        plans = self.plans(farm, season)
        def tally(items):
            out: dict[str, int] = {}
            for p in items:
                out[p["crop"]] = out.get(p["crop"], 0) + 1
            return dict(sorted(out.items(), key=lambda kv: -kv[1]))
        taluka = (farm.taluka or "").lower()
        taluka_items = [p for p in plans if taluka and (p.get("taluka") or "").lower() == taluka]
        village = (farm.village or "").lower()
        village_items = [p for p in plans if village and (p.get("village") or "").lower() == village]
        usual = {}
        for crop in {c for (d, c, s) in m.apy() if d == m.norm_district(farm.district) and s == season}:
            t = m.apy_trend(farm.district, crop, season)
            if t and t.get("district_share"):
                usual[crop] = {"share": t["district_share"], "area_ha": t["area_ha"], "change": t["change"], "year": t["latest_year"]}
        return {
            "season": season, "year": plan_year(season), "district": farm.district, "taluka": farm.taluka,
            "district_counts": tally(plans), "district_farms": len(plans),
            # Taluka counts are shown only once a few farms have planned, so no single farm can be identified.
            "taluka_counts": tally(taluka_items) if len(taluka_items) >= 3 else {}, "taluka_farms": len(taluka_items),
            "village": farm.village, "village_counts": tally(village_items) if len(village_items) >= 3 else {}, "village_farms": len(village_items),
            "sample_entries": sum(1 for p in plans if p.get("source") == "demo"),
            "usual_mix": dict(sorted(usual.items(), key=lambda kv: -kv[1]["share"])),
        }

    # ------------------------------------------------------------ markets
    def apmc_table(self, farm: Farm, crop: str, season: str) -> list[dict[str, Any]]:
        markets = m.market_rows().get((m.norm_district(farm.district), crop), {})
        locations = apmc_locations()
        sow = m.next_sowing_year(season, crop) - 1
        out = []
        for name, series in markets.items():
            window = m.harvest_months(crop, season, sow)
            prev = m.harvest_months(crop, season, sow - 1)
            prices = [series[k][0] for k in window if k in series and series[k][0]]
            arr = [series[k][1] for k in window if k in series and series[k][1]]
            prev_arr = [series[k][1] for k in prev if k in series and series[k][1]]
            if not prices and not arr:
                continue
            loc = locations.get(f"{m.norm_district(farm.district)}|{name}")
            dist = round(_km((farm.location.latitude, farm.location.longitude), tuple(loc)), 1) if loc else None
            out.append({
                "market": name.replace("APMC", "").strip() or name, "price": round(sum(prices) / len(prices)) if prices else None,
                "arrivals_t": round(sum(arr), 1) if arr else None,
                "arrivals_change": round(sum(arr) / sum(prev_arr) - 1, 3) if arr and prev_arr and sum(prev_arr) else None,
                "distance_km": dist, "season": m._season_label(season, sow),
                "is_local": bool(farm.taluka and farm.taluka.lower() in name.lower()),
            })
        out.sort(key=lambda r: (not r["is_local"], r["distance_km"] if r["distance_km"] is not None else 9999, -(r["arrivals_t"] or 0)))
        return out

    def outlook(self, farm: Farm, crop: str, season: str, lookback: int = 3, soil_score: float | None = None) -> dict[str, Any]:
        from .data.maharashtra_agri_context import get_district_profile
        from .domain import normalize_crop
        crop = normalize_crop(crop)
        covered = m.is_covered(farm.district)
        base = {"crop": crop, "season": season, "district": farm.district, "covered": covered, "lookback": lookback}
        if not covered:
            return base | {"reason": "not_covered", "covered_districts": sorted(m.covered_districts())}
        if not m.season_calendar(crop, season):
            return base | {"reason": "not_in_season"}
        plans = self.plans(farm, season)
        import time
        key = (farm.id, farm.version, crop, season, lookback, soil_score, len(plans), sum(1 for p in plans if p.get("crop") == crop), date.today())
        hit = _outlooks.get(key)
        if hit and time.time() - hit[0] < OUTLOOK_TTL:
            return hit[1]
        crowd = m.crowding(farm.district, crop, season, plans, farm.taluka)
        crowd |= self._village_counts(farm, crop, plans)
        price = m.price_forecast(farm.district, crop, season, lookback, crowd["supply_shift"])
        profile = get_district_profile(farm.district)
        yld = m.yield_model(farm.district, crop, season, farm.water_access, soil_score, getattr(profile, "dryspell_risk_category", None))
        cost = m.cost_per_ha(crop)
        apmcs = self.apmc_table(farm, crop, season)
        nearest = next((a for a in apmcs if a["distance_km"] is not None), apmcs[0] if apmcs else None)
        live = None if crop in m.FRP_CROPS else self.live.recent(m.norm_district(farm.district), crop)
        sim = None
        if price and yld:
            sim = m.simulate(price, yld, cost, m.Assumptions(area_ha=farm.area_ha, distance_km=(nearest or {}).get("distance_km")))
        result = base | {
            "sow_year": m.next_sowing_year(season, crop), "price": price, "yield": yld, "cost": cost, "crowding": crowd,
            "apmcs": apmcs[:12], "nearest_apmc": nearest, "live": live, "simulation": sim,
            "recent_prices": m.recent_prices(farm.district, crop, 36), "monthly_profile": m.monthly_profile(farm.district, crop),
            "best_sell": m.best_sell_month(farm.district, crop, season), "storable": crop in m.STORABLE,
            "sources": self._sources(cost, yld, live),
        }
        if len(_outlooks) > 500:
            _outlooks.clear()
        _outlooks[key] = (time.time(), result)
        return result

    @staticmethod
    def _village_counts(farm: Farm, crop: str, plans: list[dict[str, Any]]) -> dict[str, Any]:
        village = (farm.village or "").strip().lower()
        same = [p for p in plans if village and (p.get("village") or "").lower() == village]
        return {"village": farm.village, "village_farms": len(same), "village_same_crop": sum(1 for p in same if p.get("crop") == crop)}

    def simulate(self, farm: Farm, req: SimulationRequest, soil_score: float | None = None) -> dict[str, Any]:
        from .data.maharashtra_agri_context import get_district_profile
        from .domain import normalize_crop
        crop = normalize_crop(req.crop)
        if not m.is_covered(farm.district):
            raise ValueError(f"Market simulation is available for {', '.join(sorted(m.covered_districts())).title()} only")
        crowd = m.crowding(farm.district, crop, req.season, self.plans(farm, req.season), farm.taluka)
        price = m.price_forecast(farm.district, crop, req.season, req.lookback, crowd["supply_shift"])
        profile = get_district_profile(farm.district)
        yld = m.yield_model(farm.district, crop, req.season, farm.water_access, soil_score, getattr(profile, "dryspell_risk_category", None))
        if req.yield_override_kg_ha and not yld:
            yld = {"kg_ha": req.yield_override_kg_ha, "cv": 0.2, "source": "your yield", "estimate": False}
        if req.price_override and not price:
            price = {"expected": req.price_override, "sigma": 0.0, "msp": m.msp_for(crop, date.today().year)}
        if not price or not yld:
            raise ValueError("Not enough price or yield data for this crop and season; enter your own price and yield")
        apmcs = self.apmc_table(farm, crop, req.season)
        nearest = next((a for a in apmcs if a["distance_km"] is not None), None)
        cost = m.cost_per_ha(crop)
        result = m.simulate(price, yld, cost, m.Assumptions(
            area_ha=req.area_ha or farm.area_ha, price_override=req.price_override, cost_per_ha_override=req.cost_per_ha_override,
            yield_override_kg_ha=req.yield_override_kg_ha, use_msp_floor=req.use_msp_floor,
            distance_km=(nearest or {}).get("distance_km"), transport_rs_per_qtl_km=req.transport_rs_per_qtl_km))
        return {"crop": crop, "season": req.season, "price": price, "yield": yld, "cost": cost, "crowding": crowd,
                "nearest_apmc": nearest, "simulation": result, "sources": self._sources(cost, yld, None)}

    @staticmethod
    def _sources(cost, yld, live) -> list[dict[str, str]]:
        ref = m.reference().get("sources", {})
        out = [
            {"name": "AGMARKNET monthly mandi prices", "detail": "District and APMC modal prices, 2014 onwards", "url": "https://agmarknet.gov.in"},
            {"name": "UPAg district crop statistics", "detail": "Area, production and yield (DES, final estimates)", "url": "https://upag.gov.in"},
            {"name": "MSP and cost of production (PIB)", "detail": "Kharif 2026-27, Rabi 2026-27 and 2027-28, sugarcane FRP 2026-27", "url": ref.get("pib_kharif_2026_27", "")},
        ]
        if live:
            out.append({"name": live["source"], "detail": f"{live['reports']} price reports, last {live['days']} days", "url": "https://agmarknet.ceda.ashoka.edu.in"})
        if (yld or {}).get("estimate") or (cost or {}).get("estimate"):
            out.append({"name": "Reference estimate", "detail": "No official district figure; replace with your own numbers", "url": ""})
        return out

    # ------------------------------------------------------------ ranking
    def economics_for(self, farm: Farm, options: list[Any], season: str, locale: str) -> None:
        """Adds price/crowding/profit to each eligible crop, a 'market' factor, and re-ranks by
        60% agronomy and 40% economics. Leaves options unchanged outside the market districts."""
        if not m.is_covered(farm.district):
            return
        plans = self.plans(farm, season)
        scored = []
        for opt in options:
            soil = next((d.score for d in opt.dimensions if d.name == "soil_fit"), None)
            econ = self._light_outlook(farm, opt.crop, season, plans, soil)
            if not econ:
                continue
            opt.economics = econ
            opt.factors.append(_market_factor(econ, locale))
            scored.append(opt)
        profits = [o.economics["profit_per_ha_p50"] for o in scored if o.economics.get("profit_per_ha_p50") is not None]
        if not profits:
            return
        lo, hi = min(profits), max(profits)
        for opt in scored:
            p = opt.economics.get("profit_per_ha_p50")
            if p is None or opt.rank_score is None:
                continue
            norm = 0.5 if hi == lo else (p - lo) / (hi - lo)
            econ_score = 0.7 * norm + 0.3 * (1 - (opt.economics.get("loss_probability") or 0))
            opt.economics["economic_score"] = round(econ_score, 3)
            opt.agronomic_score = opt.rank_score
            opt.rank_score = round(0.6 * opt.rank_score + 0.4 * econ_score, 3)

    def _light_outlook(self, farm: Farm, crop: str, season: str, plans: list[dict[str, Any]], soil: float | None) -> dict[str, Any] | None:
        from .data.maharashtra_agri_context import get_district_profile
        if not m.season_calendar(crop, season):
            return None
        crowd = m.crowding(farm.district, crop, season, plans, farm.taluka)
        price = m.price_forecast(farm.district, crop, season, 3, crowd["supply_shift"])
        profile = get_district_profile(farm.district)
        yld = m.yield_model(farm.district, crop, season, farm.water_access, soil, getattr(profile, "dryspell_risk_category", None))
        if not price or not yld:
            return None
        cost = m.cost_per_ha(crop)
        sim = m.simulate(price, yld, cost, m.Assumptions(area_ha=1.0), runs=800)
        last = (price.get("past") or [{}])[0]
        return {
            "expected_price": price["expected"], "price_low": price["low"], "price_high": price["high"], "msp": price.get("msp"),
            "last_season_price": last.get("price"), "last_season": last.get("label"), "sell_months": price.get("sell_months"),
            "below_msp_seasons": price.get("below_msp_seasons"), "yield_kg_ha": yld["kg_ha"], "yield_estimate": yld["estimate"],
            "cost_per_ha": (cost or {}).get("rs_ha"), "cost_estimate": (cost or {}).get("estimate"),
            "profit_per_ha_p10": (sim["profit_rs"] or {}).get("p10"), "profit_per_ha_p50": (sim["profit_rs"] or {}).get("p50"),
            "profit_per_ha_p90": (sim["profit_rs"] or {}).get("p90"), "loss_probability": sim["loss_probability"],
            "crowding": crowd["level"], "district_same_crop": crowd["district_same_crop"], "district_farms": crowd["district_farms"],
            "area_change": (crowd.get("apy_trend") or {}).get("change"),
        }


def _rs(v: float | None) -> str:
    return "—" if v is None else f"₹{v:,.0f}"


MARKET_TEXT = {
    "en-IN": {"name": "Market price and profit", "data": "Expected {price}/qtl at harvest ({months}); last season {last}; MSP {msp}. Profit per hectare {p10} to {p90}, most likely {p50}.",
              "high": "Many farmers near you are planting this; prices may fall at harvest.", "low": "Fewer farmers than usual are planting this; less competition at the mandi.",
              "normal": "Planting near you looks normal for this crop.", "loss": "Chance of a loss: {loss}.",
              "remedy": "Sell in stages, or store and sell later; check the simulator before deciding."},
    "hi-IN": {"name": "बाजार भाव और मुनाफा", "data": "कटाई पर अनुमानित भाव {price}/क्विंटल ({months}); पिछला सीज़न {last}; MSP {msp}. प्रति हेक्टेयर मुनाफा {p10} से {p90}, संभावित {p50}.",
              "high": "आपके आसपास बहुत किसान यही फसल लगा रहे हैं; कटाई पर भाव गिर सकता है।", "low": "इस बार कम किसान यह फसल लगा रहे हैं; मंडी में कम प्रतिस्पर्धा।",
              "normal": "आसपास इस फसल की बुवाई सामान्य दिख रही है।", "loss": "नुकसान की संभावना: {loss}.",
              "remedy": "थोड़ा-थोड़ा बेचें या भंडारण करके बाद में बेचें; फैसले से पहले सिम्युलेटर देखें।"},
    "mr-IN": {"name": "बाजारभाव आणि नफा", "data": "काढणीवेळी अपेक्षित भाव {price}/क्विंटल ({months}); मागील हंगाम {last}; हमीभाव {msp}. प्रति हेक्टर नफा {p10} ते {p90}, बहुधा {p50}.",
              "high": "तुमच्या भागातील अनेक शेतकरी हेच पीक घेत आहेत; काढणीवेळी भाव पडू शकतो.", "low": "यंदा कमी शेतकरी हे पीक घेत आहेत; बाजारात स्पर्धा कमी.",
              "normal": "तुमच्या भागात या पिकाची लागवड नेहमीसारखी दिसते.", "loss": "तोट्याची शक्यता: {loss}.",
              "remedy": "टप्प्याटप्प्याने विका किंवा साठवून नंतर विका; निर्णयापूर्वी सिम्युलेटर पाहा."},
    "te-IN": {"name": "మార్కెట్ ధర, లాభం", "data": "కోత సమయంలో అంచనా ధర {price}/క్వింటాల్ ({months}); గత సీజన్ {last}; MSP {msp}. హెక్టారుకు లాభం {p10} నుండి {p90}, ఎక్కువగా {p50}.",
              "high": "మీ దగ్గర చాలా మంది రైతులు ఇదే పంట వేస్తున్నారు; కోత సమయంలో ధర తగ్గవచ్చు.", "low": "ఈసారి తక్కువ రైతులు ఈ పంట వేస్తున్నారు; మార్కెట్‌లో పోటీ తక్కువ.",
              "normal": "మీ ప్రాంతంలో ఈ పంట సాగు సాధారణంగా ఉంది.", "loss": "నష్టం వచ్చే అవకాశం: {loss}.",
              "remedy": "కొంచెం కొంచెం అమ్మండి లేదా నిల్వ చేసి తర్వాత అమ్మండి; నిర్ణయానికి ముందు సిమ్యులేటర్ చూడండి."},
    "kn-IN": {"name": "ಮಾರುಕಟ್ಟೆ ಬೆಲೆ ಮತ್ತು ಲಾಭ", "data": "ಕಟಾವಿನಲ್ಲಿ ಅಂದಾಜು ಬೆಲೆ {price}/ಕ್ವಿಂಟಾಲ್ ({months}); ಕಳೆದ ಹಂಗಾಮು {last}; MSP {msp}. ಹೆಕ್ಟೇರಿಗೆ ಲಾಭ {p10} ರಿಂದ {p90}, ಹೆಚ್ಚಾಗಿ {p50}.",
              "high": "ನಿಮ್ಮ ಸುತ್ತಲಿನ ಅನೇಕ ರೈತರು ಇದೇ ಬೆಳೆ ಬೆಳೆಯುತ್ತಿದ್ದಾರೆ; ಕಟಾವಿನಲ್ಲಿ ಬೆಲೆ ಇಳಿಯಬಹುದು.", "low": "ಈ ಬಾರಿ ಕಡಿಮೆ ರೈತರು ಈ ಬೆಳೆ ಬೆಳೆಯುತ್ತಿದ್ದಾರೆ; ಮಾರುಕಟ್ಟೆಯಲ್ಲಿ ಪೈಪೋಟಿ ಕಡಿಮೆ.",
              "normal": "ನಿಮ್ಮ ಭಾಗದಲ್ಲಿ ಈ ಬೆಳೆ ಬಿತ್ತನೆ ಸಾಮಾನ್ಯವಾಗಿದೆ.", "loss": "ನಷ್ಟದ ಸಾಧ್ಯತೆ: {loss}.",
              "remedy": "ಹಂತ ಹಂತವಾಗಿ ಮಾರಿ ಅಥವಾ ಸಂಗ್ರಹಿಸಿ ನಂತರ ಮಾರಿ; ನಿರ್ಧಾರಕ್ಕೆ ಮುನ್ನ ಸಿಮ್ಯುಲೇಟರ್ ನೋಡಿ."},
}


def _market_factor(econ: dict[str, Any], locale: str) -> CropDecisionFactor:
    text = MARKET_TEXT.get(locale if locale in LANGS else "en-IN")
    loss = econ.get("loss_probability") or 0
    status = "constrained" if econ["crowding"] == "high" or loss > 0.35 else "optimal" if econ["crowding"] == "low" and loss < 0.15 else "compatible"
    months = ", ".join(sorted({date(int(s[:4]), int(s[5:]), 1).strftime("%b") for s in econ.get("sell_months") or []}, key=lambda x: x))
    data = text["data"].format(price=_rs(econ["expected_price"]), months=months, last=_rs(econ.get("last_season_price")), msp=_rs(econ.get("msp")),
                               p10=_rs(econ.get("profit_per_ha_p10")), p50=_rs(econ.get("profit_per_ha_p50")), p90=_rs(econ.get("profit_per_ha_p90")))
    reasoning = text[econ["crowding"]] + " " + text["loss"].format(loss=f"{round(loss * 100)}%")
    return CropDecisionFactor(factor_id="market", factor_name=text["name"], status=status, data_used=data, reasoning=reasoning,
                              remedy=text["remedy"] if status == "constrained" else None)
