import React, { FormEvent, useState } from "react";
import { Camera, Microscope, UserCheck, Volume2 } from "lucide-react";
import { api, speakText, upload } from "../api";
import { useResource } from "../hooks";
import { Json, Locale, T, View } from "../types";
import { ErrorNote, formatDate, Loading, SourceBadge, StageHeader, StatusPill } from "../components/ui";

interface Props {
  t: T;
  locale: Locale;
  farm?: Json;
  go: (v: View) => void;
}

const STAGES = ["seedling", "vegetative", "flowering", "fruiting", "maturity"];
const SEVERITY_STATUS: Record<string, string> = { none: "good", mild: "fair", moderate: "limiting", severe: "blocking", unknown: "info" };
const CONFIDENCE_STATUS: Record<string, string> = { high: "good", medium: "fair", low: "limiting" };

export function DiagnoseView({ t, locale, farm }: Props) {
  const catalog = useResource<Json>(farm ? `/api/v1/catalog/crops?locale=${locale}&country_code=${farm.country_code}&state_code=${farm.state_code}` : `/api/v1/catalog/crops?locale=${locale}`);
  const cases = useResource<Json[]>(farm ? `/api/v1/farms/${farm.id}/cases` : null);
  const [crop, setCrop] = useState<string>(farm?.crop_status === "planted" ? farm.current_crop || "" : "");
  const [stage, setStage] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<Json | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError(t("photo_required"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const media = await upload(file, "crop_diagnosis");
      const path = farm ? `/api/v1/farms/${farm.id}/diagnoses` : "/api/v1/diagnoses";
      const res = await api<Json>(path, { method: "POST", body: JSON.stringify({ media_id: media.id, crop: crop || "auto-detect", crop_stage: stage || null, symptoms: notes || null, locale }) });
      setResult(res);
      cases.reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const d = result?.diagnosis;
  const readAloud = d ? [d.suspected_condition, ...(d.visible_findings || []), ...(d.safe_next_steps || [])].filter(Boolean).join(". ") : "";

  return (
    <section className="panel narrow">
      <StageHeader icon={<Microscope />} title={t("doctor_title")} subtitle={t("doctor_sub")} />
      <form onSubmit={submit} className="form-block">
        <label className="photo-drop">
          {preview ? <img src={preview} alt={t("leaf_photo")} /> : (
            <span><Camera size={32} /><b>{t("take_photo")}</b><small>{t("photo_tips")}</small></span>
          )}
          <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" hidden onChange={(e) => pick(e.target.files?.[0])} />
        </label>
        <div className="form-grid">
          <label className="field">
            <span>{t("crop")}</span>
            <select value={crop} onChange={(e) => setCrop(e.target.value)}>
              <option value="">{t("detect_from_photo")}</option>
              {(catalog.data?.crops || []).map((c: Json) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>{t("growth_stage")}</span>
            <select value={stage} onChange={(e) => setStage(e.target.value)}>
              <option value="">{t("not_sure")}</option>
              {STAGES.map((s) => <option key={s} value={s}>{t(`stage_${s}`)}</option>)}
            </select>
          </label>
        </div>
        <label className="field">
          <span>{t("what_you_see")}</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={t("what_you_see_placeholder")} maxLength={1000} rows={2} />
        </label>
        {error && <ErrorNote t={t} message={error} />}
        <button className="primary big full" type="submit" disabled={busy}>{busy ? t("checking_photo") : t("check_photo")}</button>
      </form>

      {busy && <Loading label={t("checking_photo_long")} />}

      {d && (
        <article className="diagnosis">
          <div className="diag-head">
            <div>
              <small>{t(`category_${d.category}`)} · <SourceBadge t={t} kind="ai" /></small>
              <h3>{d.suspected_condition || t("no_clear_problem")}</h3>
              {d.detected_crop && <small>{t("crop")}: {d.detected_crop}</small>}
            </div>
            <div className="diag-pills">
              <StatusPill status={CONFIDENCE_STATUS[d.confidence] || "info"} label={t(`confidence_${d.confidence}`)} />
              <StatusPill status={SEVERITY_STATUS[d.severity] || "info"} label={t(`severity_${d.severity}`)} />
              <button className="icon-btn" onClick={() => speakText(readAloud, locale).catch(() => undefined)}><Volume2 size={16} /> {t("listen")}</button>
            </div>
          </div>
          {d.image_quality === "poor" || d.image_quality === "not_crop" ? <div className="info-banner">{t(`quality_${d.image_quality}`)}</div> : null}
          <DiagList title={t("seen_in_photo")} items={d.visible_findings} />
          <DiagList title={t("possible_causes")} items={d.plausible_causes} />
          <DiagList title={t("do_now")} items={d.safe_next_steps} strong />
          <DiagList title={t("prevent_next_time")} items={d.prevention} />
          {d.uncertainty_reasons?.length > 0 && <DiagList title={t("why_not_certain")} items={d.uncertainty_reasons} />}
          {result?.expert_case ? (
            <div className="expert-note"><UserCheck size={18} /> {t("sent_to_expert")}</div>
          ) : (
            <p className="small-print">{t("doctor_disclaimer")}</p>
          )}
        </article>
      )}

      {farm && (cases.data?.length || 0) > 0 && (
        <div className="card-block">
          <h3>{t("my_expert_cases")}</h3>
          <ul className="case-list">
            {(cases.data as Json[]).map((c) => (
              <li key={c.id}>
                <span>{formatDate(c.created_at, locale)}{c.suspected_condition ? ` · ${c.suspected_condition}` : ""}</span>
                <StatusPill status={c.status === "resolved" ? "good" : "fair"} label={t(`case_${c.status}`)} />
                {c.review_text ? <p><b>{t("expert_reply")}:</b> {c.review_text}</p> : <p className="muted">{t("waiting_for_expert")}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function DiagList({ title, items, strong = false }: { title: string; items?: string[]; strong?: boolean }) {
  if (!items?.length) return null;
  return (
    <div className={`diag-list ${strong ? "strong" : ""}`}>
      <h4>{title}</h4>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}
