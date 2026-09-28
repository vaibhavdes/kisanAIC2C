import React, { useState } from "react";
import { FileUp, FlaskConical, Pencil, Sparkles, Volume2 } from "lucide-react";
import { api, speakText, upload } from "../api";
import { invalidate, useResource } from "../hooks";
import { Json, Locale, T, View } from "../types";
import { ErrorNote, formatDate, Loading, NeedFarm, SourceBadge, StageHeader } from "../components/ui";

interface Props {
  t: T;
  locale: Locale;
  farm?: Json;
  go: (v: View) => void;
}

const PARAMS: Array<{ key: string; unit: string; step: string }> = [
  { key: "ph", unit: "", step: "0.1" },
  { key: "ec_ds_m", unit: "dS/m", step: "0.01" },
  { key: "organic_carbon_percent", unit: "%", step: "0.01" },
  { key: "nitrogen_kg_ha", unit: "kg/ha", step: "1" },
  { key: "phosphorus_kg_ha", unit: "kg/ha", step: "0.1" },
  { key: "potassium_kg_ha", unit: "kg/ha", step: "1" },
  { key: "sulphur_ppm", unit: "ppm", step: "0.1" },
  { key: "zinc_ppm", unit: "ppm", step: "0.01" },
  { key: "iron_ppm", unit: "ppm", step: "0.1" },
  { key: "copper_ppm", unit: "ppm", step: "0.01" },
  { key: "manganese_ppm", unit: "ppm", step: "0.1" },
  { key: "boron_ppm", unit: "ppm", step: "0.01" },
];

const RATING_TONE: Record<string, string> = {
  low: "warn", deficient: "warn", acidic: "warn", saline: "warn", strongly_alkaline: "warn",
  medium: "good", neutral: "good", normal: "good", sufficient: "good", alkaline: "fair", high: "info",
};

type Values = Record<string, string>;

