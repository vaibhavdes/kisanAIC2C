import React, { useState } from "react";
import { ChevronDown, ChevronUp, Globe2, Leaf, RefreshCw, Sprout } from "lucide-react";
import { useCropName, useResource } from "../hooks";
import { Json, Locale, T, View } from "../types";
import { ErrorNote, formatDate, Loading, NeedFarm, pct, SourceBadge, StageHeader, StatusPill } from "../components/ui";
import { factorText, rejectionText } from "../utils/text";

interface Props {
  t: T;
  locale: Locale;
  farm?: Json;
  go: (v: View) => void;
}

export function CropRecView({ t, locale, farm, go }: Props) {
  const recs = useResource<Json>(farm ? `/api/v1/farms/${farm.id}/crop-recommendations?locale=${locale}` : null);
  const [showOthers, setShowOthers] = useState(false);
  const cropName = useCropName(locale);
  if (!farm) return <NeedFarm t={t} go={go} />;
  const r = recs.data;

  return (
    <section className="panel">
      <StageHeader icon={<Sprout />} step={t("step_n", { n: 4 })} title={t("crops_title")} subtitle={t("crops_sub")} />
      <div className="toolbar-row">
        <button className="secondary small" onClick={recs.reload} disabled={recs.loading}>
          <RefreshCw size={14} className={recs.loading ? "spin" : ""} /> {t("refresh")}
        </button>
      </div>
      {recs.loading && !r && <Loading label={t("loading_crops")} />}
      {recs.error && <ErrorNote t={t} message={recs.error} onRetry={recs.reload} />}

      {r && (
        <>
          <ContextBar t={t} r={r} locale={locale} />
          {farm.crop_status === "planted" && <div className="info-banner">{t("crops_planted_note", { crop: cropName(farm.current_crop) })}</div>}

          <h3 className="group-title">{t("sow_now")} <span className="count">{r.sow_now.length}</span></h3>
          {r.sow_now.length ? (
            <div className="crop-grid">{r.sow_now.map((o: Json, i: number) => <CropCard key={o.crop} t={t} o={o} locale={locale} highlight={i === 0} />)}</div>
          ) : <p className="muted">{t("nothing_to_sow_now")}</p>}

          {r.upcoming.length > 0 && (
            <>
              <h3 className="group-title">{t("sow_soon")} <span className="count">{r.upcoming.length}</span></h3>
              <div className="crop-grid">{r.upcoming.map((o: Json) => <CropCard key={o.crop} t={t} o={o} locale={locale} />)}</div>
            </>
          )}

          {r.not_suitable.length > 0 && (
            <div className="others">
              <button className="link-btn" onClick={() => setShowOthers(!showOthers)}>
                {showOthers ? <ChevronUp size={16} /> : <ChevronDown size={16} />} {t("not_now_or_unsuitable", { n: r.not_suitable.length })}
              </button>
              {showOthers && (
                <ul className="reject-list">
                  {r.not_suitable.map((o: Json) => (
                    <li key={o.crop}>
                      <b>{o.crop_name}</b>
                      <span>{o.rejection_codes.map((c: string) => {
                        const next = o.factors.find((f: Json) => f.id === "sowing_window")?.params?.next_start;
                        return c === "not_in_season" && next ? t("rej_next_window", { date: formatDate(next, locale) }) : rejectionText(t, c);
                      }).join(" · ")}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="card-block subtle">
            <h4>{t("data_used")}</h4>
            <div className="source-chips">
              {(r.data_sources as Json[]).map((s) => (
                <span key={s.id} className={`source-chip st-${s.status}`}>
                  {s.name} · {t(`ds_status_${s.status}`)}{s.as_of ? ` (${s.as_of})` : ""}
                </span>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="pipeline-footer-nav">
        <button className="nav-prev-btn" onClick={() => go("soil")}>{t("back")}</button>
        <button className="nav-next-btn" onClick={() => go("advice")}>{t("next_plan")}</button>
      </div>
    </section>
  );
}

function ContextBar({ t, r, locale }: { t: T; r: Json; locale: Locale }) {
  const c = r.context || {};
  return (
    <div className="context-bar">
      {r.knowledge_mode === "regional_pack" ? (
        <span className="context-pack"><Leaf size={14} /> {t("using_pack", { name: r.pack.name, version: r.pack.pack_version })}
          {r.pack.origin === "imported" && <em> · {t("imported_from", { node: r.pack.origin_node })}</em>}
          {r.pack.review_status !== "reviewed" && <em> · {t("pack_pending_review")}</em>}
        </span>
      ) : (
        <span className="context-pack global"><Globe2 size={14} /> {t("using_global")}</span>
      )}
      <span>{t("date_label")}: <b>{formatDate(c.today, locale)}</b>{c.season_now ? ` · ${t(`season_${c.season_now}`)}` : ""}</span>
      <span>{t("water_source")}: <b>{t(`water_${c.water_access}`)}</b></span>
      {c.soil_texture && <span>{t("texture")}: <b>{t(`texture_${c.soil_texture}`)}</b></span>}
      {c.soil_ph != null && <span>pH <b>{Number(c.soil_ph).toFixed(1)}</b> <SourceBadge t={t} kind={c.soil_ph_source === "measured" ? "measured" : "estimated"} /></span>}
      {c.previous_crop_name && <span>{t("previous_crop")}: <b>{c.previous_crop_name}</b></span>}
      {c.groundwater_category && c.groundwater_category !== "unknown" && <span>{t("groundwater")}: <b>{t(`gw_${c.groundwater_category}`)}</b></span>}
      {c.annual_rain_mm != null && <span>{t("annual_rain")}: <b>{c.annual_rain_mm} mm</b></span>}
      {(r.notes as string[]).length > 0 && <p className="context-note">{r.knowledge_mode === "global_baseline" ? t("global_note") : t("pack_note")}</p>}
    </div>
  );
}

function CropCard({ t, o, locale, highlight = false }: { t: T; o: Json; locale: Locale; highlight?: boolean }) {
  const [open, setOpen] = useState(highlight);
  const w = o.sowing;
  return (
    <article className={`crop-card ${highlight ? "best" : ""}`}>
      <header>
        <div>
          <h4>{o.crop_name}</h4>
          <small>{o.scientific_name}</small>
        </div>
        <div className="scores">
          <span className="score" title={t("fit_hint")}>{t("fit")} <b>{pct(o.suitability)}</b></span>
          <span className="score regen" title={t("regen_hint")}>{t("regen")} <b>{pct(o.regenerative_score)}</b></span>
        </div>
      </header>
      {w && (
        <p className="window-line">
          {w.status === "open" ? t("window_open_until", { date: formatDate(w.end, locale) }) : t("window_opens", { date: formatDate(w.start, locale), days: w.days_until_start })}
          {w.label && locale === "en-IN" ? ` · ${w.label}` : ""}
          {w.irrigation_required ? ` · ${t("needs_irrigation")}` : ""}
        </p>
      )}
      {o.water_need_mm != null && (
        <p className="water-line">{t("water_line", { need: o.water_need_mm, available: o.water_available_mm })}
          {o.irrigation_gap_mm > 0 ? ` · ${t("water_gap", { gap: o.irrigation_gap_mm })}` : ""}</p>
      )}
      {o.practices?.length > 0 && (
        <div className="practice-chips">{o.practices.map((p: Json) => <span key={p.id} className="practice-chip">{p.name}</span>)}</div>
      )}
      <button className="link-btn" onClick={() => setOpen(!open)}>{open ? t("hide_reasons") : t("show_reasons")}</button>
      {open && (
        <ul className="factor-list">
          {(o.factors as Json[]).map((f) => (
            <li key={f.id} className={`factor f-${f.status}`}>
              <StatusPill status={f.status} label={t(`factor_${f.id}`)} />
              <span>{factorText(t, f, locale)}</span>
              <SourceBadge t={t} kind={f.source} />
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
