import React, { useState } from "react";
import { CloudRain, Droplets, ExternalLink, FlaskConical, Globe2, MapPin, Microscope, Pencil, Share2, SprayCan, Sprout, Trash2, Volume2 } from "lucide-react";
import { speakText } from "../api";
import { useCropName, useResource } from "../hooks";
import { Json, Locale, T, View } from "../types";
import { ErrorNote, Loading, StatusPill } from "../components/ui";
import { operationText, riskText } from "../utils/text";

interface HomeViewProps {
  t: T;
  locale: Locale;
  farm?: Json;
  farms: Json[];
  loaded: boolean;
  go: (v: View) => void;
  onEdit: (farm: Json) => void;
  onDelete: (id: string) => Promise<void>;
}

export function HomeView({ t, locale, farm, farms, loaded, go, onEdit, onDelete }: HomeViewProps) {
  if (!loaded) return <Loading label={t("loading")} />;
  return (
    <>
      {farm ? <TodayCard t={t} locale={locale} farm={farm} go={go} onEdit={onEdit} onDelete={onDelete} /> : <Welcome t={t} go={go} />}
      {farms.length > 0 && (
        <div className="home-add-farm">
          <button className="secondary" onClick={() => go("farm")}><MapPin size={16} /> {t("add_another_farm")}</button>
        </div>
      )}
      <HowItWorks t={t} />
      <NetworkNodes t={t} locale={locale} />
      <DataSources t={t} />
    </>
  );
}

function Welcome({ t, go }: { t: T; go: (v: View) => void }) {
  return (
    <section className="hero">
      <div className="eyebrow">{t("hero_eyebrow")}</div>
      <h1>{t("hero_title")}</h1>
      <p>{t("hero_sub")}</p>
      <div className="cta-row">
        <button className="primary big" onClick={() => go("farm")}><MapPin size={20} /> {t("hero_cta")}</button>
        <button className="secondary" onClick={() => go("diagnose")}><Microscope size={18} /> {t("hero_doctor_cta")}</button>
      </div>
      <p className="privacy-note">{t("privacy_note")}</p>
    </section>
  );
}