export function SoilView({ t, locale, farm, go }: Props) {
  const soil = useResource<Json | null>(farm ? `/api/v1/farms/${farm.id}/soil` : null);
  const land = useResource<Json | null>(farm ? `/api/v1/farms/${farm.id}/land-profile` : null);
  const [mode, setMode] = useState<"view" | "upload" | "manual">("view");
  const [values, setValues] = useState<Values>({});
  const [extraction, setExtraction] = useState<Json | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  if (!farm) return <NeedFarm t={t} go={go} />;

  const startManual = () => {
    const current = soil.data?.values || {};
    setValues(Object.fromEntries(PARAMS.map((p) => [p.key, current[p.key] != null ? String(current[p.key]) : ""])));
    setExtraction(null);
    setMode("manual");
  };

  const readCard = async (file: File) => {
    setBusy(true);
    setError("");
    setPreview(file.type.startsWith("image/") ? URL.createObjectURL(file) : null);
    try {
      const media = await upload(file, "soil_card");
      const result = await api<Json>(`/api/v1/farms/${farm.id}/soil/extract?media_id=${media.id}&locale=${locale}`, { method: "POST" });
      setExtraction(result);
      setValues(Object.fromEntries(PARAMS.map((p) => [p.key, result.values?.[p.key] != null ? String(result.values[p.key]) : ""])));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    const parsed = Object.fromEntries(PARAMS.map((p) => [p.key, values[p.key] === "" || values[p.key] == null ? null : Number(values[p.key])]));
    if (Object.values(parsed).every((v) => v === null)) {
      setError(t("soil_enter_one"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api(`/api/v1/farms/${farm.id}/soil`, {
        method: "POST",
        body: JSON.stringify({
          values: parsed,
          sample_date: extraction?.sample_date || null,
          lab_name: extraction?.lab_name || null,
          card_recommendations: extraction?.card_recommendations || [],
          source: extraction ? "soil_card_confirmed" : "manual",
          confirmed: true,
        }),
      });
      invalidate(`/api/v1/farms/${farm.id}`);
      await soil.reload();
      setMode("view");
      setExtraction(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const saved = soil.data;
  const estimate = land.data?.soil;

  return (
    <section className="panel">
      <StageHeader icon={<FlaskConical />} step={t("step_n", { n: 3 })} title={t("soil_title")} subtitle={t("soil_sub")} />
      {soil.loading && !saved && <Loading label={t("loading")} />}
      {soil.error && <ErrorNote t={t} message={soil.error} onRetry={soil.reload} />}

      {mode === "view" && (
        <>
          {saved ? (
            <div className="card-block">
              <div className="block-head">
                <h3>{t("soil_your_test")}</h3>
                <SourceBadge t={t} kind="measured" />
                {saved.sample_date && <span className="muted">{t("sampled_on", { date: formatDate(saved.sample_date, locale) })}</span>}
                {saved.lab_name && <span className="muted">· {saved.lab_name}</span>}
              </div>
              <div className="rating-grid">
                {(saved.ratings as Json[]).map((r) => (
                  <div key={r.parameter} className="rating-card">
                    <small>{t(`soil_${r.parameter}`)}</small>
                    <b>{r.value} <span>{r.unit !== "pH" ? r.unit : ""}</span></b>
                    <span className={`status-pill tone-${RATING_TONE[r.rating] || "info"}`}>{t(`rating_${r.rating}`)}</span>
                  </div>
                ))}
              </div>
              {saved.card_recommendations?.length > 0 && (
                <div className="card-recs">
                  <h4>{t("card_recommendations")}</h4>
                  <ul>{saved.card_recommendations.map((item: string) => <li key={item}>{item}</li>)}</ul>
                </div>
              )}
              <SoilAdvice t={t} ratings={saved.ratings} />
            </div>
          ) : (
            <div className="card-block empty-soil">
              <h3>{t("soil_no_test")}</h3>
              <p>{t("soil_no_test_desc")}</p>
            </div>
          )}

          {estimate && (
            <div className="card-block subtle">
              <div className="block-head">
                <h3>{t("soil_estimate_title")}</h3>
                <SourceBadge t={t} kind="estimated" />
              </div>
              <p className="muted">{t("soil_estimate_desc")}</p>
              {estimate.radius_m > 300 && <p className="muted">{t("soil_estimate_wide", { km: estimate.radius_m / 1000 })}</p>}
              <div className="stat-row">
                {estimate.ph != null && <span>pH: <b>{estimate.ph}</b></span>}
                {estimate.texture_class && <span>{t("texture")}: <b>{t(`texture_${estimate.texture_class}`)}</b></span>}
                {estimate.clay_percent != null && <span>{t("clay")}: <b>{Math.round(estimate.clay_percent)}%</b></span>}
                {estimate.sand_percent != null && <span>{t("sand")}: <b>{Math.round(estimate.sand_percent)}%</b></span>}
              </div>
            </div>
          )}

          {land.data && !estimate && !saved && <p className="muted">{t("soil_estimate_none")}</p>}

          <div className="choice-row">
            <label className="choice-card">
              <FileUp size={22} />
              <b>{t("soil_upload")}</b>
              <span>{t("soil_upload_desc")}</span>
              <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" hidden
                     onChange={(e) => { const f = e.target.files?.[0]; if (f) { setMode("upload"); readCard(f); } }} />
            </label>
            <button className="choice-card" onClick={startManual}>
              <Pencil size={22} />
              <b>{saved ? t("soil_edit") : t("soil_manual")}</b>
              <span>{t("soil_manual_desc")}</span>
            </button>
          </div>
        </>
      )}

      {mode !== "view" && (
        <div className="card-block">
          {busy && mode === "upload" && !extraction && <Loading label={t("reading_card")} />}
          {preview && <img className="card-preview" src={preview} alt={t("soil_card")} />}
          {extraction && (
            <div className="extraction-summary">
              <h3><Sparkles size={18} /> {t("card_read_title")}</h3>
              {extraction.plain_explanation && (
                <div className="explain-box">
                  <p>{extraction.plain_explanation}</p>
                  <button className="icon-btn" onClick={() => speakText(extraction.plain_explanation, locale).catch(() => undefined)}>
                    <Volume2 size={16} /> {t("listen")}
                  </button>
                </div>
              )}
              {extraction.card_recommendations?.length > 0 && (
                <div className="card-recs">
                  <h4>{t("card_recommendations")}</h4>
                  <ul>{extraction.card_recommendations.map((item: string) => <li key={item}>{item}</li>)}</ul>
                </div>
              )}
              {extraction.uncertain_fields?.length > 0 && <p className="warn-text">{t("check_highlighted")}</p>}
            </div>
          )}
          {(mode === "manual" || extraction) && (
            <>
              <h3>{t("check_values")}</h3>
              <div className="param-grid">
                {PARAMS.map((p) => {
                  const unsure = extraction?.uncertain_fields?.includes(p.key);
                  return (
                    <label key={p.key} className={`field ${unsure ? "unsure" : ""}`}>
                      <span>{t(`soil_${p.key}`)} {p.unit && <small>({p.unit})</small>}</span>
                      <input type="number" step={p.step} min="0" value={values[p.key] ?? ""} onChange={(e) => setValues({ ...values, [p.key]: e.target.value })} />
                    </label>
                  );
                })}
              </div>
              <p className="hint">{t("leave_blank_hint")}</p>
            </>
          )}
          {error && <ErrorNote t={t} message={error} />}
          <div className="form-actions">
            <button className="secondary" onClick={() => { setMode("view"); setExtraction(null); setPreview(null); setError(""); }}>{t("cancel")}</button>
            {(mode === "manual" || extraction) && <button className="primary" onClick={save} disabled={busy}>{busy ? t("saving") : t("save_soil")}</button>}
          </div>
        </div>
      )}

      <div className="pipeline-footer-nav">
        <button className="nav-prev-btn" onClick={() => go("weather")}>{t("back")}</button>
        <button className="nav-next-btn" onClick={() => go("crops")}>{saved ? t("next_crops") : t("skip_to_crops")}</button>
      </div>
    </section>
  );
}

function SoilAdvice({ t, ratings }: { t: T; ratings: Json[] }) {
  const tips: string[] = [];
  const get = (p: string) => ratings.find((r) => r.parameter === p)?.rating;
  if (get("organic_carbon_percent") === "low") tips.push(t("tip_oc_low"));
  if (get("nitrogen_kg_ha") === "low") tips.push(t("tip_n_low"));
  if (get("ph") === "acidic") tips.push(t("tip_ph_acidic"));
  if (get("ph") === "alkaline" || get("ph") === "strongly_alkaline") tips.push(t("tip_ph_alkaline"));
  if (get("zinc_ppm") === "deficient") tips.push(t("tip_zn_low"));
  if (get("ec_ds_m") === "saline") tips.push(t("tip_saline"));
  if (!tips.length) return null;
  return (
    <div className="tips">
      <h4>{t("what_it_means")}</h4>
      <ul>{tips.map((tip) => <li key={tip}>{tip}</li>)}</ul>
    </div>
  );
}

