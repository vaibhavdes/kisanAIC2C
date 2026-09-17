/**
 * Calculates geodesic acreage from 3-5 boundary corner coordinates
 * using planar projection with WGS-84 metric scaling.
 */
export function calculateGeodesicAcres(
  coords: Array<[number, number]>,
  centerLat: number,
  centerLon: number
): number {
  if (coords.length < 3) return 1.0;
  const cosLat = Math.cos((centerLat * Math.PI) / 180);
  const pts = coords.map(([lat, lon]) => ({
    x: (lon - centerLon) * 111320 * cosLat,
    y: (lat - centerLat) * 110574
  }));
  let areaM2 = 0;
  for (let i = 0; i < pts.length; i++) {
    const j = (i + 1) % pts.length;
    areaM2 += pts[i].x * pts[j].y - pts[j].x * pts[i].y;
  }
  areaM2 = Math.abs(areaM2) * 0.5;
  const acres = areaM2 / 4046.86;
  return Math.max(0.1, Math.round(acres * 100) / 100);
}
