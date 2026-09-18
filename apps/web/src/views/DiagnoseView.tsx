import React, { useState, FormEvent } from "react";
import { Microscope, Info, RefreshCw, ArrowRight, Upload } from "lucide-react";
import { api, upload } from "../api";
import { View, Locale, Json } from "../types";

export interface DiagnoseViewProps {
  t: Record<string, string>;
  locale: Locale;
  farm?: Json;
  go: (v: View) => void;
}

export function DiagnoseView({ t, locale, farm, go }: DiagnoseViewProps) {
  const [result, setResult] = useState<Json | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [selectedCrop, setSelectedCrop] = useState(farm?.current_crop || "");
  const [symptomChips, setSymptomChips] = useState<string[]>([]);
  const [customSymptom, setCustomSymptom] = useState("");
  const [analyzing, setAnalyzing] = useState(false);

  const symptomsList = [
    "🟡 Yellowing Leaves",
    "🟤 Brown Blight Spots",
    "⚪ Powdery Coating",
    "🐛 Stem Borer Damage",
    "🍂 Plant Wilting",
    "🔄 Leaf Curling"
  ];

  const toggleSymptom = (item: string) => {
    setSymptomChips(prev =>
      prev.includes(item) ? prev.filter(x => x !== item) : [...prev, item]
    );
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setPreview(URL.createObjectURL(file));
    }
  };

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const d = new FormData(e.currentTarget);
    const file = d.get("file") as File;
    if (!file || file.size === 0) return;

    const fullSymptoms = [...symptomChips, customSymptom].filter(Boolean).join(", ");
    setAnalyzing(true);

    try {
      const media = await upload(file, "crop_diagnosis");
      const stageVal = (d.get("stage") as string) || "";
      const endpoint = farm?.id ? `/api/v1/farms/${farm.id}/diagnoses` : `/api/v1/diagnoses`;
      const res = await api<Json>(endpoint, {
        method: "POST",
        body: JSON.stringify({
          media_id: media.id,
          crop: selectedCrop || "auto-detect",
          crop_stage: stageVal || null,
          symptoms: fullSymptoms || null,
          locale
        })
      });
      setResult(res);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <section className="panel narrow">
      <div className="section-title">
        <Microscope />
        <div>
          <small>INSTANT AI PLANT DOCTOR · {farm?.name || "ANY FIELD OR GARDEN"}</small>
          <h2>{t.diagnose || "Plant Doctor"}</h2>
        </div>
      </div>

      <div className="explainer-banner">
        <div className="explainer-icon"><Info size={20} /></div>
        <div className="explainer-content">
          <h4>{t.diagnose_explainer_title || "Visual Crop Doctor"}</h4>
          <p>{t.diagnose_explainer_desc || "Powered by Gemini Multimodal AI. Inspects leaf symptoms, diagnoses likely issues, provides low-risk organic remedies, and escalates uncertain cases to real extension experts."}</p>
        </div>
      </div>

      <form onSubmit={submit}>
        <div className="form-section">
          <label className="field">
            <span>{t.affected_crop_title || "Affected Crop (Optional)"}</span>
            <select
              value={selectedCrop}
              onChange={e => setSelectedCrop(e.target.value)}
              style={{ fontSize: "14px", fontWeight: selectedCrop ? 600 : 400 }}
            >
              <option value="">{t.auto_detect_crop_opt || "-- Auto-detect crop from photo (Gemini Vision) --"}</option>
              <option value="cotton">Cotton (कापूस / कपास)</option>
              <option value="soybean">Soybean (सोयाबीन)</option>
              <option value="sorghum">Sorghum (ज्वारी / ज्वार)</option>
              <option value="pigeon_pea">Pigeon Pea / Tur (तूर / अरहर)</option>
              <option value="chickpea">Chickpea / Harbara (हरभरा / चना)</option>
              <option value="rice">Rice / Paddy (भात / धान)</option>
              <option value="wheat">Wheat (गहू / गेहूं)</option>
              <option value="maize">Maize (मका / मक्का)</option>
              <option value="groundnut">Groundnut (भुईमूग / मूंगफली)</option>
              <option value="onion">Onion (कांदा / प्याज)</option>
              <option value="sugarcane">Sugarcane (ऊस / गन्ना)</option>
            </select>
          </label>
        </div>

        <div className="photo-dropzone">
          <input
            type="file"
            name="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={handleFileChange}
            required
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
              opacity: 0,
              cursor: "pointer"
            }}
          />
          {preview ? (
            <img src={preview} alt="Crop preview" className="photo-preview" />
          ) : (
            <div>
              <Upload size={36} color="var(--green-700)" style={{ marginBottom: "10px" }} />
              <div style={{ fontWeight: 700, fontSize: "15px" }}>{t.tap_photo_prompt || "Tap to upload or take photo of affected leaf"}</div>
              <small style={{ color: "var(--muted)" }}>{t.photo_format_hint || "PNG, JPG or WebP supported"}</small>
            </div>
          )}
        </div>

        <div className="form-section" style={{ marginTop: "20px" }}>
          <label className="field">
            <span>{t.observed_symptoms_title || "Observed Symptoms (Optional)"}</span>
            <select
              onChange={e => {
                if (e.target.value) {
                  toggleSymptom(e.target.value);
                  e.target.value = "";
                }
              }}
              style={{ fontSize: "14px" }}
            >
              <option value="">{t.select_symptom_opt || "-- Select symptom from list (optional) --"}</option>
              {symptomsList.map(s => (
                <option key={s} value={s} disabled={symptomChips.includes(s)}>
                  {s} {symptomChips.includes(s) ? "✓ (Selected)" : ""}
                </option>
              ))}
            </select>
          </label>

          {symptomChips.length > 0 && (
            <div className="chip-group" style={{ marginTop: "10px" }}>
              {symptomChips.map(s => (
                <span
                  key={s}
                  className="chip active"
                  style={{ display: "inline-flex", alignItems: "center", gap: "6px", cursor: "pointer" }}
                  onClick={() => toggleSymptom(s)}
                  title="Click to remove"
                >
                  {s} <span style={{ fontWeight: 800, marginLeft: "4px" }}>×</span>
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="form-grid" style={{ marginTop: "16px" }}>
          <label className="field">
            <span>{t.growth_stage_label || "Crop Growth Stage (Optional)"}</span>
            <select name="stage" defaultValue="">
              <option value="">{t.auto_detect_stage_opt || "-- Optional: Auto-detect from photo --"}</option>
              <option value="seedling">{t.stage_seedling || "Seedling (0-20 days)"}</option>
              <option value="vegetative">{t.stage_vegetative || "Vegetative Growth"}</option>
              <option value="flowering">{t.stage_flowering || "Flowering / Squaring"}</option>
              <option value="pod_filling">{t.stage_pod_filling || "Boll / Pod Filling"}</option>
              <option value="maturity">{t.stage_maturity || "Pre-Harvest Maturity"}</option>
            </select>
          </label>

          <label className="field">
            <span>{t.additional_notes || "Additional Observations (Optional)"}</span>
            <input
              placeholder={t.notes_placeholder || "e.g. Started after recent heavy rain"}
              value={customSymptom}
              onChange={e => setCustomSymptom(e.target.value)}
            />
          </label>
        </div>

        {analyzing && (
          <div className="inplace-progress">
            <div className="inplace-progress-header">
              <b><RefreshCw className="spin" size={16} /> {t.analyzing_leaf || "Analyzing Leaf Pathology..."}</b>
            </div>
            <div className="inplace-progress-track">
              <div className="inplace-progress-fill" style={{ width: "70%" }} />
            </div>
            <div className="inplace-step active">
              {t.analyzing_leaf_desc || "Inspecting discoloration, pest lesions, and fungal symptoms with Gemini Vision..."}
            </div>
          </div>
        )}

        <button
          type="submit"
          className="primary"
          disabled={analyzing}
          style={{ width: "100%", padding: "16px", marginTop: "24px", fontSize: "16px" }}
        >
          <Microscope size={18} />
          {t.upload_photo}
          <ArrowRight size={18} />
        </button>
      </form>

      {/* Diagnosis Outcome Card */}
      {result && (
        <article className="diagnosis-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "12px", color: "var(--lime-400)", fontWeight: 700 }}>
              IMAGE QUALITY: {result.diagnosis.image_quality?.toUpperCase() || "USABLE"}
            </span>
            {result.expert_case && (
              <span style={{ background: "var(--lime-500)", color: "var(--green-900)", padding: "4px 10px", borderRadius: "20px", fontSize: "12px", fontWeight: 800 }}>
                {t.escalated_badge || "👨‍🔬 Escalated to Agronomist"}
              </span>
            )}
          </div>

          <h3>{t.visible_findings_title || "Visible Leaf Symptoms"}</h3>
          <ul>
            {result.diagnosis.visible_findings.map((x: string) => (
              <li key={x}>{x}</li>
            ))}
          </ul>

          <h3>{t.plausible_causes_title || "Plausible Causes"}</h3>
          <ul>
            {result.diagnosis.plausible_causes.map((x: string) => (
              <li key={x}>{x}</li>
            ))}
          </ul>

          <h3>{t.safe_next_steps_title || "Safe Organic Remedies & Next Steps"}</h3>
          <ul>
            {result.diagnosis.safe_next_steps.map((x: string) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </article>
      )}
    </section>
  );
}
