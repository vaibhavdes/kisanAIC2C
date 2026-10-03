"""Taluka (sub-district) for a point. In OpenStreetMap's Indian address data the 'county' field is the
taluka/tehsil ("Haveli Taluka", "Pune City Subdistrict"); it is cleaned and mapped to the revenue taluka."""
from __future__ import annotations

from .http_cache import Unavailable, fetch_json
from ..settings import get_settings

# OSM sub-district names that differ from the taluka farmers and the revenue department use.
# Villages on Pune city's edge (Wagholi, Lohegaon, Manjri, Keshavnagar) are mapped by OSM to the
# "Pune City" census sub-district but belong to Haveli taluka.
TALUKA_ALIASES = {"pune city": "Haveli", "pimpri chinchwad": "Haveli", "ahmadnagar": "Ahilyanagar", "ahmednagar": "Ahilyanagar"}


def clean_taluka(county: str | None) -> str | None:
    name = (county or "").strip()
    for word in ("Subdistrict", "Sub-district", "Taluka", "Tehsil", "Tahsil"):
        name = name.replace(word, "")
    name = " ".join(name.split())
    return TALUKA_ALIASES.get(name.lower(), name) or None


def taluka_for(lat: float, lon: float, store=None) -> str | None:
    if get_settings().app_env == "test":
        return None
    try:
        payload = fetch_json("https://nominatim.openstreetmap.org/reverse", store=store, ttl=180 * 86400, max_wait=4,
                             params={"format": "json", "lat": round(lat, 3), "lon": round(lon, 3), "zoom": 10, "addressdetails": 1})
    except Unavailable:
        return None
    return clean_taluka((payload.get("address") or {}).get("county"))
