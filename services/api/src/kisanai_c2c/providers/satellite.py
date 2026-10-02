from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Any

from ..models import EvidenceSnapshot, EvidenceValue, Farm
from ..settings import Settings, get_settings


class SatelliteUnavailable(RuntimeError):
    pass


# Agronomic class breaks per index (fixed, so areas are comparable between fields and dates).
# Each class: (lower bound, upper bound, colour, label). Bounds are inclusive-exclusive.
INDEX_CLASSES: dict[str, list[tuple[float, float, str, str]]] = {
    "NDVI": [
        (-1.0, 0.2, "#d73027", "Bare soil / very low vigour"),
        (0.2, 0.35, "#fdae61", "Sparse or stressed crop"),
        (0.35, 0.5, "#fee08b", "Moderate crop cover"),
        (0.5, 0.65, "#a6d96a", "Healthy crop"),
        (0.65, 1.0, "#1a9850", "Dense, vigorous crop"),
    ],
    "NDMI": [
        (-1.0, -0.1, "#7f0000", "Severe water stress"),
        (-0.1, 0.05, "#d73027", "High water stress"),
        (0.05, 0.2, "#fee08b", "Moderate canopy moisture"),
        (0.2, 0.35, "#91bfdb", "Adequate canopy moisture"),
        (0.35, 1.0, "#104e8b", "High canopy moisture"),
    ],
    "NDWI": [
        (-1.0, -0.3, "#d73027", "Dry surface / dense canopy"),
        (-0.3, -0.15, "#fee08b", "Mildly moist surface"),
        (-0.15, 0.0, "#74add1", "Moist surface"),
        (0.0, 0.2, "#4575b4", "Wet / water-logged"),
        (0.2, 1.0, "#313695", "Standing water"),
    ],
}
INDEX_BANDS = {"NDVI": ("B8", "B4"), "NDMI": ("B8", "B11"), "NDWI": ("B3", "B8")}
SQ_M_PER_ACRE = 4046.8564224
EE_DEADLINE_MS = 20_000  # per Earth Engine call


