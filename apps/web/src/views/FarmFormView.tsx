import { useState, FormEvent } from "react";
import { MapPin, Info, RefreshCw, CheckCircle2, ArrowRight } from "lucide-react";
import { api } from "../api";
import { Json } from "../types";
import { MAHARASHTRA_CROPS } from "../constants/crops";
import { MAHARASHTRA_DISTRICTS } from "../constants/districts";
import { calculateGeodesicAcres } from "../utils/geo";
import { FieldMap } from "../components/FieldMap";

export interface FarmFormViewProps {
  t: Record<string, string>;
  /** The farm to edit; without it the form adds a new farm. */
  farm?: Json;
  done: (id: string) => void;
}

const KNOWN_CROPS = new Set(MAHARASHTRA_CROPS.flatMap(category => category.crops.map(crop => crop.id)));

export function FarmFormView({ t, farm, done }: FarmFormViewProps) {
  const editing = Boolean(farm);
  const readOnly = editing && !farm?.is_mine;
  const savedCrop: string = farm?.current_crop || "";
  const [formData, setFormData] = useState({
    name: farm?.name ?? "My Farm",
    pincode: farm?.pincode ?? "",
    state_name: farm?.state_name ?? "Maharashtra",
    state_code: farm?.state_code ?? "MH",
    district: farm?.district ?? "",
    village: farm?.village ?? "",
    taluka: farm?.taluka ?? "",
    latitude: farm ? String(farm.location.latitude) : "19.7500",
    longitude: farm ? String(farm.location.longitude) : "75.7100",
    area_value: farm ? String(farm.area_value) : "1",
    area_unit: farm?.area_unit ?? "acre",
    water_access: farm?.water_access ?? "rainfed",
    soil_type: farm?.soil_type ?? "black",
    current_crop: !savedCrop ? "" : KNOWN_CROPS.has(savedCrop) ? savedCrop : "custom",
    custom_crop: savedCrop && !KNOWN_CROPS.has(savedCrop) ? savedCrop : "",
    previous_crop: farm?.previous_crop ?? "",
    crop_status: farm?.crop_status ?? "planning"
  });

  const [boundaryCoords, setBoundaryCoords] = useState<Array<[number, number]>>(farm?.boundary_coordinates ?? []);
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

  const latNum = parseFloat(formData.latitude) || 19.75;
  const lonNum = parseFloat(formData.longitude) || 75.71;

  // Tapping or dragging corners on the map updates the field and its area.
  const updateBoundary = (coords: Array<[number, number]>) => {
    setBoundaryCoords(coords);
    if (coords.length >= 3) {
      setFormData(prev => ({ ...prev, area_value: String(calculateGeodesicAcres(coords, latNum, lonNum)) }));
    }
  };

  const handlePincodeLookup = async () => {
    const clean = formData.pincode.trim();
    if (clean.length !== 6 || !/^\d+$/.test(clean)) {
      alert("Please type a 6-digit PIN code, for example 445001.");
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
        setPincodeMsg(`✓ ${offices.length} post offices found in ${geo.district}. Pick your village below.`);
      } else {
        setPincodeMsg(`✓ Found: ${geo.district}, ${geo.state_name}`);
      }
      setBoundaryCoords([]);
    } catch (e: any) {
      setPincodeMsg("❌ " + (e.message || "Couldn't find that PIN code. Please pick your district from the list."));
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
    setGeoAddress("Finding your location…");

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
            taluka: rev.taluka || prev.taluka,
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
        setGeoAddress("GPS isn't available, trying your network location…");
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
          setGeoAddress(`📍 Approximate location from your network: ${labelParts.join(", ")}. Please check it on the map.`);
          return;
        }
      } catch {
        // Continue to gentle guidance
      }
      setGeoAddress("⚠️ Couldn't get your location. Please type your PIN code or pick your district below.");
    };

    if (!navigator.geolocation) {
      tryIpFallback().finally(() => setGeocoding(false));
      return;
    }

    // 1. Try High Accuracy hardware GPS (10s timeout matching original morning setting)
    navigator.geolocation.getCurrentPosition(
      pos => {
        applyCoordsAndReverse(pos.coords.latitude, pos.coords.longitude, "Found you by GPS");
      },
      err => {
        // If permission was denied by user
        if (err.code === 1) {
          setGeoAddress("Location permission was not given, trying your network location…");
          tryIpFallback().finally(() => setGeocoding(false));
          return;
        }
        // 2. High accuracy unavailable or timed out -> Fallback to low accuracy (Wi-Fi/Cellular/Cache)
        navigator.geolocation.getCurrentPosition(
          pos => {
            applyCoordsAndReverse(pos.coords.latitude, pos.coords.longitude, "Location found");
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
    if (!formData.district) {
      alert("Please choose your district, or find your farm by PIN code or GPS.");
      return;
    }
    setBusy(true);
    setProgressStep("Saving your farm…");

    try {
      const cropToSave = formData.current_crop === "custom" ? formData.custom_crop : formData.current_crop;
      const f = await api<Json>(editing ? `/api/v1/farms/${farm!.id}?version=${farm!.version}` : "/api/v1/farms", {
        method: editing ? "PUT" : "POST",
        body: JSON.stringify({
          name: formData.name || "My Farm",
          pincode: formData.pincode || null,
          country_code: "IN",
          state_code: formData.state_code || "MH",
          state_name: formData.state_name || "Maharashtra",
          district: formData.district,
          village: formData.village || null,
          taluka: formData.taluka || null,
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
      localStorage.setItem("kisanai_cached_farm", JSON.stringify(f));
      done(f.id);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const soilTypes = [
    { id: "black", label: t.soil_black },
    { id: "red", label: t.soil_red },
    { id: "alluvial", label: t.soil_alluvial },
    { id: "loam", label: t.soil_loam },
    { id: "sandy", label: t.soil_sandy }
  ];

  const waterOptions = [
    { id: "rainfed", label: t.water_rainfed },
    { id: "supplemental_irrigation", label: t.water_supplemental },
    { id: "irrigated", label: t.water_irrigated }
  ];

  return (
    <section className="panel narrow">
      <div className="section-title">
        <MapPin />
        <div>
          <small>{editing ? farm!.name : t.home_add_farm}</small>
          <h2>{editing ? t.edit_farm : t.farm}</h2>
        </div>
      </div>

      <div className="explainer-banner">
        <div className="explainer-icon"><Info size={20} /></div>
        <div className="explainer-content">
          <h4>{t.farm_explainer_title}</h4>
          <p>{t.farm_explainer_desc}</p>
        </div>
      </div>

      {(
        <form onSubmit={submit}>
          {readOnly && <p className="notice">{t.farm_read_only}</p>}
          {/* PIN Code Quick Search Box */}
          <div className="pincode-search-box">
            <span style={{ fontWeight: 700, fontSize: "13px", color: "var(--green-950)", display: "flex", alignItems: "center", gap: "6px" }}>
              <MapPin size={16} color="var(--green-700)" />
              {t.pincode_label}:
            </span>
            <input
              type="text"
              maxLength={6}
              className="pincode-input"
              placeholder={t.pincode_placeholder}
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
              {pincodeLoading ? (t.pincode_searching) : (t.pincode_btn)}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={geocoding}
              onClick={locate}
              style={{ padding: "8px 12px", fontSize: "13px" }}
              title="Use GPS"
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
                <span>{t.plot_farm_boundary}</span>
              </div>
              {!readOnly && <div className="plot-toolbar-actions">
                <button type="button" className="plot-btn" onClick={autoPlot1Acre}>
                  📐 {t.plot_auto_1ac}
                </button>
                <button type="button" className="plot-btn" onClick={autoPlot25Acres}>
                  📐 {t.plot_auto_2ac}
                </button>
                {boundaryCoords.length > 0 && (
                  <button type="button" className="plot-btn" onClick={clearPoints}>
                    ↺ {t.plot_clear}
                  </button>
                )}
              </div>}
            </div>

            <FieldMap
              center={[latNum, lonNum]}
              boundary={boundaryCoords}
              onBoundaryChange={readOnly ? undefined : updateBoundary}
              recenterKey={`${formData.latitude},${formData.longitude}`}
            />

            <div className="plot-info-bar">
              <span>
                📍 {readOnly ? farm!.name : boundaryCoords.length > 0 ? t.plot_corners.replace("{n}", String(boundaryCoords.length)) : t.plot_helper_tip}
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
              <span>{t.village_label || "Village"}</span>
              <input
                value={formData.village}
                onChange={e => setFormData({ ...formData, village: e.target.value })}
                placeholder={t.village_placeholder}
              />
            </label>

            <label className="field">
              <span>Taluka</span>
              <input
                value={formData.taluka}
                onChange={e => setFormData({ ...formData, taluka: e.target.value })}
                placeholder="e.g. Baramati"
              />
            </label>
          </div>

          {/* Water Access Selection */}
          <div className="form-section">
            <div className="form-section-title">{t.water_section}</div>
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
            <div className="form-section-title">{t.soil_section}</div>
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
              <span>{t.current_crop_label}</span>
              <select
                value={formData.current_crop}
                onChange={e => setFormData({ ...formData, current_crop: e.target.value })}
              >
                <option value="">{t.select_crop_empty}</option>
                {MAHARASHTRA_CROPS.map(group => (
                  <optgroup label={group.category} key={group.category}>
                    {group.crops.map(c => (
                      <option value={c.id} key={c.id}>{c.label}</option>
                    ))}
                  </optgroup>
                ))}
                <option value="custom">{t.custom_crop_opt}</option>
              </select>
            </label>

            <label className="field">
              <span>{t.previous_crop_label}</span>
              <select
                value={formData.previous_crop}
                onChange={e => setFormData({ ...formData, previous_crop: e.target.value })}
              >
                <option value="">{t.select_prev_crop_empty}</option>
                {MAHARASHTRA_CROPS.map(group => (
                  <optgroup label={group.category} key={group.category}>
                    {group.crops.map(c => (
                      <option value={c.id} key={c.id}>{c.label}</option>
                    ))}
                  </optgroup>
                ))}
                <option value="none">{t.fallow_opt}</option>
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
            disabled={busy || readOnly}
            style={{ width: "100%", padding: "16px", marginTop: "20px", fontSize: "16px" }}
          >
            <CheckCircle2 size={18} />
            {editing ? t.save_changes : t.save}
            <ArrowRight size={18} />
          </button>
        </form>
      )}
    </section>
  );
}
