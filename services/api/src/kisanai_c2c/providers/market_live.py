"""Recent mandi prices, fetched live through the cached, throttled client (http_cache):
data.gov.in's daily AGMARKNET feed (with a key), CEDA Ashoka's daily APMC prices (with a key) and
AGMARKNET's own monthly report for the current month (no key). The derived price is also kept in the
document store for six hours, so a busy demo asks each source at most a few times a day."""
from __future__ import annotations

import statistics
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..settings import Settings
from .http_cache import Unavailable, fetch_json

CEDA = "https://api.ceda.ashoka.edu.in/v1/agmarknet"
DATA_GOV = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
AGMARKNET = "https://api.agmarknet.gov.in/v1"
CACHE_AGE = timedelta(hours=6)
CEDA_STATE = {"maharashtra": 27}
CEDA_DISTRICT = {"pune": 521, "ahilyanagar": 522}
CEDA_NAMES = {
    "wheat": "Wheat", "rice": "Paddy(Dhan)(Common)", "maize": "Maize", "sorghum": "Jowar(Sorghum)", "pearl_millet": "Bajra(Pearl Millet/Cumbu)",
    "pigeon_pea": "Arhar (Tur/Red Gram)(Whole)", "chickpea": "Bengal Gram(Gram)(Whole)", "groundnut": "Groundnut",
    "soybean": "Soyabean", "cotton": "Cotton", "onion": "Onion", "tomato": "Tomato", "potato": "Potato",
}
AGMARKNET_IDS = {"soybean": 13, "cotton": 15, "pigeon_pea": 45, "chickpea": 6, "wheat": 1, "sorghum": 5,
                 "pearl_millet": 28, "onion": 23, "rice": 2, "maize": 4, "groundnut": 10, "tomato": 65, "potato": 24}
DATA_GOV_NAMES = {"pune": "Pune", "ahilyanagar": "Ahmednagar"}


class MarketLive:
    def __init__(self, settings: Settings, store: Any):
        self.settings = settings
        self.store = store

    def _cached(self, key: str) -> dict[str, Any] | None:
        if self.store is None:
            return None
        doc = self.store.get("market_cache", key)
        if doc and datetime.now(UTC) - datetime.fromisoformat(doc["fetched_at"]) < CACHE_AGE:
            return doc["value"]
        return None

    def _save(self, key: str, value: dict[str, Any]) -> None:
        if self.store is None:
            return
        now = datetime.now(UTC).isoformat()
        self.store.put("market_cache", key, {"id": key, "fetched_at": now, "created_at": now, "value": value})

    def recent(self, district_key: str, crop: str, days: int = 45) -> dict[str, Any] | None:
        """Latest mandi price for the district: today (data.gov.in), recent days (CEDA) or this month (AGMARKNET)."""
        key = f"recent_{district_key}_{crop}_{days}"
        cached = self._cached(key)
        if cached:
            return cached
        result = self._from_data_gov(district_key, crop) or self._from_ceda(district_key, crop, days) or self._from_agmarknet(district_key, crop)
        if result:  # a failed or empty lookup is retried on a later request
            self._save(key, result)
        return result

    def _from_agmarknet(self, district_key: str, crop: str) -> dict[str, Any] | None:
        from ..market import norm_district
        commodity = AGMARKNET_IDS.get(crop)
        if not commodity:
            return None
        today = date.today()
        previous = (today.year - (today.month == 1), (today.month - 2) % 12 + 1)
        for year, month in ((today.year, today.month), previous):
            try:
                payload = fetch_json(f"{AGMARKNET}/price-trend/wholesale-prices-monthly", store=self.store, ttl=6 * 3600, params={
                    "report_mode": "Districtwise", "commodity": commodity, "year": year, "month": month, "state": 20})
            except Unavailable:
                continue
            column = f"prices_{date(year, month, 1).strftime('%B').lower()}_{year}"
            value = next((r.get(column) for r in payload.get("rows") or [] if norm_district(r.get("district")) == district_key and r.get(column)), None)
            if value:
                return {"median_rs_qtl": round(value), "reports": None, "markets": None, "latest_date": f"{year}-{month:02d}",
                        "days": None, "month": f"{year}-{month:02d}", "source": "AGMARKNET monthly average (this month so far)"}
        return None

    def _ceda_commodity_id(self, crop: str) -> int | None:
        payload = fetch_json(f"{CEDA}/commodities", headers={"Authorization": f"Bearer {self.settings.ceda_api_key}"},
                             store=self.store, ttl=30 * 86400)
        names = {row["commodity_name"]: row["commodity_id"] for row in payload["output"]["data"]}
        name = CEDA_NAMES.get(crop)
        if name in names:
            return names[name]
        stem = (name or crop).split("(")[0].strip().lower()
        return next((cid for cname, cid in names.items() if cname.lower().startswith(stem)), None)

    def _from_ceda(self, district_key: str, crop: str, days: int) -> dict[str, Any] | None:
        if not self.settings.ceda_api_key or district_key not in CEDA_DISTRICT:
            return None
        try:
            commodity = self._ceda_commodity_id(crop)
            if not commodity:
                return None
            end = date.today()
            body = {"commodity_id": commodity, "state_id": CEDA_STATE["maharashtra"], "district_id": [CEDA_DISTRICT[district_key]],
                    "from_date": (end - timedelta(days=days)).isoformat(), "to_date": end.isoformat()}
            # Raw daily rows can be large, so only the derived price is stored (via `recent`).
            payload = fetch_json(f"{CEDA}/prices", body=body, headers={"Authorization": f"Bearer {self.settings.ceda_api_key}"}, ttl=6 * 3600, timeout=60)
            rows = [r for r in payload["output"]["data"] if r.get("modal_price")]
        except (Unavailable, KeyError, TypeError):
            return None
        if not rows:
            return None
        return {"median_rs_qtl": round(statistics.median(r["modal_price"] for r in rows)), "reports": len(rows),
                "markets": len({r.get("market_id") for r in rows}), "latest_date": max(r["date"][:10] for r in rows), "days": days,
                "source": "CEDA Ashoka Agri Market API (AGMARKNET daily prices)"}

    def _from_data_gov(self, district_key: str, crop: str) -> dict[str, Any] | None:
        if not self.settings.data_gov_in_api_key or district_key not in DATA_GOV_NAMES:
            return None
        try:
            payload = fetch_json(DATA_GOV, ttl=3 * 3600, params={
                "api-key": self.settings.data_gov_in_api_key, "format": "json", "limit": 500,
                "filters[state.keyword]": "Maharashtra", "filters[district]": DATA_GOV_NAMES[district_key]})
        except Unavailable:
            return None
        stem = (CEDA_NAMES.get(crop) or crop).split("(")[0].strip().lower()
        rows = [r for r in payload.get("records", []) if str(r.get("commodity", "")).lower().startswith(stem)]
        prices = [float(r["modal_price"]) for r in rows if r.get("modal_price")]
        if not prices:
            return None
        return {"median_rs_qtl": round(statistics.median(prices)), "reports": len(prices), "markets": len({r.get("market") for r in rows}),
                "latest_date": rows[0].get("arrival_date"), "days": 1, "source": "data.gov.in AGMARKNET daily prices"}
