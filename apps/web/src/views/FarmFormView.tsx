import React, { useState, useRef, FormEvent } from "react";
import { MapPin, Info, RefreshCw, CheckCircle2, ArrowRight } from "lucide-react";
import { api } from "../api";
import { Json } from "../types";
import { MAHARASHTRA_CROPS } from "../constants/crops";
import { MAHARASHTRA_DISTRICTS } from "../constants/districts";
import { calculateGeodesicAcres } from "../utils/geo";
import { SoilCardSection } from "./SoilCardSection";

export interface FarmFormViewProps {
  t: Record<string, string>;
  done: (id: string) => void;
}

export function FarmFormView({ t, done }: FarmFormViewProps) {
  const [formData, setFormData] = useState({
    name: "My Farm",
    pincode: "",
    state_name: "Maharashtra",
    state_code: "MH",
    district: "",
    village: "",
    latitude: "19.7500",
    longitude: "75.7100",
    area_value: "1",
    area_unit: "acre",
    water_access: "rainfed",
    soil_type: "black",
    current_crop: "",
    custom_crop: "",
    previous_crop: "",
    crop_status: "planning"
  });

  const [boundaryCoords, setBoundaryCoords] = useState<Array<[number, number]>>([]);
  const [savedFarmId, setSavedFarmId] = useState("");
  const [busy, setBusy] = useState(false);
  const [pincodeLoading, setPincodeLoading] = useState(false);
  const [pincodeMsg, setPincodeMsg] = useState("");
  const [geocoding, setGeocoding] = useState(false);
  const [geoAddress, setGeoAddress] = useState("");
  const [progressStep, setProgressStep] = useState("");

  const [postOffices, setPostOffices] = useState<Array<{
    name: string;
    latitude: number | null;
    longitude: number | null;
    district?: string;
    state?: string;
    office_type?: string;
  }>>([]);

  const [zoomLevel, setZoomLevel] = useState(1);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const latNum = parseFloat(formData.latitude) || 19.75;
  const lonNum = parseFloat(formData.longitude) || 75.71;

  // Coordinate viewport window for plotting canvas (scaled with zoomLevel)
  const dLon = 0.008 / zoomLevel;
  const dLat = 0.006 / zoomLevel;
  const minLon = lonNum - dLon;
  const maxLon = lonNum + dLon;
  const minLat = latNum - dLat;
  const maxLat = latNum + dLat;

  const handlePincodeLookup = async () => {
    const clean = formData.pincode.trim();
    if (clean.length !== 6 || !/^\d+$/.test(clean)) {
      alert("Please enter a valid 6-digit Indian PIN code (e.g. 431203)");
      return;
    }
    setPincodeLoading(true);
    setPincodeMsg("");
    setPostOffices([]);
    try {
      const geo = await api<any>(`/api/v1/geo/pincode/${clean}`);
      const offices = geo.post_offices || [];
      setPostOffices(offices);
      setFormData(prev => ({
        ...prev,
        state_name: geo.state_name || prev.state_name,
        state_code: geo.state_code || prev.state_code,
        district: geo.district || prev.district,
        village: geo.village || prev.village,
        latitude: String(Number(geo.latitude).toFixed(4)),
        longitude: String(Number(geo.longitude).toFixed(4))
      }));
      if (offices.length > 1) {
        setPincodeMsg(`✓ Found ${offices.length} village post offices in ${geo.district}, ${geo.state_name}. Choose your exact village from the dropdown below.`);
      } else {
        setPincodeMsg(`✓ Matched: ${geo.district}, ${geo.state_name} (${Number(geo.latitude).toFixed(2)}°N, ${Number(geo.longitude).toFixed(2)}°E)`);
      }
      setBoundaryCoords([]);
    } catch (e: any) {
      setPincodeMsg("❌ " + (e.message || "PIN code lookup failed. Please select your district from the dropdown."));
    } finally {
      setPincodeLoading(false);
    }
  };

  const handleVillageSelect = (villageName: string) => {
    const match = postOffices.find(p => p.name === villageName);
    if (match) {
      setFormData(prev => ({
        ...prev,
        village: match.name,
        district: match.district || prev.district,
        state_name: match.state || prev.state_name,
        latitude: match.latitude ? String(match.latitude.toFixed(4)) : prev.latitude,
        longitude: match.longitude ? String(match.longitude.toFixed(4)) : prev.longitude,
      }));
      setPincodeMsg(`✓ Selected Village: ${match.name} (${match.latitude ? match.latitude.toFixed(4) : "—"}°N, ${match.longitude ? match.longitude.toFixed(4) : "—"}°E)`);
      setBoundaryCoords([]);
    }
  };

  const locate = () => {
    setGeocoding(true);
    setGeoAddress("Detecting GPS coordinates & resolving district...");

    const applyCoordsAndReverse = async (lat: number, lon: number, sourceLabel: string) => {
      setFormData(prev => ({
        ...prev,
        latitude: lat.toFixed(4),
        longitude: lon.toFixed(4)
      }));
      setBoundaryCoords([]);
      try {
        const rev = await api<any>(`/api/v1/geo/reverse?latitude=${lat}&longitude=${lon}`);
        if (rev) {
          setFormData(prev => ({
            ...prev,
            district: rev.district || prev.district,
            state_name: rev.state_name || prev.state_name,
            state_code: rev.state_code || prev.state_code,
            village: rev.village || prev.village,
            pincode: rev.pincode || prev.pincode,
          }));
          const labelParts = [rev.village, rev.district, rev.state_name].filter(Boolean);
          setGeoAddress(`✓ ${sourceLabel}: ${labelParts.join(", ")} (${lat.toFixed(3)}°N, ${lon.toFixed(3)}°E)`);
        } else {
          setGeoAddress(`✓ ${sourceLabel}: ${lat.toFixed(4)}°N, ${lon.toFixed(4)}°E`);
        }
      } catch {
        setGeoAddress(`✓ ${sourceLabel}: ${lat.toFixed(4)}°N, ${lon.toFixed(4)}°E`);
      } finally {
        setGeocoding(false);
      }
    };

    const tryIpFallback = async () => {
      try {
        setGeoAddress("GPS unavailable on device. Detecting network location...");
        const ipGeo = await api<any>("/api/v1/geo/ip");
        if (ipGeo && ipGeo.latitude && ipGeo.longitude) {
          const lat = Number(ipGeo.latitude);
          const lon = Number(ipGeo.longitude);
          setFormData(prev => ({
            ...prev,
            latitude: lat.toFixed(4),
            longitude: lon.toFixed(4),
            district: ipGeo.district || prev.district,
            state_name: ipGeo.state_name || prev.state_name,
            state_code: ipGeo.state_code || prev.state_code,
            village: ipGeo.village || prev.village,
            pincode: ipGeo.pincode || prev.pincode,
          }));
          const labelParts = [ipGeo.village, ipGeo.district, ipGeo.state_name].filter(Boolean);
          setGeoAddress(`📍 Network Location Detected: ${labelParts.join(", ")} (${lat.toFixed(3)}°N, ${lon.toFixed(3)}°E)`);
          return;
        }
      } catch {
        // Continue to gentle guidance
      }
      setGeoAddress("⚠️ GPS signal unavailable on this device. Please enter your 6-digit PIN code or choose your district from the dropdown below.");
    };

    if (!navigator.geolocation) {
      tryIpFallback().finally(() => setGeocoding(false));
      return;
    }

    // 1. Try High Accuracy hardware GPS (10s timeout matching original morning setting)
    navigator.geolocation.getCurrentPosition(
      pos => {
        applyCoordsAndReverse(pos.coords.latitude, pos.coords.longitude, "GPS Location Detected");
      },
      err => {
        // If permission was denied by user
        if (err.code === 1) {
          setGeoAddress("Location permission not granted. Detecting network location...");
          tryIpFallback().finally(() => setGeocoding(false));
          return;
        }
        // 2. High accuracy unavailable or timed out -> Fallback to low accuracy (Wi-Fi/Cellular/Cache)
        navigator.geolocation.getCurrentPosition(
          pos => {
            applyCoordsAndReverse(pos.coords.latitude, pos.coords.longitude, "Location Detected");
          },
          () => {
            // 3. Both browser options failed -> Fallback to backend IP Geolocation
            tryIpFallback().finally(() => setGeocoding(false));
          },
          { enableHighAccuracy: false, timeout: 6000, maximumAge: 300000 }
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
  };

  const handleZoomIn = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setZoomLevel(prev => Math.min(Number((prev * 1.4).toFixed(2)), 5));
  };

  const handleZoomOut = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setZoomLevel(prev => Math.max(Number((prev / 1.4).toFixed(2)), 0.4));
  };

  const handleCanvasClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const relX = (e.clientX - rect.left) / rect.width;
    const relY = (e.clientY - rect.top) / rect.height;

    // Guard: ignore clicks in the top-left area where zoom buttons sit to avoid accidental plotting under buttons
    if (relX < 0.12 && relY < 0.22) {
      return;
    }

    if (boundaryCoords.length >= 5) {
      alert("Maximum 5 boundary corner points allowed");
      return;
    }
    const clickedLon = minLon + relX * (2 * dLon);
    const clickedLat = maxLat - relY * (2 * dLat);
    const newCoords = [...boundaryCoords, [Number(clickedLat.toFixed(5)), Number(clickedLon.toFixed(5))] as [number, number]];
    setBoundaryCoords(newCoords);
    if (newCoords.length >= 3) {
      const acres = calculateGeodesicAcres(newCoords, latNum, lonNum);
      setFormData(prev => ({ ...prev, area_value: String(acres) }));
    }
  };

  const autoPlot1Acre = () => {
    const dLatBox = 31.8 / 110574;
    const dLonBox = 31.8 / (111320 * Math.cos(latNum * Math.PI / 180));
    const box: Array<[number, number]> = [
      [Number((latNum + dLatBox).toFixed(5)), Number((lonNum - dLonBox).toFixed(5))],
      [Number((latNum + dLatBox).toFixed(5)), Number((lonNum + dLonBox).toFixed(5))],
      [Number((latNum - dLatBox).toFixed(5)), Number((lonNum + dLonBox).toFixed(5))],
      [Number((latNum - dLatBox).toFixed(5)), Number((lonNum - dLonBox).toFixed(5))]
    ];
    setBoundaryCoords(box);
    setFormData(prev => ({ ...prev, area_value: "1.00" }));
  };

  const autoPlot25Acres = () => {
    const dLatBox = 50.3 / 110574;
    const dLonBox = 50.3 / (111320 * Math.cos(latNum * Math.PI / 180));
    const box: Array<[number, number]> = [
      [Number((latNum + dLatBox).toFixed(5)), Number((lonNum - dLonBox).toFixed(5))],
      [Number((latNum + dLatBox).toFixed(5)), Number((lonNum + dLonBox).toFixed(5))],
      [Number((latNum - dLatBox).toFixed(5)), Number((lonNum + dLonBox).toFixed(5))],
      [Number((latNum - dLatBox).toFixed(5)), Number((lonNum - dLonBox).toFixed(5))]
    ];
    setBoundaryCoords(box);
    setFormData(prev => ({ ...prev, area_value: "2.50" }));
  };

  const clearPoints = () => {
    setBoundaryCoords([]);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setProgressStep("Registering field boundary & syncing coordinates...");

    try {
      const cropToSave = formData.current_crop === "custom" ? formData.custom_crop : formData.current_crop;
      const f = await api<Json>("/api/v1/farms", {
        method: "POST",
        body: JSON.stringify({
          name: formData.name || "My Farm",
          pincode: formData.pincode || null,
          country_code: "IN",
          state_code: formData.state_code || "MH",
          state_name: formData.state_name || "Maharashtra",
          district: formData.district || "Default District",
          village: formData.village || null,
          area_value: Number(formData.area_value) || 1,
          area_unit: formData.area_unit,
          location: {
            latitude: latNum,
            longitude: lonNum,
            source: (geocoding || geoAddress) ? "device" : "farmer",
            confirmed: true
          },
          boundary_coordinates: boundaryCoords,
          water_access: formData.water_access,
          soil_type: formData.soil_type,
          current_crop: cropToSave || null,
          previous_crop: formData.previous_crop && formData.previous_crop !== "none" ? formData.previous_crop : null,
          crop_status: cropToSave ? "planted" : "planning"
        })
      });
      setSavedFarmId(f.id);
      localStorage.setItem("kisanai_cached_farm", JSON.stringify(f));
      try {
        const myIds = JSON.parse(localStorage.getItem("kisanai_my_farm_ids") || "[]");
        if (!myIds.includes(f.id)) {
          myIds.push(f.id);
          localStorage.setItem("kisanai_my_farm_ids", JSON.stringify(myIds));
        }
      } catch {}
      done(f.id);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const soilTypes = [
    { id: "black", label: "⬛ Deep Black (Regur / काळी माती)" },
    { id: "red", label: "🟫 Red Sandy Loam (तांबडी माती)" },
    { id: "alluvial", label: "🟨 Alluvial Soil (गाळाची माती)" },
    { id: "loam", label: "🪨 Clay Loam (पोयटा माती)" },
    { id: "sandy", label: "🏜️ Light Sandy (हलकी मुरमाड)" }
  ];

  const waterOptions = [
    { id: "rainfed", label: "🌧️ Rainfed (जिरायती / Monsoon)" },
    { id: "supplemental_irrigation", label: "💧 Well / Supplemental (बागायती / विहीर)" },
    { id: "irrigated", label: "🚿 Canal / Drip Irrigated (कॅनल / ठिबक)" }
  ];

  const svgPoints = boundaryCoords.map(([ptLat, ptLon]) => {
    const x = ((ptLon - minLon) / (2 * dLon)) * 1000;
    const y = ((maxLat - ptLat) / (2 * dLat)) * 600;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return (
    <section className="panel narrow">
      <div className="section-title">
        <MapPin />
        <div>
          <small>PIPELINE STAGE 1 OF 5</small>
          <h2>{t.farm}</h2>
        </div>
      </div>

      <div className="explainer-banner">
        <div className="explainer-icon"><Info size={20} /></div>
        <div className="explainer-content">
          <h4>{t.farm_explainer_title || "Farm Location & Plot Corner Plotter"}</h4>
          <p>{t.farm_explainer_desc || "Enter your 6-digit Indian PIN code to locate your district, or tap GPS. Click on the map to plot 3 to 5 field corners to compute exact boundary acreage."}</p>
        </div>
      </div>

      {!savedFarmId ? (
        <form onSubmit={submit}>
          {/* PIN Code Quick Search Box */}
          <div className="pincode-search-box">
            <span style={{ fontWeight: 700, fontSize: "13px", color: "var(--green-950)", display: "flex", alignItems: "center", gap: "6px" }}>
              <MapPin size={16} color="var(--green-700)" />
              {t.pincode_label || "PIN Code"}:
            </span>
            <input
              type="text"
              maxLength={6}
              className="pincode-input"
              placeholder={t.pincode_placeholder || "Enter 6-digit Indian PIN (e.g. 431203)"}
              value={formData.pincode}
              onChange={e => setFormData({ ...formData, pincode: e.target.value })}
            />
            <button
              type="button"
              className="pincode-btn"
              disabled={pincodeLoading}
              onClick={handlePincodeLookup}
            >
              <RefreshCw size={13} className={pincodeLoading ? "spin" : ""} />
              {pincodeLoading ? (t.pincode_searching || "Searching...") : (t.pincode_btn || "Find Location")}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={geocoding}
              onClick={locate}
              style={{ padding: "8px 12px", fontSize: "13px" }}
              title="Auto-detect via GPS"
            >
              <MapPin size={14} className={geocoding ? "spin" : ""} />
              GPS
            </button>
          </div>

          {pincodeMsg && (
            <div className="geo-sync-banner" style={{ marginBottom: "14px" }}>
              <CheckCircle2 size={16} color="#16a34a" />
              <span>{pincodeMsg}</span>
            </div>
          )}

          {postOffices.length > 1 && (
            <div style={{
              marginBottom: "16px",
              padding: "12px 14px",
              background: "#f0fdf4",
              border: "1px solid #86efac",
              borderRadius: "10px"
            }}>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 700, color: "#166534", marginBottom: "6px" }}>
                📍 Select Village / Sub-Post Office ({postOffices.length} found in PIN {formData.pincode}):
              </label>
              <select
                value={formData.village}
                onChange={e => handleVillageSelect(e.target.value)}
                style={{
                  width: "100%",
                  padding: "9px 12px",
                  borderRadius: "8px",
                  border: "1px solid #4ade80",
                  background: "white",
                  fontSize: "13px",
                  fontWeight: 600,
                  color: "#1e293b",
                  cursor: "pointer"
                }}
              >
                <option value="">-- Choose your village to position map --</option>
                {postOffices.map((po, idx) => (
                  <option key={idx} value={po.name}>
                    {po.name} {po.office_type ? `(${po.office_type})` : ""} {po.latitude && po.longitude ? `• ${po.latitude.toFixed(3)}°N, ${po.longitude.toFixed(3)}°E` : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          {geoAddress && !pincodeMsg && (
            <div className="geo-sync-banner" style={{ marginBottom: "14px" }}>
              <CheckCircle2 size={16} color="#16a34a" />
              <span>{geoAddress}</span>
            </div>
          )}

          {/* Interactive Plot Canvas */}
          <div style={{ marginBottom: "18px" }}>
            <div className="plot-toolbar">
              <div className="plot-toolbar-title">
                <MapPin size={15} color="var(--lime-400)" />
                <span>{t.plot_farm_boundary || "Interactive Farm Boundary Plotter"}</span>
              </div>
              <div className="plot-toolbar-actions">
                <button type="button" className="plot-btn" onClick={autoPlot1Acre}>
                  📐 {t.plot_auto_1ac || "1-Acre Box"}
                </button>
                <button type="button" className="plot-btn" onClick={autoPlot25Acres}>
                  📐 {t.plot_auto_2ac || "2.5-Acre Box"}
                </button>
                {boundaryCoords.length > 0 && (
                  <button type="button" className="plot-btn" onClick={clearPoints}>
                    ↺ {t.plot_clear || "Clear"}
                  </button>
                )}
              </div>
            </div>

            <div className="plot-interactive-stage" style={{ position: "relative" }}>
              {/* Isolated Canvas Zoom Controls */}
              <div
                className="map-zoom-controls"
                style={{
                  position: "absolute",
                  top: "12px",
                  left: "12px",
                  zIndex: 35,
                  display: "flex",
                  flexDirection: "column",
                  borderRadius: "6px",
                  overflow: "hidden",
                  boxShadow: "0 2px 8px rgba(0,0,0,0.35)",
                  border: "1px solid #64748b",
                  background: "#ffffff"
                }}
              >
                <button
                  type="button"
                  onClick={handleZoomIn}
                  onMouseDown={e => e.stopPropagation()}
                  title="Zoom In (+)"
                  style={{
                    width: "32px",
                    height: "32px",
                    background: "#ffffff",
                    color: "#0f172a",
                    border: "none",
                    borderBottom: "1px solid #cbd5e1",
                    fontSize: "20px",
                    fontWeight: "bold",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    cursor: "pointer",
                    padding: 0,
                    lineHeight: 1
                  }}
                >
                  +
                </button>
                <button
                  type="button"
                  onClick={handleZoomOut}
                  onMouseDown={e => e.stopPropagation()}
                  title="Zoom Out (−)"
                  style={{
                    width: "32px",
                    height: "32px",
                    background: "#ffffff",
                    color: "#0f172a",
                    border: "none",
                    fontSize: "20px",
                    fontWeight: "bold",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    cursor: "pointer",
                    padding: 0,
                    lineHeight: 1
                  }}
                >
                  −
                </button>
              </div>

              <iframe
                className="plot-map-frame"
                title="Field Location Basemap"
                src={`https://www.openstreetmap.org/export/embed.html?bbox=${minLon},${minLat},${maxLon},${maxLat}&layer=mapnik`}
              />
              <svg
                ref={svgRef}
                className="plot-svg-overlay"
                viewBox="0 0 1000 600"
                onClick={handleCanvasClick}
              >
                {boundaryCoords.length >= 3 && (
                  <polygon
                    points={svgPoints}
                    fill="rgba(34, 197, 94, 0.35)"
                    stroke="#16a34a"
                    strokeWidth="3"
                    strokeDasharray="6 3"
                  />
                )}
                {boundaryCoords.length === 2 && (
                  <polyline
                    points={svgPoints}
                    fill="none"
                    stroke="#16a34a"
                    strokeWidth="3"
                    strokeDasharray="6 3"
                  />
                )}
                {boundaryCoords.map(([ptLat, ptLon], idx) => {
                  const x = ((ptLon - minLon) / (2 * dLon)) * 1000;
                  const y = ((maxLat - ptLat) / (2 * dLat)) * 600;
                  return (
                    <g key={idx}>
                      <circle cx={x} cy={y} r="14" fill="#eab308" stroke="#ffffff" strokeWidth="3" />
                      <text x={x} y={y + 4} textAnchor="middle" fill="#000000" fontSize="12" fontWeight="bold">
                        {idx + 1}
                      </text>
                    </g>
                  );
                })}
                {/* Center marker */}
                <circle cx={500} cy={300} r="6" fill="#ef4444" stroke="#ffffff" strokeWidth="2" />
              </svg>
            </div>

            <div className="plot-info-bar">
              <span>
                📍 {boundaryCoords.length > 0 ? `Corners: ${boundaryCoords.length} / 5 points plotted` : (t.plot_helper_tip || "Click map to plot 3-5 corners")}
              </span>
              <span className="plot-acreage-badge">
                {formData.area_value} {formData.area_unit}s ({boundaryCoords.length >= 3 ? "✓ Plotted" : "Estimated"})
              </span>
            </div>
          </div>

          <div className="form-grid">
            <label className="field">
              <span>Farm Name</span>
              <input
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </label>

            <label className="field">
              <span>State</span>
              <select
                value={formData.state_name}
                onChange={e => {
                  const stateMap: Record<string, string> = {
                    Maharashtra: "MH",
                    Telangana: "TS",
                    Karnataka: "KA",
                    "Madhya Pradesh": "MP",
                    Gujarat: "GJ",
                    Punjab: "PB",
                    "Andhra Pradesh": "AP",
                    Rajasthan: "RJ",
                    "Uttar Pradesh": "UP"
                  };
                  const name = e.target.value;
                  setFormData({
                    ...formData,
                    state_name: name,
                    state_code: stateMap[name] || "IN"
                  });
                }}
              >
                <option value="Maharashtra">Maharashtra (महाराष्ट्र)</option>
                <option value="Telangana">Telangana (తెలంగాణ)</option>
                <option value="Karnataka">Karnataka (ಕರ್ನಾಟಕ)</option>
                <option value="Madhya Pradesh">Madhya Pradesh (मध्य प्रदेश)</option>
                <option value="Gujarat">Gujarat (ગુજરાત)</option>
                <option value="Punjab">Punjab (ਪੰਜਾਬ)</option>
                <option value="Andhra Pradesh">Andhra Pradesh (ఆంధ్రప్రదేశ్)</option>
                <option value="Rajasthan">Rajasthan (राजस्थान)</option>
                <option value="Uttar Pradesh">Uttar Pradesh (उत्तर प्रदेश)</option>
              </select>
            </label>

            <label className="field">
              <span>District (जिल्हा)</span>
              <select
                value={formData.district}
                onChange={e => {
                  const distName = e.target.value;
                  const match = MAHARASHTRA_DISTRICTS.find(d => d.name === distName);
                  setFormData(prev => ({
                    ...prev,
                    district: distName,
                    state_name: "Maharashtra",
                    state_code: "MH",
                    latitude: match && boundaryCoords.length === 0 ? String(match.lat.toFixed(4)) : prev.latitude,
                    longitude: match && boundaryCoords.length === 0 ? String(match.lon.toFixed(4)) : prev.longitude,
                  }));
                }}
                required
              >
                <option value="">-- Select Maharashtra District --</option>
                {formData.district && !MAHARASHTRA_DISTRICTS.some(d => d.name === formData.district) && (
                  <option value={formData.district}>{formData.district}</option>
                )}
                {MAHARASHTRA_DISTRICTS.map(d => (
                  <option key={d.name} value={d.name}>
                    {d.name} ({d.nameMr})
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Village / Taluka (Optional)</span>
              <input
                value={formData.village}
                onChange={e => setFormData({ ...formData, village: e.target.value })}
                placeholder={t.village_placeholder || "Enter village or taluka"}
              />
            </label>
          </div>

          {/* Water Access Selection */}
          <div className="form-section">
            <div className="form-section-title">Water Access & Irrigation</div>
            <div className="chip-group">
              {waterOptions.map(w => (
                <button
                  key={w.id}
                  type="button"
                  className={`chip ${formData.water_access === w.id ? "active" : ""}`}
                  onClick={() => setFormData({ ...formData, water_access: w.id })}
                >
                  {w.label}
                </button>
              ))}
            </div>
          </div>

          {/* Soil Type Selection */}
          <div className="form-section">
            <div className="form-section-title">Soil Classification</div>
            <div className="chip-group">
              {soilTypes.map(s => (
                <button
                  key={s.id}
                  type="button"
                  className={`chip ${formData.soil_type === s.id ? "active" : ""}`}
                  onClick={() => setFormData({ ...formData, soil_type: s.id })}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Crop Dropdowns */}
          <div className="form-grid" style={{ marginTop: "10px" }}>
            <label className="field">
              <span>{t.current_crop_label || "Current Standing Crop"}</span>
              <select
                value={formData.current_crop}
                onChange={e => setFormData({ ...formData, current_crop: e.target.value })}
              >
                <option value="">{t.select_crop_empty || "-- Select (None / Planning New Crop) --"}</option>
                {MAHARASHTRA_CROPS.map(group => (
                  <optgroup label={group.category} key={group.category}>
                    {group.crops.map(c => (
                      <option value={c.id} key={c.id}>{c.label}</option>
                    ))}
                  </optgroup>
                ))}
                <option value="custom">{t.custom_crop_opt || "✍️ Other / Custom Crop..."}</option>
              </select>
            </label>

            <label className="field">
              <span>{t.previous_crop_label || "Previous Season Crop (For Crop Rotation Plan)"}</span>
              <select
                value={formData.previous_crop}
                onChange={e => setFormData({ ...formData, previous_crop: e.target.value })}
              >
                <option value="">{t.select_prev_crop_empty || "-- Select (None / Fallow) --"}</option>
                {MAHARASHTRA_CROPS.map(group => (
                  <optgroup label={group.category} key={group.category}>
                    {group.crops.map(c => (
                      <option value={c.id} key={c.id}>{c.label}</option>
                    ))}
                  </optgroup>
                ))}
                <option value="none">{t.fallow_opt || "None / Fallow"}</option>
              </select>
            </label>
          </div>

          {formData.current_crop === "custom" && (
            <label className="field" style={{ marginTop: "12px" }}>
              <span>Enter Custom Crop Name</span>
              <input
                value={formData.custom_crop}
                onChange={e => setFormData({ ...formData, custom_crop: e.target.value })}
                placeholder="e.g. Dragonfruit, Mulberry, Custard Apple"
                required
              />
            </label>
          )}

          {busy && (
            <div className="inplace-progress">
              <div className="inplace-progress-header">
                <b><RefreshCw className="spin" size={16} /> Creating Farm Profile...</b>
              </div>
              <div className="inplace-progress-track">
                <div className="inplace-progress-fill" style={{ width: "80%" }} />
              </div>
              <div className="inplace-step active">{progressStep}</div>
            </div>
          )}

          <button
            type="submit"
            className="primary"
            disabled={busy}
            style={{ width: "100%", padding: "16px", marginTop: "20px", fontSize: "16px" }}
          >
            <CheckCircle2 size={18} />
            {t.save || "Save & Proceed to Weather"}
            <ArrowRight size={18} />
          </button>
        </form>
      ) : (
        <SoilCardSection t={t} farmId={savedFarmId} />
      )}
    </section>
  );
}