class SatelliteProvider:
    """Adapted from the original Kisan Alert Earth Engine index service.

    The C2C implementation adds pixel-level cloud masking, acquisition/coverage
    metadata, and avoids translating spectral indices into soil-test claims.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _init_ee(self, ee) -> None:
        ee.Initialize(project=self.settings.google_cloud_project)
        # Without a deadline a slow Earth Engine call holds the request until Cloud Run kills it.
        ee.data.setDeadline(EE_DEADLINE_MS)

    @staticmethod
    def _water_stress(ndvi, ndwi, ndmi) -> str:
        """Crop water stress from leaf water (NDMI). NDWI is not used: it is negative over any
        green canopy, so it cannot separate stressed from healthy crop. Over bare soil
        (NDVI < 0.2) there is no crop to be stressed."""
        if ndmi is None or ndvi is None or ndvi < 0.2:
            return "unknown"
        if ndmi < -0.1:
            return "high"
        if ndmi < 0.05:  # same breakpoints as _moisture_status and the NDMI map zones
            return "medium"
        return "low"

    @staticmethod
    def _vegetation_status(ndvi) -> str:
        if ndvi is None:
            return "unknown"
        # Same breaks as the NDVI map zones (INDEX_CLASSES), so card and map agree.
        return "poor" if ndvi < 0.35 else "moderate" if ndvi < 0.5 else "healthy"

    @staticmethod
    def _moisture_status(ndmi) -> str:
        if ndmi is None:
            return "unknown"
        # Same breaks as the NDMI map zones.
        return "very_dry" if ndmi < -0.1 else "dry" if ndmi < 0.05 else "adequate" if ndmi < 0.35 else "moist"

    @staticmethod
    def _chlorophyll_status(ndre) -> str:
        if ndre is None:
            return "unknown"
        return "low" if ndre < 0.18 else "medium" if ndre < 0.32 else "good"

    @staticmethod
    def _rounded(value) -> float | None:
        if value is None:
            return None
        return round(float(value), 3)

    def fetch(self, farm: Farm, days: int = 45) -> EvidenceSnapshot:
        if not self.settings.earth_engine_enabled:
            raise SatelliteUnavailable("Earth Engine is disabled")
        try:
            import ee
            self._init_ee(ee)
            end = datetime.now(UTC)
            start = end - timedelta(days=days)
            geometry, _ = self._geometry(ee, farm)

            def clear_mask(image):
                scl = image.select("SCL")
                return scl.neq(1).And(scl.neq(3)).And(scl.neq(7)).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))

            def with_clear_share(image):
                share = clear_mask(image).rename("clear").reduceRegion(ee.Reducer.mean(), geometry, 20, maxPixels=250000).get("clear")
                return image.set("clear_share", share)

            # Same scene choice as the satellite map: the newest one that is mostly clear over the
            # field. The newest scene alone is often cloudy here, which left every value empty.
            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(geometry)
                .filterDate(start.date().isoformat(), (end.date() + timedelta(days=1)).isoformat())
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 70))
                .map(with_clear_share)
                .filter(ee.Filter.gte("clear_share", 0.6))
                .sort("system:time_start", False)
            )
            times = collection.limit(1).aggregate_array("system:time_start").getInfo() or []
            if not times:
                raise SatelliteUnavailable(f"No Sentinel-2 scene with at least 60% clear sky over the field in the last {days} days")
            # Indices are computed only for the chosen scene.
            scene = ee.Image(collection.first())
            clean = scene.updateMask(clear_mask(scene))
            image = ee.Image.cat([
                clean.normalizedDifference(["B8", "B4"]).rename("NDVI"),
                clean.normalizedDifference(["B3", "B8"]).rename("NDWI"),
                clean.normalizedDifference(["B8", "B11"]).rename("NDMI"),
                clean.normalizedDifference(["B8", "B5"]).rename("NDRE"),
                clean.expression(
                    "2.5 * ((nir-red) / (nir+6*red-7.5*blue+1))",
                    {"nir": clean.select("B8").divide(10000), "red": clean.select("B4").divide(10000), "blue": clean.select("B2").divide(10000)},
                ).rename("EVI"),
            ])
            acquired = datetime.fromtimestamp(float(times[0]) / 1000, tz=UTC)
            # Index medians (as on the map) and the clear-pixel share in one Earth Engine round trip.
            combined = ee.Dictionary({
                "values": image.select(["NDVI", "NDWI", "NDMI", "NDRE", "EVI"]).reduceRegion(
                    reducer=ee.Reducer.median(), geometry=geometry, scale=10, maxPixels=1_000_000),
                "valid": image.select("NDVI").mask().reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=geometry, scale=20, maxPixels=250000),
            }).getInfo() or {}
            values = combined.get("values") or {}
            valid = combined.get("valid") or {}
        except SatelliteUnavailable:
            raise
        except Exception as exc:
            raise SatelliteUnavailable(f"Earth Engine query failed: {exc}") from exc
        coverage = float(valid.get("NDVI") or 0)
        flags = [] if farm.boundary_coordinates and len(farm.boundary_coordinates) >= 3 else ["point_buffer_approximation"]
        if coverage < 0.5:
            flags.append("low_valid_pixel_coverage")
        return EvidenceSnapshot(
            farm_id=farm.id,
            node_id=farm.node_id,
            provider="earth_engine_sentinel_2",
            kind="satellite_observation",
            mode="live",
            observed_at=acquired,
            valid_until=acquired + timedelta(days=12),
            spatial_scope="farm_polygon" if not flags or flags[0] != "point_buffer_approximation" else "125m_point_buffer",
            values=[
                EvidenceValue(name=name.lower(), value=self._rounded(value))
                for name, value in values.items()
            ] + [
                EvidenceValue(name="valid_pixel_coverage", value=self._rounded(coverage), unit="fraction"),
                EvidenceValue(name="water_stress", value=self._water_stress(values.get("NDVI"), values.get("NDWI"), values.get("NDMI"))),
                EvidenceValue(name="vegetation_status", value=self._vegetation_status(values.get("NDVI"))),
                EvidenceValue(name="moisture_status", value=self._moisture_status(values.get("NDMI"))),
                EvidenceValue(name="chlorophyll_status", value=self._chlorophyll_status(values.get("NDRE"))),
            ],
            quality_flags=flags,
            source_reference="COPERNICUS/S2_SR_HARMONIZED",
        )

    @staticmethod
    def _geometry(ee, farm: Farm) -> tuple[Any, str]:
        if farm.boundary_coordinates and len(farm.boundary_coordinates) >= 3:
            coords = [[float(pt[1]), float(pt[0])] for pt in farm.boundary_coordinates]
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            return ee.Geometry.Polygon([coords]), "farm_polygon"
        return ee.Geometry.Point([farm.location.longitude, farm.location.latitude]).buffer(125), "point_buffer"

    @staticmethod
    def _preview_style(index: str) -> tuple[str, dict, dict[str, str]]:
        meanings = {
            "NDVI": "Crop growth and vigour (NDVI)",
            "NDMI": "Crop canopy moisture (NDMI)",
            "NDWI": "Surface wetness and standing water (NDWI)",
        }
        if index not in INDEX_CLASSES:
            raise ValueError(f"Unsupported satellite index: {index}")
        classes = INDEX_CLASSES[index]
        vis = {"min": classes[0][1] - 0.1, "max": classes[-1][0] + 0.1, "palette": [c[2] for c in classes]}
        return meanings[index], vis, {c[2]: c[3] for c in classes}

    @staticmethod
    def shape_key(farm: Farm) -> str:
        """Fingerprint of the field's position and shape; a stored map is reused only while it matches."""
        shape = json.dumps([farm.location.latitude, farm.location.longitude, farm.boundary_coordinates, farm.area_value, farm.area_unit])
        return hashlib.sha1(shape.encode()).hexdigest()[:12]

    @staticmethod
    def download_image(map_url: str) -> bytes:
        """The Earth Engine thumbnail link expires within hours, so the PNG itself is kept."""
        import requests

        response = requests.get(map_url, timeout=20)
        if response.status_code != 200 or len(response.content) < 100:
            raise SatelliteUnavailable(f"Earth Engine thumbnail download failed ({response.status_code})")
        return response.content

    def satellite_map(self, farm: Farm, index: str = "NDVI", days: int = 30) -> "SatelliteMapResult":
        """Latest mostly-clear Sentinel-2 scene over the field: index map, measured zone areas and summary.

        Every call queries Earth Engine; AppService stores the result. A failure is reported as
        data_mode="missing" with the reason, never replaced with estimated values.
        """
        from ..models import SatelliteMapResult

        normalized = index.upper()
        meaning, vis, legend = self._preview_style(normalized)

        end = datetime.now(UTC).date()
        start = end - timedelta(days=days)
        has_boundary = bool(farm.boundary_coordinates and len(farm.boundary_coordinates) >= 3)
        base = dict(
            farm_id=farm.id, index=normalized, meaning=meaning,
            image_api_path=f"/api/v1/farms/{farm.id}/satellite/image?index={normalized}&days={days}",
            start_date=start.isoformat(), end_date=end.isoformat(), legend=legend,
        )

        def missing(reason: str) -> SatelliteMapResult:
            # Not stored, so the next request tries again.
            return SatelliteMapResult(**base, source="earth_engine_sentinel_2", data_mode="missing", zones=[],
                                      field_status_narrative=None, acquisition_note=reason)

        if not self.settings.earth_engine_enabled:
            return missing("Satellite analysis is turned off on this server (EARTH_ENGINE_ENABLED=false).")

        try:
            import ee
            self._init_ee(ee)
            geometry, _ = self._geometry(ee, farm)
            low_band, high_band = INDEX_BANDS[normalized][1], INDEX_BANDS[normalized][0]

            def prepare(image):
                scl = image.select("SCL")
                clear = scl.neq(1).And(scl.neq(3)).And(scl.neq(7)).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
                layer = image.updateMask(clear).normalizedDifference([high_band, low_band]).rename("index")
                share = layer.mask().reduceRegion(ee.Reducer.mean(), geometry, 20, maxPixels=250000).get("index")
                return layer.copyProperties(image, ["system:time_start", "CLOUDY_PIXEL_PERCENTAGE"]).set("clear_share", share)

            scenes = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(geometry)
                .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 70))
                .map(prepare)
                .filter(ee.Filter.gte("clear_share", 0.6))
                .sort("system:time_start", False)
            )
            first = scenes.limit(1)
            meta = first.reduceColumns(ee.Reducer.toList(3), ["system:time_start", "CLOUDY_PIXEL_PERCENTAGE", "clear_share"]).getInfo()
            rows = (meta or {}).get("list") or []
            if not rows:
                return missing(f"No Sentinel-2 scene with at least 60% clear sky over the field between {start} and {end}.")
            scene_ms, scene_cloud, clear_share = rows[0]
            layer = ee.Image(first.first()).clip(geometry)

            classes = INDEX_CLASSES[normalized]
            class_image = ee.Image(0)
            for number, (lower, _, _, _) in enumerate(classes[1:], start=1):
                class_image = class_image.where(layer.gte(lower), number)
            class_image = class_image.updateMask(layer.mask()).rename("zone")
            area = ee.Image.pixelArea().addBands(class_image)
            stats = ee.Dictionary({
                "area": area.reduceRegion(ee.Reducer.sum().group(groupField=1, groupName="zone"), geometry, 10, maxPixels=1_000_000),
                "mean": layer.addBands(class_image).reduceRegion(ee.Reducer.mean().group(groupField=1, groupName="zone"), geometry, 10, maxPixels=1_000_000),
                "overall": layer.reduceRegion(ee.Reducer.median().combine(ee.Reducer.minMax(), sharedInputs=True), geometry, 10, maxPixels=1_000_000),
                # The thumbnail covers exactly this box, so the app can lay it over a map.
                "bounds": geometry.bounds().coordinates(),
            }).getInfo() or {}

            boundary = ee.Image().byte().paint(featureCollection=ee.FeatureCollection([ee.Feature(geometry)]), color=1, width=2)
            map_url = layer.visualize(**vis).blend(boundary.visualize(palette=["#00ffff"])).getThumbURL(
                {"region": geometry.bounds(), "dimensions": 600, "format": "png"})
        except Exception as exc:
            return missing(f"Earth Engine query failed: {str(exc)[:160]}")

        zones = self._zones(normalized, stats)
        overall = stats.get("overall") or {}
        median = overall.get("index_median")
        scene_dt = datetime.fromtimestamp(float(scene_ms) / 1000, tz=UTC)
        scope = "field boundary" if has_boundary else "125 m around the farm point (draw the field boundary for parcel-level zones)"
        ring = (stats.get("bounds") or [[]])[0]
        bounds = None
        if ring:
            lons, lats = [point[0] for point in ring], [point[1] for point in ring]
            bounds = [[min(lats), min(lons)], [max(lats), max(lons)]]
        result = SatelliteMapResult(
            **base,
            map_url=map_url,
            bounds=bounds,
            clear_percent=round(float(clear_share) * 100),
            median=round(float(median), 3) if median is not None else None,
            scene_date=scene_dt.strftime("%d %b %Y"),
            cloud_coverage_percent=round(float(scene_cloud), 1) if scene_cloud is not None else None,
            field_status_narrative=self._narrative(normalized, median, zones),
            source="earth_engine_sentinel_2",
            zones=zones,
            data_mode="live",
            acquisition_note=(
                f"Sentinel-2 L2A scene of {scene_dt.strftime('%d %b %Y')}; {round(float(clear_share) * 100)}% of the area cloud-free; "
                f"clouds and shadows masked. Area: {scope}."
            ),
        )
        return result

    @staticmethod
    def _zones(index: str, stats: dict[str, Any]) -> list["SatelliteZone"]:
        from ..models import SatelliteZone

        areas = {int(row["zone"]): float(row.get("sum") or 0) for row in (stats.get("area") or {}).get("groups", [])}
        means = {int(row["zone"]): row.get("mean") for row in (stats.get("mean") or {}).get("groups", [])}
        total = sum(areas.values())
        if total <= 0:
            return []
        zones = []
        for number, (lower, upper, colour, label) in enumerate(INDEX_CLASSES[index]):
            area_m2 = areas.get(number, 0.0)
            if area_m2 <= 0:
                continue
            mean = means.get(number)
            zones.append(SatelliteZone(
                id=number + 1, color=colour, label=label,
                min_val=max(lower, -1.0), max_val=min(upper, 1.0),
                median_val=round(float(mean), 3) if mean is not None else round((lower + upper) / 2, 3),
                area_acres=round(area_m2 / SQ_M_PER_ACRE, 2),
                percentage=round(area_m2 / total * 100, 1),
            ))
        return zones

    @staticmethod
    def _narrative(index: str, median: float | None, zones: list["SatelliteZone"]) -> str | None:
        if median is None or not zones:
            return None
        dominant = max(zones, key=lambda zone: zone.percentage)
        return f"Median {index} {median:.2f}. Largest zone: {dominant.label.lower()} ({dominant.percentage:.0f}% of the area, {dominant.area_acres:.2f} acres)."
