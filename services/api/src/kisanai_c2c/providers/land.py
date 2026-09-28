"""Location land profile: monthly climate normals, modelled topsoil properties and land cover.

Two independent lookups run in parallel:
  * Climate normals from the Open-Meteo ERA5 archive (2015-2024 daily data aggregated to
    months, including FAO-56 Penman-Monteith reference evapotranspiration). If that fails and
    Earth Engine is enabled, WorldClim 1.4 monthly normals are used with Hargreaves PET.
  * Google Earth Engine: ISRIC SoilGrids 2.0 topsoil 0-30 cm (projects/soilgrids-isric/*) and
    ESA WorldCover 10 m v200 land cover plus the cropland share within 2 km.
All values are modelled estimates and are labelled as such; farmer soil tests override them.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import requests

from ..models import ClimateMonth, Farm, LandProfile, SoilEstimate
from ..settings import Settings, get_settings

WORLDCOVER_LABELS = {
    10: "tree_cover", 20: "shrubland", 30: "grassland", 40: "cropland", 50: "built_up",
    60: "bare_sparse", 70: "snow_ice", 80: "water", 90: "wetland", 95: "mangroves", 100: "moss_lichen",
}
DEPTH_WEIGHTS = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}
SOIL_LAYERS = ("phh2o", "soc", "clay", "sand", "nitrogen")


class LandProfileUnavailable(RuntimeError):
    pass


def texture_class(clay_pct: float | None, sand_pct: float | None) -> str | None:
    """Coarse FAO EcoCrop texture class from topsoil clay and sand fractions."""
    if clay_pct is None or sand_pct is None:
        return None
    if clay_pct >= 35:
        return "heavy"
    if sand_pct >= 65 and clay_pct < 18:
        return "light"
    return "medium"


class LandProfileProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def fetch(self, farm: Farm) -> LandProfile:
        flags: list[str] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            climate_future = pool.submit(self._climate, farm)
            ground_future = pool.submit(self._soil_and_cover, farm) if self.settings.earth_engine_enabled else None
            try:
                months, climate_source, climate_period = climate_future.result()
            except Exception as exc:  # noqa: BLE001
                raise LandProfileUnavailable(f"Climate normals unavailable: {str(exc)[:200]}") from exc
            soil, cover = None, None
            if ground_future is not None:
                try:
                    soil, cover = ground_future.result()
                except Exception as exc:  # noqa: BLE001
                    flags.append(f"earth_engine_soil_unavailable: {str(exc)[:120]}")
            else:
                flags.append("earth_engine_disabled")
        if ground_future is not None and soil is None and not flags:
            flags.append("soilgrids_no_data_at_location")
        return LandProfile(
            farm_id=farm.id, node_id=farm.node_id,
            latitude=farm.location.latitude, longitude=farm.location.longitude,
            climate=months, climate_source=climate_source, climate_period=climate_period,
            soil=soil, land_cover=cover, quality_flags=flags,
        )

    def _climate(self, farm: Farm) -> tuple[list[ClimateMonth], str, str]:
        try:
            return self._fetch_open_meteo_normals(farm), "open_meteo_era5_archive", "2015-2024"
        except Exception:
            if not self.settings.earth_engine_enabled:
                raise
            return self._fetch_worldclim_normals(farm), "worldclim_1_4", "1960-1990"

    # Earth Engine -------------------------------------------------------------------------
    def _geometry(self, ee, farm: Farm):
        if farm.boundary_coordinates and len(farm.boundary_coordinates) >= 3:
            coords = [[float(pt[1]), float(pt[0])] for pt in farm.boundary_coordinates]
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            return ee.Geometry.Polygon([coords])
        return ee.Geometry.Point([farm.location.longitude, farm.location.latitude]).buffer(150)

    def _soil_and_cover(self, farm: Farm) -> tuple[SoilEstimate | None, dict[str, Any] | None]:
        import ee

        ee.Initialize(project=self.settings.google_cloud_project)
        geometry = self._geometry(ee, farm)
        centroid = geometry.centroid(1)
        soil_img = None
        for layer in SOIL_LAYERS:
            source = ee.Image(f"projects/soilgrids-isric/{layer}_mean")
            weighted = None
            for depth, weight in DEPTH_WEIGHTS.items():
                band = source.select(f"{layer}_{depth}_mean").multiply(weight)
                weighted = band if weighted is None else weighted.add(band)
            weighted = weighted.divide(sum(DEPTH_WEIGHTS.values())).rename(layer)
            soil_img = weighted if soil_img is None else soil_img.addBands(weighted)
        worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
        result = ee.Dictionary({
            "soil": soil_img.reduceRegion(ee.Reducer.mean(), geometry, 250, maxPixels=1e7),
            "cover": worldcover.reduceRegion(ee.Reducer.mode(), geometry, 10, maxPixels=1e8),
            "cropland": worldcover.eq(40).reduceRegion(ee.Reducer.mean(), centroid.buffer(2000), 30, maxPixels=1e8),
        }).getInfo()
        soil = self._soilgrids_estimate(result.get("soil") or {})
        cover_code = (result.get("cover") or {}).get("Map")
        cropland = (result.get("cropland") or {}).get("Map")
        cover = None
        if cover_code is not None:
            code = int(round(float(cover_code)))
            cover = {
                "class_code": code,
                "label": WORLDCOVER_LABELS.get(code, "unknown"),
                "cropland_share_2km": round(float(cropland), 3) if cropland is not None else None,
                "source": "ESA WorldCover 10 m v200 (2021)",
            }
        return soil, cover

    def _fetch_worldclim_normals(self, farm: Farm) -> list[ClimateMonth]:
        import ee

        ee.Initialize(project=self.settings.google_cloud_project)
        point = ee.Geometry.Point([farm.location.longitude, farm.location.latitude])
        rows = ee.ImageCollection("WORLDCLIM/V1/MONTHLY").getRegion(point, 1000).getInfo()
        header, data = rows[0], rows[1:]
        months: list[ClimateMonth] = []
        for row in data:
            item = dict(zip(header, row))
            month = int(item["id"])
            tmin, tmax = float(item["tmin"]) * 0.1, float(item["tmax"]) * 0.1
            months.append(ClimateMonth(
                month=month, tmin_c=round(tmin, 1), tmax_c=round(tmax, 1), tmean_c=round((tmin + tmax) / 2, 1),
                precip_mm=float(item["prec"]),
                pet_mm=round(hargreaves_monthly_pet(farm.location.latitude, month, tmin, tmax), 1),
            ))
        return sorted(months, key=lambda m: m.month)

    @staticmethod
    def _soilgrids_estimate(values: dict[str, Any]) -> SoilEstimate | None:
        if values.get("phh2o") is None and values.get("soc") is None:
            return None

        def scaled(key: str, factor: float) -> float | None:
            value = values.get(key)
            return round(float(value) * factor, 2) if value is not None else None

        clay = scaled("clay", 0.1)
        sand = scaled("sand", 0.1)
        return SoilEstimate(
            ph=scaled("phh2o", 0.1),
            organic_carbon_percent=scaled("soc", 0.01),
            clay_percent=clay,
            sand_percent=sand,
            total_nitrogen_g_kg=scaled("nitrogen", 0.01),
            texture_class=texture_class(clay, sand),
            depth="0-30 cm",
            source="ISRIC SoilGrids 2.0 (250 m)",
        )

    # Open-Meteo ERA5 archive -------------------------------------------------------------------
    def _fetch_open_meteo_normals(self, farm: Farm) -> list[ClimateMonth]:
        response = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": farm.location.latitude, "longitude": farm.location.longitude,
                "start_date": "2015-01-01", "end_date": "2024-12-31",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration",
                "timezone": "auto",
            },
            timeout=20,
        )
        response.raise_for_status()
        daily = response.json().get("daily") or {}
        buckets: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        yearly_precip: dict[tuple[int, int], float] = defaultdict(float)
        yearly_pet: dict[tuple[int, int], float] = defaultdict(float)
        for idx, day in enumerate(daily.get("time") or []):
            year, month = int(day[:4]), int(day[5:7])
            tmax = daily["temperature_2m_max"][idx]
            tmin = daily["temperature_2m_min"][idx]
            if tmax is not None and tmin is not None:
                buckets[month]["tmax"].append(tmax)
                buckets[month]["tmin"].append(tmin)
            yearly_precip[(year, month)] += daily["precipitation_sum"][idx] or 0.0
            yearly_pet[(year, month)] += daily["et0_fao_evapotranspiration"][idx] or 0.0
        months: list[ClimateMonth] = []
        for month in range(1, 13):
            tmins, tmaxs = buckets[month]["tmin"], buckets[month]["tmax"]
            if not tmins:
                raise LandProfileUnavailable("Open-Meteo archive returned incomplete data")
            precip = [value for (year, m), value in yearly_precip.items() if m == month]
            pet = [value for (year, m), value in yearly_pet.items() if m == month]
            tmin_c, tmax_c = sum(tmins) / len(tmins), sum(tmaxs) / len(tmaxs)
            months.append(ClimateMonth(
                month=month, tmin_c=round(tmin_c, 1), tmax_c=round(tmax_c, 1), tmean_c=round((tmin_c + tmax_c) / 2, 1),
                precip_mm=round(sum(precip) / len(precip), 1), pet_mm=round(sum(pet) / len(pet), 1) if pet else None,
            ))
        return months


def annual_precip(profile: LandProfile) -> float:
    return round(sum(month.precip_mm for month in profile.climate), 1)


def profile_age_days(profile: LandProfile) -> float:
    return (datetime.now(UTC) - profile.fetched_at).total_seconds() / 86400


def hargreaves_monthly_pet(latitude: float, month: int, tmin: float, tmax: float) -> float:
    """FAO-56 Hargreaves reference ET for the middle day of a month, scaled to the month (mm)."""
    day_of_year = [15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349][month - 1]
    phi = math.radians(latitude)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    ra = (24 * 60 / math.pi) * 0.082 * dr * (ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws))
    et0_day = 0.0023 * ((tmin + tmax) / 2 + 17.8) * math.sqrt(max(tmax - tmin, 0.0)) * 0.408 * ra
    return et0_day * [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
