import { FormEvent, useEffect, useState } from "react";
import { ArrowRight, Edit3, FlaskConical, RefreshCw, Upload } from "lucide-react";
import { api, upload } from "../api";
import { Json, Locale, View } from "../types";
import { InfoTip } from "../components/InfoTip";

export interface SoilViewProps {
  t: Record<string, string>;
  locale: Locale;
  farm?: Json;
  cropRecs: Json | null;
  season: string;
  go: (v: View) => void;
  onSoilSaved?: () => void;
}

const FIELDS: Array<{ key: string; label: string; unit: string; step: string; term?: string }> = [
  { key: "ph", label: "ph_label", unit: "", step: "0.1", term: "ph" },
  { key: "organic_carbon_percent", label: "oc_label", unit: "%", step: "0.01", term: "oc" },
  { key: "nitrogen_kg_ha", label: "n_label", unit: "kg/ha", step: "1", term: "npk" },
  { key: "phosphorus_kg_ha", label: "p_label", unit: "kg/ha", step: "0.1", term: "npk" },
  { key: "potassium_kg_ha", label: "k_label", unit: "kg/ha", step: "1", term: "npk" },
  { key: "ec_ds_m", label: "ec_label", unit: "dS/m", step: "0.01" },
];

const ALL_CROPS = ["soybean", "cotton", "pigeon_pea", "sorghum", "chickpea", "wheat", "groundnut", "maize", "pearl_millet", "onion", "sugarcane", "rice"];

