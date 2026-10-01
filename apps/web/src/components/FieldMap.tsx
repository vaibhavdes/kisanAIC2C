import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export type LatLon = [number, number];

interface FieldMapProps {
  center: LatLon;
  boundary: LatLon[];
  /** When set, tapping the map adds a corner and corners can be dragged. */
  onBoundaryChange?: (coords: LatLon[]) => void;
  maxPoints?: number;
  /** Image laid over the field (e.g. the satellite index map) with its [south-west, north-east] bounds. */
  overlay?: { url: string; bounds: [LatLon, LatLon]; opacity: number } | null;
  height?: number;
  /** Change this to move the map back to the center (e.g. after a PIN code lookup). */
  recenterKey?: string;
}

// Satellite photo with place names on top, like other farm map tools; street map as an option.
const imagery = () =>
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19,
    maxNativeZoom: 18,
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
  });
const labels = () =>
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19,
    maxNativeZoom: 18,
  });
const streets = () =>
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap contributors",
  });

const cornerIcon = L.divIcon({ className: "field-corner", iconSize: [14, 14] });

export function FieldMap({ center, boundary, onBoundaryChange, maxPoints = 8, overlay, height = 380, recenterKey }: FieldMapProps) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const shapes = useRef<L.LayerGroup | null>(null);
  const image = useRef<L.ImageOverlay | null>(null);
  const latest = useRef({ boundary, onBoundaryChange, maxPoints });
  latest.current = { boundary, onBoundaryChange, maxPoints };

  // Create the map once.
  useEffect(() => {
    if (!box.current || map.current) return;
    const satellite = L.layerGroup([imagery(), labels()]);
    const m = L.map(box.current, { zoomControl: true, attributionControl: true }).setView(center, 17);
    satellite.addTo(m);
    L.control.layers({ Satellite: satellite, Map: streets() }, undefined, { position: "topright" }).addTo(m);
    L.control.scale({ imperial: false }).addTo(m);
    shapes.current = L.layerGroup().addTo(m);
    m.on("click", (event: L.LeafletMouseEvent) => {
      const { boundary: current, onBoundaryChange: change, maxPoints: max } = latest.current;
      if (!change || current.length >= max) return;
      change([...current, [Number(event.latlng.lat.toFixed(6)), Number(event.latlng.lng.toFixed(6))]]);
    });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  // Recenter when asked (new PIN / GPS location) or when a saved boundary is first shown.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (boundary.length >= 3) m.fitBounds(L.latLngBounds(boundary), { padding: [30, 30], maxZoom: 18 });
    else m.setView(center, Math.max(m.getZoom(), 16));
  }, [recenterKey, center[0], center[1]]);

  // Draw the field outline and draggable corners.
  useEffect(() => {
    const group = shapes.current;
    if (!group) return;
    group.clearLayers();
    if (boundary.length >= 2) {
      const style = { color: "#00e5ff", weight: 3, fillColor: "#00e5ff", fillOpacity: overlay ? 0 : 0.15 };
      (boundary.length >= 3 ? L.polygon(boundary, style) : L.polyline(boundary, style)).addTo(group);
    }
    if (onBoundaryChange) {
      boundary.forEach((point, index) => {
        const marker = L.marker(point, { icon: cornerIcon, draggable: true }).addTo(group);
        marker.on("dragend", () => {
          const { lat, lng } = marker.getLatLng();
          const next = [...latest.current.boundary];
          next[index] = [Number(lat.toFixed(6)), Number(lng.toFixed(6))];
          latest.current.onBoundaryChange?.(next);
        });
      });
    } else if (boundary.length === 0) {
      L.circleMarker(center, { radius: 6, color: "#fff", weight: 2, fillColor: "#e11d48", fillOpacity: 1 }).addTo(group);
    }
  }, [boundary, overlay, center[0], center[1]]);

  // Satellite index image over the field.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    image.current?.remove();
    image.current = null;
    if (overlay) {
      image.current = L.imageOverlay(overlay.url, overlay.bounds, { opacity: overlay.opacity, interactive: false }).addTo(m);
      shapes.current?.eachLayer(layer => (layer as L.Path).bringToFront?.());
      m.fitBounds(L.latLngBounds(overlay.bounds), { padding: [20, 20], maxZoom: 18 });
    }
  }, [overlay?.url, overlay?.bounds?.[0]?.[0]]);

  useEffect(() => {
    image.current?.setOpacity(overlay?.opacity ?? 1);
  }, [overlay?.opacity]);

  return <div ref={box} className="field-map" style={{ height }} />;
}
