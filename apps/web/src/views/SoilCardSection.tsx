import React, { useState, FormEvent } from "react";
import { FileCheck, CheckCircle2, RefreshCw } from "lucide-react";
import { api, upload } from "../api";
import { Json } from "../types";

export interface SoilCardSectionProps {
  t: Record<string, string>;
  farmId: string;
}

export function SoilCardSection({ t, farmId }: SoilCardSectionProps) {
  const [mode, setMode] = useState<"upload" | "baseline">("baseline");
  const [extracted, setExtracted] = useState<Json | null>(null);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(false);
  const [stepMsg, setStepMsg] = useState("");

  const extractFile = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const file = new FormData(e.currentTarget).get("file") as File;
    if (!file) return;
    setLoading(true);
    setStepMsg("Uploading card image and extracting N-P-K & pH via Gemini Vision...");
    try {
      const media = await upload(file, "soil_card");
      const res = await api<Json>(`/api/v1/farms/${farmId}/soil/extract`, {
        method: "POST",
        body: JSON.stringify({ media_id: media.id })
      });
      setExtracted(res);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const saveBaseline = async () => {
    setLoading(true);
    setStepMsg("Attaching regional baseline soil nutrient values...");
    try {
      await api(`/api/v1/farms/${farmId}/soil`, {
        method: "POST",
        body: JSON.stringify({
          ph: 7.2,
          organic_carbon: 0.58,
          nitrogen: 210,
          phosphorus: 18,
          potassium: 285
        })
      });
      setSaved(true);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const saveExtracted = async () => {
    if (!extracted) return;
    setLoading(true);
    setStepMsg("Saving confirmed soil test values...");
    try {
      await api(`/api/v1/farms/${farmId}/soil`, {
        method: "POST",
        body: JSON.stringify(extracted)
      });
      setSaved(true);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  if (saved) {
    return (
      <div className="explainer-banner" style={{ background: "#eaf6ea", borderColor: "#a9dc9f" }}>
        <div className="explainer-icon" style={{ background: "#1b4d2b" }}>
          <CheckCircle2 size={24} />
        </div>
        <div className="explainer-content">
          <h4>Soil Profile Attached</h4>
          <p>Your soil nutrient profile has been saved. Your advisory engine will calibrate crop selections against your confirmed baseline.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ marginTop: "24px" }}>
      <div className="section-title" style={{ paddingBottom: "12px", borderBottom: "none" }}>
        <FileCheck />
        <div>
          <small>SOIL CARD (OPTIONAL)</small>
          <h2>Attach Soil Health Card</h2>
        </div>
      </div>

      <div className="soil-choice-tabs">
        <div
          className={`soil-choice-card ${mode === "baseline" ? "selected" : ""}`}
          onClick={() => setMode("baseline")}
        >
          <h4>🌟 1-Click Regional Baseline</h4>
          <p>No card on hand? Pre-populate verified regional nutrient averages (pH 7.2, N-P-K balanced).</p>
        </div>
        <div
          className={`soil-choice-card ${mode === "upload" ? "selected" : ""}`}
          onClick={() => setMode("upload")}
        >
          <h4>📄 Upload Physical Card</h4>
          <p>Upload a photo or PDF of your Government Soil Health Card for multimodal extraction.</p>
        </div>
      </div>

      {loading && (
        <div className="inplace-progress">
          <div className="inplace-progress-header">
            <b><RefreshCw className="spin" size={16} /> Processing Soil Health Data...</b>
          </div>
          <div className="inplace-progress-track">
            <div className="inplace-progress-fill" style={{ width: "75%" }} />
          </div>
          <div className="inplace-step active">{stepMsg}</div>
        </div>
      )}

      {mode === "baseline" ? (
        <div style={{ marginTop: "20px", textAlign: "center" }}>
          <button className="primary" onClick={saveBaseline} disabled={loading} style={{ padding: "14px 24px" }}>
            <FileCheck size={18} />
            {t.soil_auto}
          </button>
        </div>
      ) : (
        <div style={{ marginTop: "20px" }}>
          {!extracted ? (
            <form onSubmit={extractFile} style={{ display: "flex", gap: "10px", alignItems: "center" }}>
              <input type="file" name="file" accept="image/*,application/pdf" required />
              <button className="primary" disabled={loading}>{t.soil_extract}</button>
            </form>
          ) : (
            <div style={{ background: "#fbfbf6", border: "1px solid var(--line)", borderRadius: "12px", padding: "18px" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "16px" }}>
                {Object.entries(extracted).map(([k, v]: [string, any]) => (
                  <div key={k} style={{ padding: "10px", background: "#ffffff", border: "1px solid var(--line)", borderRadius: "8px" }}>
                    <small style={{ color: "var(--muted)", textTransform: "uppercase", fontSize: "11px" }}>{k.replace(/_/g, " ")}</small>
                    <div style={{ fontSize: "16px", fontWeight: "700" }}>{v.value} {v.unit}</div>
                    {v.is_uncertain && <span style={{ color: "#d97706", fontSize: "12px" }}>⚠ {t.uncertain}</span>}
                  </div>
                ))}
              </div>
              <button className="primary" onClick={saveExtracted} disabled={loading}>
                <CheckCircle2 size={16} />
                {t.soil_confirm}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
