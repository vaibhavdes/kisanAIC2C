import React, { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { T } from "../types";

export type LatLon = [number, number];

interface FieldMapProps {
  t: T;
  center: LatLon;
  zoom?: number;
  corners: LatLon[];
  onCornersChange: (corners: LatLon[]) => void;
  onCenterChange?: (center: LatLon) => void;
  maxCorners?: number;
}

const cornerIcon = (n: number) =>
  L.divIcon({ className: "corner-marker", html: `<span>${n}</span>`, iconSize: [26, 26], iconAnchor: [13, 13] });

/**
 * Satellite basemap where the farmer taps the corners of the field. Corners can be dragged to
 * adjust. Imagery: Esri World Imagery; place names: OpenStreetMap contributors.
 */
export function FieldMap({ t, center, zoom = 17, corners, onCornersChange, onCenterChange, maxCorners = 8 }: FieldMapProps) {
  const holder = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const cornersRef = useRef(corners);
  cornersRef.current = corners;

  useEffect(() => {
    if (!holder.current || map.current) return;
    const instance = L.map(holder.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: false }).setView(center, zoom);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19,
      attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics",
    }).addTo(instance);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
    }).addTo(instance);
    layer.current = L.layerGroup().addTo(instance);
    instance.on("click", (event: L.LeafletMouseEvent) => {
      if (cornersRef.current.length >= maxCorners) return;
      onCornersChange([...cornersRef.current, [Number(event.latlng.lat.toFixed(6)), Number(event.latlng.lng.toFixed(6))]]);
    });
    instance.on("moveend", () => {
      const c = instance.getCenter();
      onCenterChange?.([Number(c.lat.toFixed(5)), Number(c.lng.toFixed(5))]);
    });
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const current = instance.getCenter();
    if (Math.abs(current.lat - center[0]) > 1e-4 || Math.abs(current.lng - center[1]) > 1e-4) {
      instance.setView(center, 17);
    }
  }, [center[0], center[1]]);

  useEffect(() => {
    const group = layer.current;
    if (!group) return;
    group.clearLayers();
    if (corners.length >= 3) {
      L.polygon(corners, { color: "#facc15", weight: 3, fillColor: "#facc15", fillOpacity: 0.18 }).addTo(group);
    } else if (corners.length === 2) {
      L.polyline(corners, { color: "#facc15", weight: 3, dashArray: "6 4" }).addTo(group);
    }
    corners.forEach((corner, idx) => {
      const marker = L.marker(corner, { draggable: true, icon: cornerIcon(idx + 1), keyboard: false }).addTo(group);
      marker.on("dragend", () => {
        const pos = marker.getLatLng();
        const next = [...cornersRef.current];
        next[idx] = [Number(pos.lat.toFixed(6)), Number(pos.lng.toFixed(6))];
        onCornersChange(next);
      });
    });
  }, [corners]);

  return <div ref={holder} className="field-map" role="application" aria-label={t("map_aria")} />;
}

/** Geodesic polygon area in hectares (spherical excess on a local equirectangular projection). */
export function polygonAreaHa(points: LatLon[]): number {
  if (points.length < 3) return 0;
  const R = 6371008.8;
  const lat0 = (points.reduce((sum, p) => sum + p[0], 0) / points.length) * (Math.PI / 180);
  const xy = points.map(([lat, lon]) => [R * (lon * Math.PI / 180) * Math.cos(lat0), R * (lat * Math.PI / 180)]);
  let area = 0;
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i];
    const [x2, y2] = xy[(i + 1) % xy.length];
    area += x1 * y2 - x2 * y1;
  }
  return Math.abs(area) / 2 / 10000;
}
