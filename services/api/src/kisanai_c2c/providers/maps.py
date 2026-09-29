"""Google Maps Platform (server-side key): Geocoding for place search and GPS-to-village lookup,
Map Tiles for the satellite basemap. The key never reaches the browser; callers fall back to
OpenStreetMap / Esri when Maps is not configured or fails.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import requests

from ..settings import Settings, get_settings

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
TILES_URL = "https://tile.googleapis.com/v1"
_SESSION: dict[str, Any] = {}
_LOCK = threading.Lock()


class MapsUnavailable(RuntimeError):
    pass


def _component(components: list[dict[str, Any]], kind: str, short: bool = False) -> str:
    item = next((c for c in components if kind in c["types"]), None)
    return (item["short_name"] if short else item["long_name"]) if item else ""


def place_from_google(result: dict[str, Any]) -> dict[str, Any]:
    comps = result.get("address_components", [])
    country = _component(comps, "country", short=True)
    # Districts are administrative level 3 in India; Brazilian municipalities are level 2.
    district = (_component(comps, "administrative_area_level_3") if country == "IN" else "") or _component(comps, "administrative_area_level_2")
    village = (_component(comps, "locality") or _component(comps, "sublocality") or _component(comps, "administrative_area_level_4")
               or district)
    location = result["geometry"]["location"]
    return {
        "latitude": location["lat"], "longitude": location["lng"],
        "country_code": country, "country_name": _component(comps, "country"),
        "state_code": _component(comps, "administrative_area_level_1", short=True), "state_name": _component(comps, "administrative_area_level_1"),
        "district": district.replace(" District", "").strip(), "village": village, "pincode": _component(comps, "postal_code"),
        "label": result.get("formatted_address"), "source": "google_maps_geocoding",
    }


class GoogleMaps:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.google_maps_api_key)

    def _geocode(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.enabled:
            raise MapsUnavailable("Google Maps is not configured on this node")
        response = requests.get(GEOCODE_URL, params=params | {"key": self.settings.google_maps_api_key, "language": "en"}, timeout=6)
        data = response.json()
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            raise MapsUnavailable(f"Geocoding returned {data.get('status')}")
        return [place_from_google(item) for item in data.get("results", [])]

    def reverse(self, latitude: float, longitude: float) -> dict[str, Any]:
        places = self._geocode({"latlng": f"{latitude},{longitude}"})
        if not places:
            raise MapsUnavailable("No address at this point")
        return places[0] | {"latitude": latitude, "longitude": longitude}

    def search(self, query: str, country_code: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"address": query}
        if country_code:
            params["components"] = f"country:{country_code.upper()}"
        return self._geocode(params)[:6]

    def _tile_session(self) -> str:
        with _LOCK:
            if _SESSION.get("expiry", 0) - 3600 > time.time():
                return _SESSION["session"]
            response = requests.post(f"{TILES_URL}/createSession", params={"key": self.settings.google_maps_api_key},
                                     json={"mapType": "satellite", "language": "en-US", "region": self.settings.node_country_code,
                                           "layerTypes": ["layerRoadmap"], "overlay": False}, timeout=6)
            data = response.json()
            if "session" not in data:
                raise MapsUnavailable("Map Tiles session could not be created")
            _SESSION.update(session=data["session"], expiry=float(data.get("expiry", time.time() + 86400)))
            return _SESSION["session"]

    def satellite_tile(self, z: int, x: int, y: int) -> tuple[bytes, str]:
        if not self.enabled:
            raise MapsUnavailable("Google Maps is not configured on this node")
        response = requests.get(f"{TILES_URL}/2dtiles/{z}/{x}/{y}",
                                params={"session": self._tile_session(), "key": self.settings.google_maps_api_key}, timeout=8)
        if response.status_code != 200:
            raise MapsUnavailable(f"Map tile returned {response.status_code}")
        return response.content, response.headers.get("content-type", "image/jpeg")
