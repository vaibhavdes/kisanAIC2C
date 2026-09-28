"""Sentinel-2 field observations through Google Earth Engine.

* `fetch` returns the latest scene over the field that has at least half of its pixels
  cloud-free (pixel-level SCL masking), with NDVI / NDWI / NDMI / NDRE / EVI means.
* `satellite_map` renders an index map of the field from a recent cloud-free mosaic, measures
  the area of each fixed agronomic class, and compares the field median with nearby cropland
  (ESA WorldCover class 40) so a low value can be read against local season conditions.
Spectral indices describe canopy vigour and moisture; they are never converted into soil-test
claims.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..models import EvidenceSnapshot, EvidenceValue, Farm, SatelliteMapResult, SatelliteZone
from ..settings import Settings, get_settings

CLOUD_CLASSES = (1, 3, 8, 9, 10, 11)  # SCL: saturated, cloud shadow, clouds (med/high), cirrus, snow
INDEX_BANDS = {"NDVI": ("B8", "B4"), "NDWI": ("B3", "B8"), "NDMI": ("B8", "B11")}

# Fixed thresholds so a class means the same thing on every field (label, colour, lower, upper).
INDEX_CLASSES: dict[str, list[tuple[str, str, float, float]]] = {
    "NDVI": [("bare_or_sparse", "#b45309", -1.0, 0.2), ("low_vigour", "#f59e0b", 0.2, 0.35), ("moderate_vigour", "#facc15", 0.35, 0.5),
             ("good_vigour", "#84cc16", 0.5, 0.65), ("dense_canopy", "#15803d", 0.65, 1.0)],
    "NDMI": [("severe_water_stress", "#b91c1c", -1.0, -0.1), ("water_stress", "#f97316", -0.1, 0.05), ("moderate_moisture", "#facc15", 0.05, 0.2),
             ("adequate_moisture", "#38bdf8", 0.2, 0.35), ("high_moisture", "#1d4ed8", 0.35, 1.0)],
    "NDWI": [("dry_surface", "#a16207", -1.0, -0.3), ("mildly_moist", "#eab308", -0.3, -0.1), ("moist", "#67e8f9", -0.1, 0.1),
             ("wet", "#3b82f6", 0.1, 0.3), ("standing_water", "#1e3a8a", 0.3, 1.0)],
}
INDEX_MEANING = {
    "NDVI": "Crop vigour (NDVI)",
    "NDMI": "Canopy water content (NDMI)",
    "NDWI": "Surface wetness / standing water (NDWI)",
}


class SatelliteUnavailable(RuntimeError):
    pass


def _water_stress(ndvi, ndwi, ndmi) -> str:
    if ndvi is None and ndwi is None and ndmi is None:
        return "unknown"
    if ndmi is not None and ndmi < -0.1:
        return "high"
    if ndmi is not None and ndmi < 0.05:
        return "medium"
    if ndvi is not None and ndvi < 0.25:
        return "not_applicable"
    return "low"


def _vegetation_status(ndvi) -> str:
    if ndvi is None:
        return "unknown"
    return "bare_or_sparse" if ndvi < 0.2 else "low" if ndvi < 0.35 else "moderate" if ndvi < 0.5 else "good" if ndvi < 0.65 else "dense"


def _moisture_status(ndmi) -> str:
    if ndmi is None:
        return "unknown"
    return "very_dry" if ndmi < -0.1 else "dry" if ndmi < 0.05 else "moderate" if ndmi < 0.2 else "adequate" if ndmi < 0.35 else "moist"


def _rounded(value) -> float | None:
    return None if value is None else round(float(value), 3)


class SatelliteProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    # shared -----------------------------------------------------------------------------
    @staticmethod
    def _geometry(ee, farm: Farm) -> tuple[Any, str]:
        if farm.boundary_coordinates and len(farm.boundary_coordinates) >= 3:
            coords = [[float(pt[1]), float(pt[0])] for pt in farm.boundary_coordinates]
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            return ee.Geometry.Polygon([coords]), "farm_polygon"
        return ee.Geometry.Point([farm.location.longitude, farm.location.latitude]).buffer(60), "point_buffer"

    @staticmethod
    def _masked_collection(ee, region, start: date, end: date):
        def clean(image):
            scl = image.select("SCL")
            clear = scl.remap(list(CLOUD_CLASSES), [0] * len(CLOUD_CLASSES), 1)
            masked = image.updateMask(clear)
            bands = [masked.normalizedDifference(list(pair)).rename(name) for name, pair in INDEX_BANDS.items()]
            ndre = masked.normalizedDifference(["B8", "B5"]).rename("NDRE")
            evi = masked.expression(
                "2.5 * ((nir-red) / (nir+6*red-7.5*blue+1))",
                {"nir": masked.select("B8").divide(10000), "red": masked.select("B4").divide(10000), "blue": masked.select("B2").divide(10000)},
            ).rename("EVI")
            return masked.addBands(bands + [ndre, evi])

        return (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(region)
            .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 70))
            .map(clean)
        )

    # evidence ---------------------------------------------------------------------------
    def fetch(self, farm: Farm, days: int = 45) -> EvidenceSnapshot:
        if not self.settings.earth_engine_enabled:
            raise SatelliteUnavailable("Earth Engine is disabled")
        try:
            import ee

            ee.Initialize(project=self.settings.google_cloud_project)
            end = datetime.now(UTC).date()
            geometry, scope = self._geometry(ee, farm)
            collection = self._masked_collection(ee, geometry, end - timedelta(days=days), end)

            def with_coverage(image):
                valid = image.select("NDVI").mask().reduceRegion(ee.Reducer.mean(), geometry, 20, maxPixels=250000).get("NDVI")
                return image.set("valid_fraction", ee.Algorithms.If(valid, valid, 0))

            ranked = collection.map(with_coverage).filter(ee.Filter.gte("valid_fraction", 0.5)).sort("system:time_start", False)
            image = ee.Image(ranked.first())
            info = ee.Dictionary({
                "count": ranked.size(),
                "time": image.get("system:time_start"),
                "valid": image.get("valid_fraction"),
                "values": image.select(["NDVI", "NDWI", "NDMI", "NDRE", "EVI"]).reduceRegion(ee.Reducer.mean(), geometry, 20, maxPixels=250000),
            }).getInfo()
        except Exception as exc:
            if "count" in str(exc) or "first" in str(exc).lower():
                raise SatelliteUnavailable("No cloud-free Sentinel-2 scene over the field in the last 45 days") from exc
            raise SatelliteUnavailable(f"Earth Engine query failed: {str(exc)[:200]}") from exc
        if not info.get("count"):
            raise SatelliteUnavailable("No cloud-free Sentinel-2 scene over the field in the last 45 days")
        values = info.get("values") or {}
        acquired = datetime.fromtimestamp(float(info["time"]) / 1000, tz=UTC)
        flags = [] if scope == "farm_polygon" else ["point_buffer_60m_no_boundary"]
        return EvidenceSnapshot(
            farm_id=farm.id,
            node_id=farm.node_id,
            provider="earth_engine_sentinel_2",
            kind="satellite_observation",
            mode="live",
            observed_at=acquired,
            valid_until=acquired + timedelta(days=12),
            spatial_scope=scope,
            values=[EvidenceValue(name=name.lower(), value=_rounded(value)) for name, value in values.items()] + [
                EvidenceValue(name="valid_pixel_coverage", value=_rounded(info.get("valid")), unit="fraction"),
                EvidenceValue(name="water_stress", value=_water_stress(values.get("NDVI"), values.get("NDWI"), values.get("NDMI"))),
                EvidenceValue(name="vegetation_status", value=_vegetation_status(values.get("NDVI"))),
                EvidenceValue(name="moisture_status", value=_moisture_status(values.get("NDMI"))),
            ],
            quality_flags=flags,
            source_reference="COPERNICUS/S2_SR_HARMONIZED",
        )

    # map --------------------------------------------------------------------------------
    def satellite_map(self, farm: Farm, index: str = "NDVI", days: int = 30) -> SatelliteMapResult:
        index = index.upper()
        if index not in INDEX_CLASSES:
            raise ValueError(f"Unsupported satellite index: {index}")
        end = date.today()
        start = end - timedelta(days=days)
        legend = [{"class": label, "color": color, "min": low, "max": high} for label, color, low, high in INDEX_CLASSES[index]]
        base = {
            "farm_id": farm.id, "index": index, "meaning": INDEX_MEANING[index],
            "image_api_path": f"/api/v1/farms/{farm.id}/satellite/image?index={index}",
            "start_date": start.isoformat(), "end_date": end.isoformat(), "legend": legend,
        }
        if not self.settings.earth_engine_enabled:
            return SatelliteMapResult(**base, source="earth_engine_disabled", data_mode="missing",
                                      note="Satellite analysis is not enabled on this node.")
        try:
            return self._satellite_map_live(farm, index, start, end, base)
        except SatelliteUnavailable as exc:
            return SatelliteMapResult(**base, source="earth_engine_sentinel_2", data_mode="missing", note=str(exc))
        except Exception as exc:  # noqa: BLE001
            return SatelliteMapResult(**base, source="earth_engine_error", data_mode="missing", note=f"Earth Engine query failed: {str(exc)[:160]}")

    def _map_image(self, ee, farm: Farm, index: str, start: date, end: date):
        geometry, scope = self._geometry(ee, farm)
        neighbourhood = geometry.centroid(1).buffer(2000)
        collection = self._masked_collection(ee, neighbourhood, start, end).sort("system:time_start")
        layer = collection.select(index).mosaic().rename(index)  # latest valid pixel on top
        return geometry, scope, neighbourhood, collection, layer

    def _satellite_map_live(self, farm: Farm, index: str, start: date, end: date, base: dict[str, Any]) -> SatelliteMapResult:
        import ee

        ee.Initialize(project=self.settings.google_cloud_project)
        geometry, scope, neighbourhood, collection, layer = self._map_image(ee, farm, index, start, end)
        classes = INDEX_CLASSES[index]
        classified = ee.Image(0)
        for idx, (_, _, low, _) in enumerate(classes):
            classified = classified.where(layer.gte(low), idx + 1)
        classified = classified.updateMask(layer.mask()).rename("class")

        cropland = ee.ImageCollection("ESA/WorldCover/v200").first().eq(40)
        neighbours = layer.updateMask(cropland).clip(neighbourhood.difference(geometry, 1))
        percentiles = list(range(5, 100, 5))
        info = ee.Dictionary({
            "count": collection.size(),
            "latest": collection.aggregate_max("system:time_start"),
            "cloud": collection.aggregate_mean("CLOUDY_PIXEL_PERCENTAGE"),
            "areas": ee.Image.pixelArea().addBands(classified).reduceRegion(
                reducer=ee.Reducer.sum().group(groupField=1, groupName="class"), geometry=geometry, scale=10, maxPixels=1e8),
            "field": layer.reduceRegion(ee.Reducer.median(), geometry, 10, maxPixels=1e8),
            "neighbours": neighbours.reduceRegion(ee.Reducer.percentile(percentiles), neighbourhood, 20, maxPixels=1e8),
        }).getInfo()
        if not info.get("count"):
            raise SatelliteUnavailable(f"No Sentinel-2 scene with clear sky over the field between {start} and {end}")

        groups = {int(item["class"]): float(item["sum"]) for item in (info.get("areas") or {}).get("groups", [])}
        total = sum(groups.values())
        zones: list[SatelliteZone] = []
        for idx, (label, color, low, high) in enumerate(classes, start=1):
            area_m2 = groups.get(idx, 0.0)
            zones.append(SatelliteZone(id=idx, color=color, label=label, min_val=low, max_val=high,
                                       area_acres=round(area_m2 / 4046.86, 2), percentage=round(100 * area_m2 / total, 1) if total else 0.0))
        field_median = (info.get("field") or {}).get(index)
        neighbour_values = info.get("neighbours") or {}
        neighbour_median = neighbour_values.get(f"{index}_p50")
        percentile = None
        if field_median is not None and neighbour_median is not None:
            below = [p for p in percentiles if neighbour_values.get(f"{index}_p{p}") is not None and neighbour_values[f"{index}_p{p}"] <= field_median]
            percentile = float(max(below)) if below else 0.0
        latest = datetime.fromtimestamp(float(info["latest"]) / 1000, tz=UTC) if info.get("latest") else None
        status = None
        if percentile is not None:
            status = "below_neighbours" if percentile <= 25 else "above_neighbours" if percentile >= 75 else "similar_to_neighbours"
        return SatelliteMapResult(
            **base,
            scene_date=latest.strftime("%Y-%m-%d") if latest else None,
            scene_count=int(info["count"]),
            cloud_coverage_percent=round(float(info["cloud"]), 1) if info.get("cloud") is not None else None,
            geometry=scope,
            field_median=_rounded(field_median),
            neighbour_cropland_median=_rounded(neighbour_median),
            neighbour_percentile=percentile,
            field_status=status,
            source="earth_engine_sentinel_2",
            zones=zones if total else [],
            data_mode="live",
            note=None if scope == "farm_polygon" else "No field boundary plotted: values cover a 60 m circle around the farm point.",
        )

    def satellite_image_bytes(self, farm: Farm, index: str = "NDVI", days: int = 30) -> tuple[bytes, str]:
        """PNG of the classified index over the field (server-side proxy; no keys reach the browser)."""
        import requests

        if not self.settings.earth_engine_enabled:
            raise SatelliteUnavailable("Satellite analysis is not enabled on this node")
        import ee

        index = index.upper()
        ee.Initialize(project=self.settings.google_cloud_project)
        end = date.today()
        geometry, _, _, _, layer = self._map_image(ee, farm, index, end - timedelta(days=days), end)
        classes = INDEX_CLASSES[index]
        palette = [color for _, color, _, _ in classes]
        classified = ee.Image(0)
        for idx, (_, _, low, _) in enumerate(classes):
            classified = classified.where(layer.gte(low), idx)
        classified = classified.updateMask(layer.mask()).clip(geometry.buffer(40))
        outline = ee.Image().byte().paint(featureCollection=ee.FeatureCollection([ee.Feature(geometry)]), color=1, width=2)
        preview = classified.visualize(min=0, max=len(classes) - 1, palette=palette).blend(outline.visualize(palette=["#ffffff"]))
        url = preview.getThumbURL({"region": geometry.buffer(60).bounds(), "dimensions": 640, "format": "png"})
        for attempt in range(2):
            try:
                response = requests.get(url, timeout=25)
            except requests.RequestException as exc:
                if attempt:
                    raise SatelliteUnavailable("Earth Engine thumbnail request failed") from exc
                continue
            if response.status_code == 200:
                return response.content, response.headers.get("content-type", "image/png")
        raise SatelliteUnavailable("Earth Engine thumbnail request failed")
