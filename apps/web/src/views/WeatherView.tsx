import React, { useState } from "react";
import { AlertTriangle, CloudRain, Droplets, RefreshCw, ShieldAlert, Sprout, SprayCan, Waves } from "lucide-react";
import { api } from "../api";
import { invalidate, useResource } from "../hooks";
import { Json, Locale, T, View } from "../types";
import { ErrorNote, formatDate, Loading, NeedFarm, SourceBadge, StageHeader, StatusPill } from "../components/ui";
import { operationText, riskText } from "../utils/text";

interface Props {
  t: T;
  locale: Locale;
  farm?: Json;
  go: (v: View) => void;
}

export function WeatherView({ t, locale, farm, go }: Props) {
  const ops = useResource<Json>(farm ? `/api/v1/farms/${farm.id}/weather/operational` : null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState("");
  if (!farm) return <NeedFarm t={t} go={go} />;

  const refresh = async () => {
    setRefreshing(true);
    setRefreshError("");
    try {
      await api(`/api/v1/farms/${farm.id}/evidence/refresh`, { method: "POST" });
      invalidate(`/api/v1/farms/${farm.id}`);
      await ops.reload();
    } catch (err) {
      setRefreshError((err as Error).message);
    } finally {
      setRefreshing(false);
    }
  };

  const o = ops.data;
  const maxRain = Math.max(5, ...((o?.daily || []) as Json[]).map((d) => d.rain_mm || 0));

  return (
    <section className="panel">
      <StageHeader icon={<CloudRain />} step={t("step_n", { n: 2 })} title={t("weather_title")} subtitle={`${farm.name} · ${farm.district}`} />

      <div className="toolbar-row">
        {o?.forecast_issued_at && <span className="muted">{t("forecast_updated", { time: formatDate(o.forecast_issued_at, locale, true) })}</span>}
        <SourceBadge t={t} kind="forecast" />
        <button className="secondary small" onClick={refresh} disabled={refreshing}>
          <RefreshCw size={14} className={refreshing ? "spin" : ""} /> {refreshing ? t("refreshing") : t("refresh")}
        </button>
      </div>
      {refreshError && <ErrorNote t={t} message={refreshError} />}
      {ops.loading && !o && <Loading label={t("loading_forecast")} />}
      {ops.error && <ErrorNote t={t} message={ops.error} onRetry={ops.reload} />}
      {o && !o.available && <ErrorNote t={t} message={t("forecast_not_ready")} onRetry={refresh} />}

      {o?.available && (
        <>
          <ImdBanner t={t} imd={o.imd} farm={farm} />

          <div className="window-grid">
            <WindowCard icon={<Sprout />} title={t("sowing")} status={o.sowing.status} label={t(`status_sow_${o.sowing.status}`)} text={operationText(t, "sowing", o.sowing, locale)} />
            <WindowCard icon={<SprayCan />} title={t("spraying")} status={o.spray.status} label={t(`status_spray_${o.spray.status}`)} text={operationText(t, "spray", o.spray, locale)} />
            <WindowCard icon={<Droplets />} title={t("irrigation")} status={o.irrigation.status} label={t(`status_irr_${o.irrigation.status}`)} text={operationText(t, "irrigation", o.irrigation, locale)} />
            <WindowCard icon={<Waves />} title={t("drainage")} status={o.drainage.status} label={t(`status_drain_${o.drainage.status}`)} text={operationText(t, "drainage", o.drainage, locale)} />
          </div>

          <div className="card-block">
            <h3>{t("forecast_7d")}</h3>
            <div className="forecast-table" role="table">
              {(o.daily as Json[]).map((d) => (
                <div key={d.date} className="forecast-col" role="row">
                  <span className="fc-day">{formatDate(d.date, locale)}</span>
                  <div className="fc-bar-wrap" title={`${d.rain_mm} mm`}>
                    <div className="fc-bar" style={{ height: `${Math.max(3, Math.round(((d.rain_mm || 0) / maxRain) * 100))}%` }} />
                  </div>
                  <span className="fc-rain">{(d.rain_mm ?? 0).toFixed(1)} mm</span>
                  <span className="fc-prob">{d.rain_probability ?? 0}%</span>
                  <span className="fc-temp">{Math.round(d.tmax)}° / {Math.round(d.tmin)}°</span>
                  <span className="fc-wind">{Math.round(d.wind_max_kmh)} km/h</span>
                </div>
              ))}
            </div>
            <p className="muted small-print">{t("forecast_legend")}</p>
            <div className="stat-row">
              <span>{t("rain_7d")}: <b>{o.rain_7d_mm} mm</b></span>
              <span>{t("et0_7d")}: <b>{o.et0_7d_mm} mm</b></span>
              {o.current?.temperature_2m != null && <span>{t("now")}: <b>{o.current.temperature_2m}°C · {o.current.relative_humidity_2m}%</b></span>}
              {o.temperature_extremes?.heat_days > 0 && <span className="warn-text">{t("heat_days", { n: o.temperature_extremes.heat_days })}</span>}
              {o.temperature_extremes?.cold_days > 0 && <span className="warn-text">{t("cold_days", { n: o.temperature_extremes.cold_days })}</span>}
            </div>
          </div>

          <div className="card-block">
            <h3><ShieldAlert size={18} /> {t("pest_disease_risk")}</h3>
            <p className="muted">{t("risk_disclaimer")}</p>
            <div className="risk-list">
              {(o.disease_risks as Json[]).map((r) => (
                <div key={r.id} className="risk-row">
                  <b>{t(`risk_${r.id}`)}</b>
                  <StatusPill status={r.status} label={t(`level_${r.status}`)} />
                  <span>{riskText(t, r)}</span>
                </div>
              ))}
            </div>
            <button className="link-btn" onClick={() => go("diagnose")}>{t("check_with_doctor")}</button>
          </div>
        </>
      )}

      <div className="pipeline-footer-nav">
        <button className="nav-prev-btn" onClick={() => go("home")}>{t("back_home")}</button>
        <button className="nav-next-btn" onClick={() => go("soil")}>{t("next_soil")}</button>
      </div>
    </section>
  );
}

function WindowCard({ icon, title, status, label, text }: { icon: React.ReactNode; title: string; status: string; label: string; text: string }) {
  return (
    <div className="window-card">
      <div className="window-head">{icon}<b>{title}</b><StatusPill status={status} label={label} /></div>
      <p>{text}</p>
    </div>
  );
}

function ImdBanner({ t, imd, farm }: { t: T; imd: Json; farm: Json }) {
  if (farm.country_code !== "IN") return null;
  if (imd?.status !== "available") {
    return <div className="info-banner"><AlertTriangle size={18} /> {t("imd_unavailable")}</div>;
  }
  if (imd.level) {
    return <div className={`alert-banner ${imd.level}`}><AlertTriangle size={20} /> {t(`imd_${imd.level}`, { district: farm.district })}</div>;
  }
  return <div className="info-banner ok">{t("imd_no_warning", { district: farm.district })}</div>;
}
