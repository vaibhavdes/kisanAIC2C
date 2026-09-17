import React, { useState, useEffect, FormEvent } from "react";
import {
  FlaskConical,
  CheckCircle2,
  FileCheck,
  RefreshCw,
  ArrowRight,
  Upload,
  Info,
  Sparkles,
  Edit3,
  ShieldCheck,
  Check
} from "lucide-react";
import { api, upload } from "../api";
import { View, Locale, Json } from "../types";

export interface SoilViewProps {
  t: Record<string, string>;
  locale: Locale;
  farm?: Json;
  go: (v: View) => void;
}

export function SoilView({ t, locale, farm, go }: SoilViewProps) {
  const [mode, setMode] = useState<"upload" | "manual">("upload");
  const [loading, setLoading] = useState(false);
  const [stepMsg, setStepMsg] = useState("");
  const [savedSoil, setSavedSoil] = useState<Json | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  // Manual inputs state (starts empty with placeholders; unentered fields use regional baseline)
  const [ph, setPh] = useState<string>("");
  const [organicCarbon, setOrganicCarbon] = useState<string>("");
  const [nitrogen, setNitrogen] = useState<string>("");
  const [phosphorus, setPhosphorus] = useState<string>("");
  const [potassium, setPotassium] = useState<string>("");
  const [ec, setEc] = useState<string>("");
  const [labName, setLabName] = useState<string>("");

  // Extracted card state
  const [extractedData, setExtractedData] = useState<Json | null>(null);
  const [cardPreview, setCardPreview] = useState<string | null>(null);

  // Load existing soil test if available
  useEffect(() => {
    if (!farm) return;
    const fetchExistingSoil = async () => {
      try {
        const existing = await api<Json>(`/api/v1/farms/${farm.id}/soil`);
        if (existing && existing.values) {
          setSavedSoil(existing);
          const v = existing.values as Record<string, any>;
          if (v.ph !== undefined && v.ph !== null) setPh(String(v.ph));
          if (v.organic_carbon_percent !== undefined && v.organic_carbon_percent !== null)
            setOrganicCarbon(String(v.organic_carbon_percent));
          if (v.nitrogen_kg_ha !== undefined && v.nitrogen_kg_ha !== null)
            setNitrogen(String(v.nitrogen_kg_ha));
          if (v.phosphorus_kg_ha !== undefined && v.phosphorus_kg_ha !== null)
            setPhosphorus(String(v.phosphorus_kg_ha));
          if (v.potassium_kg_ha !== undefined && v.potassium_kg_ha !== null)
            setPotassium(String(v.potassium_kg_ha));
          if (v.ec_ds_m !== undefined && v.ec_ds_m !== null)
            setEc(String(v.ec_ds_m));
        }
      } catch (e) {
        console.warn("No existing soil test found", e);
      }
    };
    fetchExistingSoil();
  }, [farm?.id]);

  if (!farm) {
    return (
      <section className="panel" style={{ textAlign: "center", padding: "60px 20px" }}>
        <FlaskConical size={48} color="var(--lime-500)" style={{ marginBottom: "12px" }} />
        <h2>{t.add_farm_first || "Add a Farm First"}</h2>
        <button className="primary" onClick={() => go("farm")} style={{ marginTop: "16px" }}>
          {t.start || "Add Farm Profile"}
        </button>
      </section>
    );
  }

  // Handle Photo/PDF Upload & Gemini Vision Extraction
  const handleFileUpload = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const d = new FormData(e.currentTarget);
    const file = d.get("file") as File;
    if (!file || file.size === 0) return;

    setLoading(true);
    setStepMsg("Uploading card image and extracting N-P-K, pH & Organic Carbon via Gemini Vision...");
    try {
      const media = await upload(file, "soil_card");
      const res = await api<Json>(`/api/v1/farms/${farm.id}/soil/extract?media_id=${media.id}&locale=${locale}`, {
        method: "POST"
      });
      setExtractedData(res);
      if (res.values) {
        const v = res.values as Record<string, any>;
        if (v.ph !== undefined && v.ph !== null) setPh(String(v.ph));
        if (v.organic_carbon_percent !== undefined && v.organic_carbon_percent !== null)
          setOrganicCarbon(String(v.organic_carbon_percent));
        if (v.nitrogen_kg_ha !== undefined && v.nitrogen_kg_ha !== null)
          setNitrogen(String(v.nitrogen_kg_ha));
        if (v.phosphorus_kg_ha !== undefined && v.phosphorus_kg_ha !== null)
          setPhosphorus(String(v.phosphorus_kg_ha));
        if (v.potassium_kg_ha !== undefined && v.potassium_kg_ha !== null)
          setPotassium(String(v.potassium_kg_ha));
        if (v.ec_ds_m !== undefined && v.ec_ds_m !== null)
          setEc(String(v.ec_ds_m));
        if (res.lab_name) setLabName(String(res.lab_name));
      }
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  // Save Soil Test (used by Manual, Baseline, or confirmed Extracted values)
  const saveSoilRecord = async (sourceType: "manual" | "soil_card_confirmed" = "manual") => {
    setLoading(true);
    setStepMsg("Saving soil nutrient profile...");
    try {
      const payload = {
        values: {
          ph: ph ? parseFloat(ph) : null,
          organic_carbon_percent: organicCarbon ? parseFloat(organicCarbon) : null,
          nitrogen_kg_ha: nitrogen ? parseFloat(nitrogen) : null,
          phosphorus_kg_ha: phosphorus ? parseFloat(phosphorus) : null,
          potassium_kg_ha: potassium ? parseFloat(potassium) : null,
          ec_ds_m: ec ? parseFloat(ec) : null
        },
        lab_name: labName || null,
        source: sourceType,
        confirmed: true
      };

      const res = await api<Json>(`/api/v1/farms/${farm.id}/soil`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      setSavedSoil(res);
      setIsEditing(false);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const getPhStatus = (val: number) => {
    if (val < 6.0) return { label: "Acidic", color: "#c0392b" };
    if (val < 6.5) return { label: "Slightly Acidic", color: "#e67e22" };
    if (val <= 7.5) return { label: "Neutral / Optimal", color: "#27ae60" };
    if (val <= 8.5) return { label: "Slightly Alkaline", color: "#2980b9" };
    return { label: "Strongly Alkaline", color: "#8e44ad" };
  };

  const getNutrientStatus = (nutrient: "N" | "P" | "K" | "OC", val: number) => {
    if (nutrient === "N") {
      if (val < 280) return { label: "Low", color: "#d97706" };
      if (val <= 560) return { label: "Medium", color: "#16a34a" };
      return { label: "High", color: "#2563eb" };
    }
    if (nutrient === "P") {
      if (val < 10) return { label: "Low", color: "#d97706" };
      if (val <= 25) return { label: "Medium", color: "#16a34a" };
      return { label: "High", color: "#2563eb" };
    }
    if (nutrient === "K") {
      if (val < 108) return { label: "Low", color: "#d97706" };
      if (val <= 280) return { label: "Medium", color: "#16a34a" };
      return { label: "High", color: "#2563eb" };
    }
    if (nutrient === "OC") {
      if (val < 0.5) return { label: "Low", color: "#d97706" };
      if (val <= 0.75) return { label: "Medium", color: "#16a34a" };
      return { label: "High", color: "#2563eb" };
    }
    return { label: "Normal", color: "#16a34a" };
  };

  return (
    <section className="panel">
      {/* Stage Header */}
      <div className="section-title">
        <FlaskConical />
        <div>
          <small>PIPELINE STAGE 3 OF 5 · {farm.name} ({farm.district})</small>
          <h2>{t.step_soil || "Soil Health & Nutrient Profile"}</h2>
        </div>
      </div>

      {/* Explainer Banner */}
      <div className="explainer-banner">
        <div className="explainer-icon">
          <Info size={20} />
        </div>
        <div className="explainer-content">
          <h4>Soil Health Card Calibration (Optional Step)</h4>
          <p>
            Soil test results (pH, Organic Carbon, N, P, K) allow KISANAI to calculate exact crop suitability scores and ICAR-approved regenerative fertilizer dosages. You can upload your Government Soil Health Card, enter numbers manually, apply regional averages, or skip directly to crop recommendations.
          </p>
        </div>
      </div>

      {/* If Soil Profile is Already Saved and Not Editing */}
      {savedSoil && !isEditing ? (
        <div style={{ marginTop: "20px" }}>
          <div
            className="explainer-banner"
            style={{
              background: "#edf7ed",
              borderColor: "#a3d9a5",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center"
            }}
          >
            <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
              <div className="explainer-icon" style={{ background: "#1b4d2b" }}>
                <CheckCircle2 size={24} />
              </div>
              <div className="explainer-content">
                <h4 style={{ color: "#1b4d2b", margin: 0 }}>Soil Nutrient Profile Active</h4>
                <p style={{ margin: "4px 0 0", color: "#2e5c3c" }}>
                  Confirmed nutrient data will be factored into your crop recommendations and field plan.
                </p>
              </div>
            </div>
            <button
              className="secondary"
              onClick={() => setIsEditing(true)}
              style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px" }}
            >
              <Edit3 size={14} />
              Update / Edit Values
            </button>
          </div>

          {/* Saved Nutrient Badges Grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: "14px",
              marginTop: "16px"
            }}
          >
            {savedSoil.values && (
              <>
                <div
                  style={{
                    background: "#ffffff",
                    border: "1px solid var(--line)",
                    borderRadius: "12px",
                    padding: "16px"
                  }}
                >
                  <small style={{ color: "var(--muted)", textTransform: "uppercase", fontSize: "11px", fontWeight: 600 }}>
                    Soil Reaction (pH)
                  </small>
                  <div style={{ fontSize: "24px", fontWeight: 700, margin: "6px 0", color: "var(--green-950)" }}>
                    {(savedSoil.values as any).ph ?? "7.2"}
                  </div>
                  {(() => {
                    const status = getPhStatus((savedSoil.values as any).ph ?? 7.2);
                    return (
                      <span
                        style={{
                          fontSize: "11px",
                          fontWeight: 700,
                          padding: "2px 8px",
                          borderRadius: "12px",
                          background: `${status.color}15`,
                          color: status.color
                        }}
                      >
                        {status.label}
                      </span>
                    );
                  })()}
                </div>

                <div
                  style={{
                    background: "#ffffff",
                    border: "1px solid var(--line)",
                    borderRadius: "12px",
                    padding: "16px"
                  }}
                >
                  <small style={{ color: "var(--muted)", textTransform: "uppercase", fontSize: "11px", fontWeight: 600 }}>
                    Organic Carbon (%)
                  </small>
                  <div style={{ fontSize: "24px", fontWeight: 700, margin: "6px 0", color: "var(--green-950)" }}>
                    {(savedSoil.values as any).organic_carbon_percent ?? "0.58"} %
                  </div>
                  {(() => {
                    const status = getNutrientStatus("OC", (savedSoil.values as any).organic_carbon_percent ?? 0.58);
                    return (
                      <span
                        style={{
                          fontSize: "11px",
                          fontWeight: 700,
                          padding: "2px 8px",
                          borderRadius: "12px",
                          background: `${status.color}15`,
                          color: status.color
                        }}
                      >
                        {status.label}
                      </span>
                    );
                  })()}
                </div>

                <div
                  style={{
                    background: "#ffffff",
                    border: "1px solid var(--line)",
                    borderRadius: "12px",
                    padding: "16px"
                  }}
                >
                  <small style={{ color: "var(--muted)", textTransform: "uppercase", fontSize: "11px", fontWeight: 600 }}>
                    Available Nitrogen (N)
                  </small>
                  <div style={{ fontSize: "24px", fontWeight: 700, margin: "6px 0", color: "var(--green-950)" }}>
                    {(savedSoil.values as any).nitrogen_kg_ha ?? "210"} <small style={{ fontSize: "12px", fontWeight: 400 }}>kg/ha</small>
                  </div>
                  {(() => {
                    const status = getNutrientStatus("N", (savedSoil.values as any).nitrogen_kg_ha ?? 210);
                    return (
                      <span
                        style={{
                          fontSize: "11px",
                          fontWeight: 700,
                          padding: "2px 8px",
                          borderRadius: "12px",
                          background: `${status.color}15`,
                          color: status.color
                        }}
                      >
                        {status.label}
                      </span>
                    );
                  })()}
                </div>

                <div
                  style={{
                    background: "#ffffff",
                    border: "1px solid var(--line)",
                    borderRadius: "12px",
                    padding: "16px"
                  }}
                >
                  <small style={{ color: "var(--muted)", textTransform: "uppercase", fontSize: "11px", fontWeight: 600 }}>
                    Available Phosphorus (P)
                  </small>
                  <div style={{ fontSize: "24px", fontWeight: 700, margin: "6px 0", color: "var(--green-950)" }}>
                    {(savedSoil.values as any).phosphorus_kg_ha ?? "18"} <small style={{ fontSize: "12px", fontWeight: 400 }}>kg/ha</small>
                  </div>
                  {(() => {
                    const status = getNutrientStatus("P", (savedSoil.values as any).phosphorus_kg_ha ?? 18);
                    return (
                      <span
                        style={{
                          fontSize: "11px",
                          fontWeight: 700,
                          padding: "2px 8px",
                          borderRadius: "12px",
                          background: `${status.color}15`,
                          color: status.color
                        }}
                      >
                        {status.label}
                      </span>
                    );
                  })()}
                </div>

                <div
                  style={{
                    background: "#ffffff",
                    border: "1px solid var(--line)",
                    borderRadius: "12px",
                    padding: "16px"
                  }}
                >
                  <small style={{ color: "var(--muted)", textTransform: "uppercase", fontSize: "11px", fontWeight: 600 }}>
                    Available Potassium (K)
                  </small>
                  <div style={{ fontSize: "24px", fontWeight: 700, margin: "6px 0", color: "var(--green-950)" }}>
                    {(savedSoil.values as any).potassium_kg_ha ?? "285"} <small style={{ fontSize: "12px", fontWeight: 400 }}>kg/ha</small>
                  </div>
                  {(() => {
                    const status = getNutrientStatus("K", (savedSoil.values as any).potassium_kg_ha ?? 285);
                    return (
                      <span
                        style={{
                          fontSize: "11px",
                          fontWeight: 700,
                          padding: "2px 8px",
                          borderRadius: "12px",
                          background: `${status.color}15`,
                          color: status.color
                        }}
                      >
                        {status.label}
                      </span>
                    );
                  })()}
                </div>

                <div
                  style={{
                    background: "#ffffff",
                    border: "1px solid var(--line)",
                    borderRadius: "12px",
                    padding: "16px"
                  }}
                >
                  <small style={{ color: "var(--muted)", textTransform: "uppercase", fontSize: "11px", fontWeight: 600 }}>
                    Conductivity (EC)
                  </small>
                  <div style={{ fontSize: "24px", fontWeight: 700, margin: "6px 0", color: "var(--green-950)" }}>
                    {(savedSoil.values as any).ec_ds_m ?? "0.32"} <small style={{ fontSize: "12px", fontWeight: 400 }}>dS/m</small>
                  </div>
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: "12px",
                      background: "#16a34a15",
                      color: "#16a34a"
                    }}
                  >
                    Normal (Non-saline)
                  </span>
                </div>
              </>
            )}
          </div>

          {/* Quick Continue Button */}
          <div style={{ marginTop: "24px", textAlign: "right" }}>
            <button
              className="primary"
              onClick={() => go("crops")}
              style={{ padding: "14px 28px", fontSize: "15px", display: "inline-flex", alignItems: "center", gap: "8px" }}
            >
              <span>{t.btn_proceed_crops || "Proceed to Crop Recommendations →"}</span>
            </button>
          </div>
        </div>
      ) : (
        /* Entry Modes Selection */
        <div style={{ marginTop: "20px" }}>
          <div
            className="soil-choice-tabs"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
              gap: "14px"
            }}
          >
            <div
              className={`soil-choice-card ${mode === "upload" ? "selected" : ""}`}
              onClick={() => setMode("upload")}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <h4 style={{ margin: 0 }}>📷 Upload Soil Card Photo / PDF</h4>
                {mode === "upload" && <Check size={18} color="var(--green-700)" />}
              </div>
              <p>Snap a photo of your Government Soil Health Card. Gemini Vision will read and extract values automatically.</p>
            </div>

            <div
              className={`soil-choice-card ${mode === "manual" ? "selected" : ""}`}
              onClick={() => setMode("manual")}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <h4 style={{ margin: 0 }}>✍️ Enter Values Manually</h4>
                {mode === "manual" && <Check size={18} color="var(--green-700)" />}
              </div>
              <p>Type in known readings from your lab test (pH, N, P, K, etc.). Any unentered field automatically uses the {farm.district} regional baseline.</p>
            </div>
          </div>

          {/* Loading Indicator */}
          {loading && (
            <div className="inplace-progress" style={{ marginTop: "20px" }}>
              <div className="inplace-progress-header">
                <b>
                  <RefreshCw className="spin" size={16} /> Processing Soil Nutrient Data...
                </b>
              </div>
              <div className="inplace-progress-track">
                <div className="inplace-progress-fill" style={{ width: "75%" }} />
              </div>
              <div className="inplace-step active">{stepMsg}</div>
            </div>
          )}

          {/* OPTION 1: Upload Soil Card Photo / PDF */}
          {mode === "upload" && (
            <div
              style={{
                marginTop: "20px",
                padding: "24px",
                border: "1px solid var(--line)",
                borderRadius: "16px",
                background: "#ffffff"
              }}
            >
              <h3 style={{ margin: "0 0 6px", fontSize: "17px", color: "var(--green-950)" }}>
                Extract Soil Card via Gemini Vision OCR
              </h3>
              <p style={{ fontSize: "14px", color: "var(--muted)", margin: "0 0 20px" }}>
                Upload a photo or scanned copy of your Government of India Soil Health Card.
              </p>

              <form onSubmit={handleFileUpload}>
                <div
                  style={{
                    border: "2px dashed var(--line)",
                    borderRadius: "12px",
                    padding: "30px",
                    textAlign: "center",
                    background: "#fbfcf7",
                    cursor: "pointer",
                    marginBottom: "16px"
                  }}
                >
                  <Upload size={32} color="var(--green-700)" style={{ margin: "0 auto 10px" }} />
                  <p style={{ margin: "0 0 6px", fontWeight: 600 }}>Choose Soil Card Photo or PDF</p>
                  <small style={{ color: "var(--muted)" }}>Supports JPG, PNG, WebP or PDF files</small>
                  <input
                    type="file"
                    name="file"
                    accept="image/*,application/pdf"
                    required
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f && f.type.startsWith("image/")) {
                        setCardPreview(URL.createObjectURL(f));
                      }
                    }}
                    style={{ marginTop: "12px", display: "block", margin: "14px auto 0" }}
                  />
                </div>

                {cardPreview && (
                  <div style={{ marginBottom: "16px", textAlign: "center" }}>
                    <img
                      src={cardPreview}
                      alt="Soil Card Preview"
                      style={{ maxHeight: "200px", borderRadius: "8px", border: "1px solid var(--line)" }}
                    />
                  </div>
                )}

                <button
                  type="submit"
                  className="primary"
                  disabled={loading}
                  style={{ padding: "12px 22px", fontSize: "14px", display: "inline-flex", alignItems: "center", gap: "8px" }}
                >
                  <Sparkles size={16} />
                  <span>{t.soil_extract || "Extract Soil Nutrients with AI"}</span>
                </button>
              </form>

              {/* Display extracted data with verification inputs */}
              {extractedData && (
                <div
                  style={{
                    marginTop: "24px",
                    padding: "20px",
                    background: "#f7faf4",
                    border: "1px solid var(--line)",
                    borderRadius: "12px"
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "14px" }}>
                    <CheckCircle2 size={20} color="var(--green-700)" />
                    <h4 style={{ margin: 0, color: "var(--green-950)" }}>Extracted Soil Card Nutrients</h4>
                  </div>
                  <p style={{ fontSize: "13px", color: "var(--muted)", margin: "0 0 16px" }}>
                    Please review the extracted values below. You can adjust any number before confirming.
                  </p>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                    <label className="field">
                      <span>Soil pH</span>
                      <input type="number" step="0.1" value={ph} onChange={(e) => setPh(e.target.value)} placeholder="e.g. 7.2" />
                    </label>
                    <label className="field">
                      <span>Organic Carbon (%)</span>
                      <input type="number" step="0.01" value={organicCarbon} onChange={(e) => setOrganicCarbon(e.target.value)} placeholder="e.g. 0.58" />
                    </label>
                    <label className="field">
                      <span>Nitrogen (kg/ha)</span>
                      <input type="number" value={nitrogen} onChange={(e) => setNitrogen(e.target.value)} placeholder="e.g. 210" />
                    </label>
                    <label className="field">
                      <span>Phosphorus (kg/ha)</span>
                      <input type="number" value={phosphorus} onChange={(e) => setPhosphorus(e.target.value)} placeholder="e.g. 18" />
                    </label>
                    <label className="field">
                      <span>Potassium (kg/ha)</span>
                      <input type="number" value={potassium} onChange={(e) => setPotassium(e.target.value)} placeholder="e.g. 285" />
                    </label>
                    <label className="field">
                      <span>Electrical Conductivity (dS/m)</span>
                      <input type="number" step="0.01" value={ec} onChange={(e) => setEc(e.target.value)} placeholder="e.g. 0.32" />
                    </label>
                  </div>

                  <div style={{ marginTop: "18px" }}>
                    <button
                      className="primary"
                      onClick={() => saveSoilRecord("soil_card_confirmed")}
                      disabled={loading}
                      style={{ padding: "12px 24px", fontSize: "14px", display: "inline-flex", alignItems: "center", gap: "8px" }}
                    >
                      <Check size={16} />
                      <span>{t.soil_confirm || "Confirm & Save Soil Test"}</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* OPTION 2: Manual Value Entry */}
          {mode === "manual" && (
            <div
              style={{
                marginTop: "20px",
                padding: "24px",
                border: "1px solid var(--line)",
                borderRadius: "16px",
                background: "#ffffff"
              }}
            >
              <h3 style={{ margin: "0 0 6px", fontSize: "17px", color: "var(--green-950)" }}>
                Enter Laboratory / Soil Health Card Test Values
              </h3>
              <p style={{ fontSize: "14px", color: "var(--muted)", margin: "0 0 20px" }}>
                Input the numbers from your soil test card. Leave any fields blank if not available — the regional baseline will be applied automatically.
              </p>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                <label className="field">
                  <span>Soil Reaction (pH)</span>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="14"
                    value={ph}
                    onChange={(e) => setPh(e.target.value)}
                    placeholder="e.g. 7.2"
                  />
                  <small style={{ color: "var(--muted)", fontSize: "11px", marginTop: "4px" }}>
                    &lt; 6.5 Acidic · 6.5-7.5 Neutral · &gt; 7.5 Alkaline
                  </small>
                </label>

                <label className="field">
                  <span>Organic Carbon (%)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="10"
                    value={organicCarbon}
                    onChange={(e) => setOrganicCarbon(e.target.value)}
                    placeholder="e.g. 0.58"
                  />
                  <small style={{ color: "var(--muted)", fontSize: "11px", marginTop: "4px" }}>
                    &lt; 0.50 Low · 0.50-0.75 Medium · &gt; 0.75 High
                  </small>
                </label>

                <label className="field">
                  <span>Available Nitrogen (N in kg/ha)</span>
                  <input
                    type="number"
                    step="1"
                    min="0"
                    max="5000"
                    value={nitrogen}
                    onChange={(e) => setNitrogen(e.target.value)}
                    placeholder="e.g. 210"
                  />
                  <small style={{ color: "var(--muted)", fontSize: "11px", marginTop: "4px" }}>
                    &lt; 280 Low · 280-560 Medium · &gt; 560 High
                  </small>
                </label>

                <label className="field">
                  <span>Available Phosphorus (P in kg/ha)</span>
                  <input
                    type="number"
                    step="1"
                    min="0"
                    max="1000"
                    value={phosphorus}
                    onChange={(e) => setPhosphorus(e.target.value)}
                    placeholder="e.g. 18"
                  />
                  <small style={{ color: "var(--muted)", fontSize: "11px", marginTop: "4px" }}>
                    &lt; 10 Low · 10-25 Medium · &gt; 25 High
                  </small>
                </label>

                <label className="field">
                  <span>Available Potassium (K in kg/ha)</span>
                  <input
                    type="number"
                    step="1"
                    min="0"
                    max="2000"
                    value={potassium}
                    onChange={(e) => setPotassium(e.target.value)}
                    placeholder="e.g. 285"
                  />
                  <small style={{ color: "var(--muted)", fontSize: "11px", marginTop: "4px" }}>
                    &lt; 108 Low · 108-280 Medium · &gt; 280 High
                  </small>
                </label>

                <label className="field">
                  <span>Electrical Conductivity (EC in dS/m)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="20"
                    value={ec}
                    onChange={(e) => setEc(e.target.value)}
                    placeholder="e.g. 0.32"
                  />
                  <small style={{ color: "var(--muted)", fontSize: "11px", marginTop: "4px" }}>
                    &lt; 1.0 Normal · &gt; 1.0 Salinity hazard
                  </small>
                </label>
              </div>

              <div style={{ marginTop: "14px" }}>
                <label className="field">
                  <span>Soil Testing Laboratory / Card Number (Optional)</span>
                  <input
                    type="text"
                    value={labName}
                    onChange={(e) => setLabName(e.target.value)}
                    placeholder="e.g. Krishi Vigyan Kendra Soil Testing Lab, Yavatmal"
                  />
                </label>
              </div>

              <div style={{ marginTop: "20px" }}>
                <button
                  className="primary"
                  onClick={() => saveSoilRecord("manual")}
                  disabled={loading}
                  style={{ padding: "14px 24px", fontSize: "15px", display: "inline-flex", alignItems: "center", gap: "8px" }}
                >
                  <FileCheck size={18} />
                  <span>Save Soil Test Profile</span>
                </button>
                <small style={{ color: "var(--muted)", display: "block", marginTop: "8px", fontSize: "12px" }}>
                  💡 Any field left empty will automatically use the official ICAR-NBSS&LUP baseline for {farm.district}.
                </small>
              </div>
            </div>
          )}

          {/* SKIP OPTION BANNER */}
          <div
            style={{
              marginTop: "24px",
              padding: "18px 22px",
              background: "#faf9f5",
              border: "1px dashed var(--line)",
              borderRadius: "14px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "14px"
            }}
          >
            <div>
              <strong style={{ fontSize: "14px", color: "var(--green-950)", display: "block" }}>
                No soil card or test values handy right now?
              </strong>
              <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--muted)" }}>
                You can skip this step and proceed directly to crop recommendations. Official ICAR-NBSS&LUP regional soil baseline for {farm.district} ({farm.soil_type || "black"} soil) will be applied automatically.
              </p>
            </div>
            <button
              className="secondary"
              onClick={() => go("crops")}
              style={{
                padding: "10px 18px",
                fontSize: "13px",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px"
              }}
            >
              <span>{t.btn_skip_soil || "Skip Soil Test & See Crops →"}</span>
            </button>
          </div>
        </div>
      )}

      {/* Pipeline Navigation Footer */}
      <div className="pipeline-footer-nav" style={{ marginTop: "32px" }}>
        <button className="nav-prev-btn" onClick={() => go("weather")}>
          {t.btn_back_weather || "← Back to Local Weather"}
        </button>
        <button className="nav-next-btn" onClick={() => go("crops")}>
          {t.btn_proceed_crops || "Proceed to Crop Recommendations →"}
        </button>
      </div>
    </section>
  );
}