export function SoilView({ t, locale, farm, cropRecs, season, go, onSoilSaved }: SoilViewProps) {
  const [profile, setProfile] = useState<Json | null>(null);
  const [form, setForm] = useState<Record<string, string> | null>(null);
  const [extraction, setExtraction] = useState<Json | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [crop, setCrop] = useState("");
  const [plan, setPlan] = useState<Json | null>(null);

  const cropOptions: Json[] = [
    ...(cropRecs?.recommendations || []),
    ...(cropRecs?.unsuitable_crops || []),
  ];
  const defaultCrop = farm?.current_crop || cropRecs?.recommendations?.[0]?.crop || "soybean";

  const loadProfile = async () => {
    if (!farm) return;
    try {
      setProfile(await api<Json>(`/api/v1/farms/${farm.id}/soil/profile`));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    setForm(null);
    setExtraction(null);
    loadProfile();
  }, [farm?.id]);

  useEffect(() => {
    if (!crop && defaultCrop) setCrop(defaultCrop);
  }, [defaultCrop]);

  useEffect(() => {
    if (!farm || !crop) return;
    api<Json>(`/api/v1/farms/${farm.id}/fertilizer?crop=${encodeURIComponent(crop)}&season=${season}`)
      .then(setPlan)
      .catch(e => { setPlan(null); setError((e as Error).message); });
  }, [farm?.id, crop, season, profile?.soil_test?.id]);

  if (!farm) {
    return (
      <section className="panel empty-state">
        <FlaskConical size={40} />
        <h2>{t.add_farm_first}</h2>
        <button className="primary" onClick={() => go("farm")}>{t.home_add_farm}</button>
      </section>
    );
  }

  const startManual = () => {
    const measured = (profile?.soil_test?.values || {}) as Json;
    setForm(Object.fromEntries(FIELDS.map(f => [f.key, measured[f.key] != null ? String(measured[f.key]) : ""])));
    setExtraction(null);
  };

  const onUpload = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const file = new FormData(e.currentTarget).get("file") as File;
    if (!file || !file.size) return;
    setBusy(t.soil_extracting);
    setError("");
    try {
      const media = await upload(file, "soil_card");
      const result = await api<Json>(`/api/v1/farms/${farm.id}/soil/extract?media_id=${media.id}&locale=${locale}`, { method: "POST" });
      setExtraction(result);
      const values = (result.values || {}) as Json;
      setForm(Object.fromEntries(FIELDS.map(f => [f.key, values[f.key] != null ? String(values[f.key]) : ""])));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  };

  const save = async () => {
    if (!form) return;
    setBusy(t.loading);
    setError("");
    try {
      await api(`/api/v1/farms/${farm.id}/soil`, {
        method: "POST",
        body: JSON.stringify({
          values: Object.fromEntries(FIELDS.map(f => [f.key, form[f.key] ? Number(form[f.key]) : null])),
          sample_date: extraction?.sample_date || null,
          lab_name: extraction?.lab_name || null,
          source: extraction ? "soil_card_confirmed" : "manual",
          confirmed: true,
        }),
      });
      setForm(null);
      setExtraction(null);
      await loadProfile();
      onSoilSaved?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  };

  const values: Json = profile?.values || {};
  const soilTest: Json | null = profile?.soil_test || null;
  const uncertain: string[] = extraction?.uncertain_fields || [];

  return (
    <section className="panel">
      <div className="section-title">
        <FlaskConical />
        <div>
          <small>{farm.name} · {farm.district}</small>
          <h2>{t.soil_title}</h2>
        </div>
      </div>

      {error && <div className="notice error" onClick={() => setError("")}>{error}</div>}

      <div className="soil-values">
        {FIELDS.filter(f => f.key !== "ec_ds_m" || values.ec_ds_m?.value != null || soilTest?.values?.ec_ds_m != null).map(f => {
          const item: Json = values[f.key] || { value: soilTest?.values?.[f.key] ?? null, source: soilTest?.values?.[f.key] != null ? "soil_test" : "unknown" };
          return (
            <div key={f.key} className="soil-value-card">
              <small>{t[f.label]} {f.term && <InfoTip term={f.term} locale={locale} />}</small>
              <strong>{item.value != null ? `${item.value} ${f.unit}` : "--"}</strong>
              <div className="soil-value-meta">
                {item.rating && <span className={`rating ${item.rating}`}>{t[`rating_${item.rating}`]}</span>}
                <span className={`source ${item.source}`}>{t[`soil_source_${item.source}`] || item.source}</span>
              </div>
            </div>
          );
        })}
      </div>
      <p className="muted small-text">
        {soilTest
          ? `${t.soil_source_soil_test}: ${[soilTest.lab_name, soilTest.sample_date].filter(Boolean).join(" · ") || new Date(soilTest.created_at).toLocaleDateString(locale)}. `
          : ""}
        {t.soil_profile_note} <InfoTip term="district_average" locale={locale} />
      </p>

      {!form ? (
        <div className="soil-actions">
          <form className="soil-upload" onSubmit={onUpload}>
            <label>
              <Upload size={16} /> {t.soil_upload}
              <input name="file" type="file" accept="image/*,application/pdf" required />
            </label>
            <small className="muted">{t.soil_upload_hint}</small>
            <button className="primary" disabled={!!busy}>
              {busy ? <RefreshCw size={15} className="spin" /> : <Upload size={15} />} {busy || t.soil_upload}
            </button>
          </form>
          <button className="secondary" onClick={startManual}><Edit3 size={15} /> {t.soil_manual}</button>
        </div>
      ) : (
        <div className="soil-form">
          {extraction && <p className="notice">{t.soil_review}</p>}
          <div className="soil-form-grid">
            {FIELDS.map(f => (
              <label key={f.key} className={uncertain.some(u => u.includes(f.key.split("_")[0])) ? "uncertain" : ""}>
                <span>{t[f.label]} {f.unit && <small>({f.unit})</small>}</span>
                <input
                  type="number"
                  step={f.step}
                  min="0"
                  value={form[f.key]}
                  onChange={e => setForm({ ...form, [f.key]: e.target.value })}
                />
                {uncertain.some(u => u.includes(f.key.split("_")[0])) && <small>{t.soil_uncertain}</small>}
              </label>
            ))}
          </div>
          <div className="row-actions">
            <button className="secondary" onClick={() => { setForm(null); setExtraction(null); }}>{t.cancel}</button>
            <button className="primary" onClick={save} disabled={!!busy}>{busy ? <RefreshCw size={15} className="spin" /> : null} {t.soil_save}</button>
          </div>
        </div>
      )}

      <div className="fert-card">
        <div className="fert-head">
          <h3>{t.fert_title} <InfoTip term="fertilizers" locale={locale} /></h3>
          <label>
            {t.fert_crop}:{" "}
            <select value={crop} onChange={e => setCrop(e.target.value)}>
              {(cropOptions.length ? cropOptions.map(c => [c.crop, c.crop_name || c.crop]) : ALL_CROPS.map(c => [c, c.replace("_", " ")])).map(([id, name]) => (
                <option key={id} value={id}>{name}</option>
              ))}
            </select>
          </label>
        </div>
        {plan ? (
          <>
            <div className="fert-dose">
              <span>{t.fert_dose} <InfoTip term="rdf" locale={locale} />:</span>
              <b>N {plan.adjusted_dose_kg_ha.n}</b>
              <b>P₂O₅ {plan.adjusted_dose_kg_ha.p2o5}</b>
              <b>K₂O {plan.adjusted_dose_kg_ha.k2o}</b>
              <small className="muted">({t.fert_rdf_note.replace("{rdf}", `${plan.recommended_dose_kg_ha.n}:${plan.recommended_dose_kg_ha.p2o5}:${plan.recommended_dose_kg_ha.k2o}`)})</small>
            </div>
            <table className="fert-table">
              <thead>
                <tr><th></th><th>DAP</th><th>Urea</th><th>MOP</th></tr>
              </thead>
              <tbody>
                {plan.applications.map((a: Json) => (
                  <tr key={a.stage}>
                    <td>{a.stage === "basal" ? t.fert_basal : t.fert_topdress}</td>
                    <td>{a.dap_kg ? `${a.dap_kg} kg` : "–"}</td>
                    <td>{a.urea_kg ? `${a.urea_kg} kg` : "–"}</td>
                    <td>{a.mop_kg ? `${a.mop_kg} kg` : "–"}</td>
                  </tr>
                ))}
                <tr className="total">
                  <td>{t.fert_total} ({plan.area_ha} ha)</td>
                  {["dap", "urea", "mop"].map(p => (
                    <td key={p}>{plan.products_total[`${p}_bags`] ? `${plan.products_total[`${p}_bags`]} ${t.fert_bags} (${p === "urea" ? 45 : 50} kg)` : "–"}</td>
                  ))}
                </tr>
              </tbody>
            </table>
            {plan.rhizobium_advice && <p className="fert-note">🌱 {t.fert_rhizobium}</p>}
            {plan.organic_advice && <p className="fert-note">🍂 {t.fert_organic_low} {t.fert_organic_advice}</p>}
            <p className="muted small-text">
              {plan.soil_source === "soil_test" ? t.fert_note_test : t.fert_note_baseline} {t.fert_confirm} <span className="fert-source">{plan.source}</span>
            </p>
          </>
        ) : (
          <span className="muted">{t.loading}</span>
        )}
      </div>

      <div className="pipeline-footer-nav">
        <button className="nav-prev-btn" onClick={() => go("weather")}>← {t.weather}</button>
        <button className="nav-next-btn" onClick={() => go("crops")}>{t.crops} <ArrowRight size={15} /></button>
      </div>
    </section>
  );
}
