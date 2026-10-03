import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export interface NeighbourPoint { lat: number; lon: number; crop: string; village?: string | null; mine?: boolean }

// Fixed categorical order so a crop keeps its colour whichever crop is selected.
export const CROP_COLORS = ["#2a78d4", "#d9822b", "#2f9e5b", "#b3478f", "#8a6d1f", "#5b5fc7"];

/** Neighbours' planned crops around the farm; the selected crop is drawn larger, others muted. */
export function NeighbourMap({ points, center, crop, colorOf, nameOf }: {
  points: NeighbourPoint[]; center: [number, number]; crop: string;
  colorOf: (crop: string) => string; nameOf: (crop: string) => string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!box.current || map.current) return;
    const m = L.map(box.current, { zoomControl: true, scrollWheelZoom: false }).setView(center, 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap contributors" }).addTo(m);
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    if (!layer.current) return;
    layer.current.clearLayers();
    // A small offset so several plans at the same rounded point stay visible.
    const seen: Record<string, number> = {};
    points.forEach(p => {
      const key = `${p.lat},${p.lon}`;
      const n = (seen[key] = (seen[key] || 0) + 1) - 1;
      const pos: [number, number] = [p.lat + (n % 3) * 0.0012, p.lon + Math.floor(n / 3) * 0.0012];
      const on = p.crop === crop;
      L.circleMarker(pos, {
        radius: on ? 8 : 5, color: "#ffffff", weight: 2, fillColor: colorOf(p.crop), fillOpacity: on ? 0.95 : 0.45,
      }).bindTooltip(`${nameOf(p.crop)}${p.village ? ` · ${p.village}` : ""}`).addTo(layer.current!);
    });
    L.circleMarker(center, { radius: 10, color: "#0f291e", weight: 3, fillColor: "#9dd84b", fillOpacity: 1 })
      .bindTooltip("Your farm").addTo(layer.current);
  }, [points, crop]);

  return <div ref={box} className="mk-map" />;
}