function TodayCard({ t, locale, farm, go, onEdit, onDelete }: { t: T; locale: Locale; farm: Json; go: (v: View) => void; onEdit: (f: Json) => void; onDelete: (id: string) => Promise<void> }) {
  const ops = useResource<Json>(`/api/v1/farms/${farm.id}/weather/operational`);
  const recs = useResource<Json>(farm.crop_status === "planted" ? null : `/api/v1/farms/${farm.id}/crop-recommendations?locale=${locale}`);
  const cropName = useCropName(locale);
  const [deleting, setDeleting] = useState(false);
  const o = ops.data;
  const topCrop = recs.data?.sow_now?.[0] || recs.data?.upcoming?.[0];
  const risks = (o?.disease_risks || []).filter((r: Json) => r.status !== "low");

  const lines: string[] = [];
  if (o?.available) {
    if (farm.crop_status !== "planted") lines.push(operationText(t, "sowing", o.sowing, locale));
    lines.push(operationText(t, "spray", o.spray, locale));
    lines.push(operationText(t, "irrigation", o.irrigation, locale));
    if (o.drainage?.status !== "normal") lines.push(operationText(t, "drainage", o.drainage, locale));
    risks.forEach((r: Json) => lines.push(`${t(`risk_${r.id}`)}: ${riskText(t, r)}`));
  }
  if (topCrop) lines.push(t("today_best_crop", { crop: topCrop.crop_name }));

  const remove = async () => {
    if (!window.confirm(t("confirm_delete_farm", { name: farm.name }))) return;
    setDeleting(true);
    try {
      await onDelete(farm.id);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <section className="today-card">
      <div className="today-head">
        <div>
          <div className="eyebrow">{t("today_on_farm")}</div>
          <h1>{farm.name}</h1>
          <p className="farm-meta">
            <MapPin size={14} /> {[farm.village, farm.district, farm.state_name].filter(Boolean).join(", ")}
            <span>· {farm.area_value} {t(`unit_${farm.area_unit}`)}</span>
            <span>· {t(`water_${farm.water_access}`)}</span>
            {farm.current_crop && <span>· {t("standing_crop")}: {cropName(farm.current_crop)}</span>}
          </p>
        </div>
        <div className="today-tools">
          {lines.length > 0 && (
            <button className="icon-btn" onClick={() => speakText(lines.join(". "), locale).catch(() => undefined)} aria-label={t("listen")}>
              <Volume2 size={18} /> <span>{t("listen")}</span>
            </button>
          )}
          <button className="icon-btn" onClick={() => onEdit(farm)} aria-label={t("edit_farm")}><Pencil size={16} /></button>
          <button className="icon-btn danger" onClick={remove} disabled={deleting} aria-label={t("delete_farm")}><Trash2 size={16} /></button>
        </div>
      </div>

      {ops.loading && !o && <Loading label={t("loading_forecast")} />}
      {ops.error && <ErrorNote t={t} message={ops.error} onRetry={ops.reload} />}
      {o && !o.available && <p className="muted">{t("forecast_not_ready")}</p>}
      {o?.available && (
        <div className="today-grid">
          {farm.crop_status !== "planted" && (
            <TodayItem icon={<Sprout size={20} />} title={t("sowing")} status={o.sowing.status} label={t(`status_sow_${o.sowing.status}`)}
                       text={operationText(t, "sowing", o.sowing, locale)} />
          )}
          <TodayItem icon={<SprayCan size={20} />} title={t("spraying")} status={o.spray.status} label={t(`status_spray_${o.spray.status}`)}
                     text={operationText(t, "spray", o.spray, locale)} />
          <TodayItem icon={<Droplets size={20} />} title={t("irrigation")} status={o.irrigation.status} label={t(`status_irr_${o.irrigation.status}`)}
                     text={operationText(t, "irrigation", o.irrigation, locale)} />
          <TodayItem icon={<CloudRain size={20} />} title={t("rain_7d")} status={o.drainage.status} label={`${o.rain_7d_mm} mm`}
                     text={operationText(t, "drainage", o.drainage, locale)} />
        </div>
      )}
      {risks.length > 0 && (
        <div className="risk-strip">
          {risks.map((r: Json) => (
            <span key={r.id} className={`risk-chip risk-${r.status}`}>{t(`risk_${r.id}`)} · {t(`level_${r.status}`)}</span>
          ))}
          <button className="link-btn" onClick={() => go("diagnose")}>{t("check_with_doctor")}</button>
        </div>
      )}
      {topCrop && (
        <div className="today-crop">
          <Sprout size={18} />
          <span>{t(recs.data?.sow_now?.length ? "today_sow_now" : "today_sow_soon", { crop: topCrop.crop_name })}</span>
          <button className="link-btn" onClick={() => go("crops")}>{t("see_all_crops")}</button>
        </div>
      )}
      <div className="today-actions">
        <button className="primary" onClick={() => go("advice")}>{t("get_field_plan")}</button>
        <button className="secondary" onClick={() => go("weather")}><CloudRain size={16} /> {t("weather_details")}</button>
        <button className="secondary" onClick={() => go("soil")}><FlaskConical size={16} /> {t("soil_card")}</button>
        <button className="secondary" onClick={() => go("diagnose")}><Microscope size={16} /> {t("plant_doctor")}</button>
      </div>
    </section>
  );
}

function TodayItem({ icon, title, status, label, text }: { icon: React.ReactNode; title: string; status: string; label: string; text: string }) {
  return (
    <div className="today-item">
      <div className="today-item-head">{icon}<b>{title}</b><StatusPill status={status} label={label} /></div>
      <p>{text}</p>
    </div>
  );
}

function HowItWorks({ t }: { t: T }) {
  const items = [
    { icon: <MapPin size={22} />, title: t("how_1_title"), text: t("how_1_text") },
    { icon: <CloudRain size={22} />, title: t("how_2_title"), text: t("how_2_text") },
    { icon: <Sprout size={22} />, title: t("how_3_title"), text: t("how_3_text") },
    { icon: <Share2 size={22} />, title: t("how_4_title"), text: t("how_4_text") },
  ];
  return (
    <section className="home-section">
      <h2>{t("how_title")}</h2>
      <div className="features-grid">
        {items.map((item) => (
          <div key={item.title} className="feature-card">
            <div className="feature-icon-box">{item.icon}</div>
            <h3>{item.title}</h3>
            <p>{item.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

const SOURCES = [
  { name: "Open-Meteo", key: "ds_openmeteo" },
  { name: "India Meteorological Department (IMD)", key: "ds_imd" },
  { name: "Copernicus Sentinel-2 · Google Earth Engine", key: "ds_sentinel" },
  { name: "ISRIC SoilGrids 2.0 · ESA WorldCover", key: "ds_soilgrids" },
  { name: "FAO EcoCrop", key: "ds_ecocrop" },
  { name: "State agricultural university packages of practices", key: "ds_packs" },
  { name: "Soil Health Card (your own test)", key: "ds_shc" },
  { name: "Google Gemini (Vertex AI, India region)", key: "ds_gemini" },
];

function DataSources({ t }: { t: T }) {
  return (
    <section className="home-section data-sources">
      <h2>{t("ds_title")}</h2>
      <p className="muted">{t("ds_sub")}</p>
      <ul className="source-list">
        {SOURCES.map((s) => (
          <li key={s.key}><b>{s.name}</b><span>{t(s.key)}</span></li>
        ))}
      </ul>
    </section>
  );
}

/** Other AgriN nodes (states and countries) - each card opens that node's app. */
function NetworkNodes({ t, locale }: { t: T; locale: Locale }) {
  const network = useResource<Json>("/api/v1/network/nodes");
  const nodes = (network.data?.nodes || []) as Json[];
  if (nodes.length < 2) return null;
  const names = (type: "region" | "language") => {
    try {
      return new Intl.DisplayNames([locale, "en"], { type });
    } catch {
      return null;
    }
  };
  const countries = names("region");
  const languages = names("language");
  return (
    <section className="card-block network-nodes">
      <h3><Globe2 size={18} /> {t("net_title")}</h3>
      <p className="muted">{t("net_sub")}</p>
      <div className="node-grid">
        {nodes.map((n) => {
          const body = (
            <>
              <div className="block-head">
                <b>{n.label}</b>
                {n.current ? <span className="status-pill tone-good">{t("net_this_node")}</span>
                  : n.status !== "online" && <span className="status-pill tone-warn">{t("net_offline")}</span>}
              </div>
              <small>{countries?.of(n.country_code) || n.country_code} · {(n.subdivisions || []).join(", ")}</small>
              <small className="muted">{(n.languages || []).map((l: string) => languages?.of(l.split("-")[0]) || l).join(" · ")}</small>
              {!n.current && n.url && <span className="node-open">{t("net_open")} <ExternalLink size={14} /></span>}
            </>
          );
          return n.current || !n.url || n.status !== "online"
            ? <div key={n.node_id || n.url} className={`node-card ${n.current ? "current" : ""}`}>{body}</div>
            : <a key={n.node_id || n.url} className="node-card" href={n.url} target="_blank" rel="noopener noreferrer">{body}</a>;
        })}
      </div>
    </section>
  );
}
