import { CloudRain, MapPin, Activity, RefreshCw, AlertTriangle, CheckCircle2 } from "lucide-react";
import { View, Locale, Json } from "../types";
import { parseWeatherFromEvidence, getImdWarningLevel } from "../utils/weather";
import { InfoTip, ListenButton } from "../components/InfoTip";

// Status from the API -> existing tag colour classes.
const TAG_CLASS: Record<string, string> = {
  ready: "safe", safe: "safe", not_needed: "safe", low: "safe", normal: "safe",
  marginal: "caution", caution: "caution", monitor: "caution", moderate: "moderate", conserve: "caution", cold: "caution",
  wait: "avoid", avoid: "avoid", irrigate: "avoid", high: "high", unknown: "hold",
};

export interface WeatherViewProps {
  t: Record<string, string>;
  locale: Locale;
  farm?: Json;
  evidence: Json[];
  operational: Json | null;
  satMap: Json | null;
  loadingWeather: boolean;
  refreshEvidence: () => Promise<void>;
  go: (v: View) => void;
}

export function WeatherView({
  t,
  locale,
  farm,
  evidence,
  operational,
  satMap,
  loadingWeather,
  refreshEvidence,
  go
}: WeatherViewProps) {
  if (!farm) {
    return (
      <section className="panel" style={{ textAlign: "center", padding: "60px 20px" }}>
        <MapPin size={48} color="var(--lime-500)" style={{ marginBottom: "12px" }} />
        <h2>{t.add_farm_first}</h2>
        <button className="primary" onClick={() => go("farm")} style={{ marginTop: "16px" }}>
          {t.start}
        </button>
      </section>
    );
  }

  const weatherData = parseWeatherFromEvidence(evidence, locale);
  const maxDailyMm = Math.max(1, ...((operational?.daily as Json[]) || []).map((d: Json) => d.rain_mm || 0));
  const imdAlert = getImdWarningLevel(evidence, locale);


  const weatherDateVal = operational?.fetched_at || evidence.find(e => e.kind === "weather_forecast")?.fetched_at;
  const weatherObsDate = weatherDateVal
    ? new Date(weatherDateVal as string).toLocaleString(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : t.forecast_pending;
  const daily: Json[] = operational?.daily || [];
  const statusLabel = (status?: string) => t[`st_${status || "unknown"}`] || status || "";
  const fmt = (value: unknown, digits = 0) => (typeof value === "number" ? value.toFixed(digits) : "--");

  return (
    <section className="panel">
      <div className="section-title">
        <CloudRain />
        <div>
          <small>{farm.name} · {farm.district}</small>
          <h2>{t.weather}</h2>
        </div>
      </div>

      {/* Observation Timestamps Strip */}
      <div className="evidence-timestamp-strip">
        <span style={{ fontWeight: 700, color: "var(--green-950)", display: "flex", alignItems: "center", gap: 5 }}>
          <Activity size={14} />
          {t.evidence_strip_title}:
        </span>
        <span className="timestamp-badge weather" title="Weather">
          🌦️ {t.latest_weather_obs}: {weatherObsDate}
        </span>
        <span className="timestamp-badge sat" title="Satellite photo date">
          🛰️ Sentinel-2: {satMap ? (satMap.scene_date || t.scene_pending) : t.loading}
        </span>
        <button className="timestamp-badge soil" onClick={() => go("soil")}>
          🌱 {t.soil_profile_title}: {farm.soil_type && farm.soil_type !== "unknown" ? (t[`soil_${farm.soil_type}`] || farm.soil_type).replace(/^\S+\s/, "") : "--"} →
        </button>
      </div>

      {/* Dynamic Weather Dashboard */}
      <div className="weather-dashboard">
        <div className="weather-metric-card">
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
              <span className="weather-live-indicator">
                <span className="weather-live-dot" />
                {t.weather_updated} {weatherObsDate} · {farm.district}
              </span>
              <button
                className="secondary"
                disabled={loadingWeather}
                style={{ padding: "6px 12px", fontSize: "12px", borderRadius: "8px" }}
                onClick={refreshEvidence}
              >
                <RefreshCw size={13} className={loadingWeather ? "spin" : ""} />
                {t.refresh}
              </button>
            </div>

            {loadingWeather ? (
              <div style={{ padding: "28px 0", textAlign: "center" }}>
                <RefreshCw className="spin" size={24} style={{ marginBottom: "8px" }} />
                <div style={{ fontSize: "14px", color: "#cbd8cf" }}>{t.forecast_pending}</div>
              </div>
            ) : (
              <div className="weather-temp-main">
                <h2>{weatherData.temp || (weatherData.hasData ? "--" : "--")}</h2>
                <div>
                  <span style={{ fontSize: "15px", color: "#cbd8cf", display: "block" }}>
                    {t.rainfall_today}: <strong>{weatherData.hasData ? (weatherData.rainfall || "0.0 mm") : "--"}</strong>
                  </span>
                  <span style={{ fontSize: "12px", color: weatherData.hasData ? "var(--lime-400)" : "var(--muted)" }}>
                    {weatherData.hasData ? "Open-Meteo" : t.forecast_pending}
                  </span>
                </div>
              </div>
            )}
          </div>

          <div className="weather-details-grid">
            <div>
              <small>{t.wind_speed}</small>
              <strong>{weatherData.wind || (weatherData.hasData ? "0 km/h" : "--")}</strong>
            </div>
            <div>
              <small>{t.humidity}</small>
              <strong>{weatherData.humidity || (weatherData.hasData ? "N/A" : "--")}</strong>
            </div>
            <div>
              <small>{t.forecast_7d}</small>
              <strong>{operational?.has_forecast ? `${fmt(operational.rain_7d_total_mm, 1)} mm` : "--"}</strong>
            </div>
            <div>
              <small>{t.past_7d_rain}</small>
              <strong>{operational?.past_7d_rain_mm != null ? `${fmt(operational.past_7d_rain_mm, 1)} mm` : "--"}</strong>
            </div>
            <div>
              <small>{t.water_balance} <InfoTip term="water_balance" locale={locale} /></small>
              <strong>{operational?.water_balance_7d_mm != null ? `${operational.water_balance_7d_mm > 0 ? "+" : ""}${fmt(operational.water_balance_7d_mm)} mm` : "--"}</strong>
            </div>
            <div>
              <small>{t.soil_moisture_label} <InfoTip term="soil_moisture" locale={locale} /></small>
              <strong>
                {operational?.soil_moisture?.root_available_pct != null
                  ? `${operational.soil_moisture.top_available_pct}% / ${operational.soil_moisture.root_available_pct}%`
                  : "--"}
              </strong>
              <small>{t.top_soil} / {t.root_zone}</small>
            </div>
          </div>
        </div>

        <div className="forecast-card">
          <h4>
            <span>{t.forecast_7d} ({farm.district})</span>
            <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600 }}>
              {operational?.has_forecast ? `${fmt(operational.rain_7d_total_mm, 1)} mm` : t.forecast_pending}
            </span>
          </h4>

          {loadingWeather ? (
            <div style={{ display: "grid", placeItems: "center", height: "140px", color: "var(--muted)" }}>
              <RefreshCw className="spin" size={20} />
            </div>
          ) : daily.length > 0 ? (
            <div className="forecast-bars">
              {daily.map(d => {
                const mm = d.rain_mm || 0;
                const heightPct = Math.max(12, Math.round((mm / maxDailyMm) * 85));
                return (
                  <div key={d.date} className="forecast-day-col">
                    <span className="forecast-day-rain">{mm.toFixed(1)} mm<br />{fmt(d.rain_prob)}%</span>
                    <div
                      className={`forecast-bar-fill ${mm > 0 ? "rainy" : ""}`}
                      style={{ height: `${heightPct}%` }}
                      title={`${d.label}: ${mm} mm (${fmt(d.rain_prob)}%)`}
                    />
                    <span>{d.label}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ textAlign: "center", padding: "30px 16px", color: "var(--muted)" }}>
              <p style={{ margin: "0 0 12px", fontSize: "14px" }}>
                {t.forecast_pending}
              </p>
              <button
                className="secondary"
                disabled={loadingWeather}
                style={{ padding: "8px 16px", fontSize: "13px", display: "inline-flex", alignItems: "center", gap: "6px" }}
                onClick={refreshEvidence}
              >
                <RefreshCw size={14} className={loadingWeather ? "spin" : ""} />
                <span>{t.refresh}</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Dynamic IMD District Alert Banner */}
      {imdAlert.level ? (
        <div className={`alert-banner ${imdAlert.level}`}>
          <AlertTriangle size={24} />
          <div>
            <div><strong>IMD District Weather Alert ({farm.district})</strong></div>
            <small>{imdAlert.msg} Source: India Meteorological Department (api.imd.gov.in)</small>
          </div>
        </div>
      ) : evidence.some(e => e.provider === "imd" && e.mode === "live") && (
        <div className="alert-banner" style={{ background: "#f0f8ec", color: "#225934", border: "1px solid #cce5c4" }}>
          <CheckCircle2 size={20} color="var(--green-700)" />
          <div>
            <strong>{t.normal_weather + farm.district}</strong>
            <small>{t.normal_weather_desc}</small>
          </div>
        </div>
      )}

      {/* Farm operation windows derived from the 7-day forecast */}
      {operational && (
        <div className="agri-action-window-grid">
          {([
            ["sowing", "🌱", t.sowing_window, "sowing"],
            ["spraying", "🧪", t.spraying_window, "spray"],
            ["irrigation", "💧", t.irrigation_advisory, "water_balance"],
            ["drainage", "🌊", t.drainage_alert, ""],
            ["temperature", "🌡️", t.temperature_window, ""],
            ["disease", "🍂", t.disease_window, "disease"],
          ] as const).map(([key, icon, title, term]) => {
            const card = (operational[key] || {}) as Json;
            return (
              <div className="agri-action-card" key={key}>
                <div className="agri-action-card-head">
                  <span>{icon} {title} {term && <InfoTip term={term} locale={locale} />}</span>
                  <span className={`agri-tag ${TAG_CLASS[card.status as string] || "caution"}`}>{statusLabel(card.status)}</span>
                </div>
                <div>
                  <strong style={{ fontSize: "13px", color: "var(--green-950)", display: "block", marginBottom: 4 }}>
                    {card.summary}
                  </strong>
                  {card.details && <p>{card.details}</p>}
                  <ListenButton text={[card.summary, card.details].filter(Boolean).join(" ")} locale={locale} label={t.listen} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Day-by-day table: every number behind the advice above */}
      {daily.length > 0 && (
        <div className="farm-forecast-table-wrap">
          <h4>{t.farm_forecast_title}</h4>
          <table className="farm-forecast-table">
            <thead>
              <tr>
                <th>{t.col_day}</th>
                <th>{t.col_rain}</th>
                <th>{t.col_chance} <InfoTip term="rain_prob" locale={locale} /></th>
                <th>{t.col_temp}</th>
                <th>{t.col_wind}</th>
                <th>{t.col_et0} <InfoTip term="et0" locale={locale} /></th>
                <th>{t.col_spray} <InfoTip term="spray" locale={locale} /></th>
              </tr>
            </thead>
            <tbody>
              {daily.map(d => (
                <tr key={d.date}>
                  <td>{d.label}</td>
                  <td>{fmt(d.rain_mm, 1)} mm</td>
                  <td>{fmt(d.rain_prob)}%</td>
                  <td>{fmt(d.temp_max)}° / {fmt(d.temp_min)}°</td>
                  <td>{fmt(d.wind_max)} km/h</td>
                  <td>{fmt(d.et0, 1)} mm</td>
                  <td><span className={`agri-tag ${TAG_CLASS[d.spray as string]}`}>{statusLabel(d.spray)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <small>{t.weather_source_note}</small>
        </div>
      )}

      {/* Verified Provenance Compact Pill (Hover for source details) */}
      <div
        className="provenance-compact-pill"
        title="Open-Meteo forecast · IMD warnings (when available) · Sentinel-2 satellite"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "8px",
          padding: "8px 16px",
          borderRadius: "20px",
          background: "#f4f7ee",
          border: "1px solid var(--line)",
          fontSize: "12px",
          color: "var(--green-900)",
          margin: "18px 0 10px",
          cursor: "help"
        }}
      >
        <span style={{ fontSize: "15px" }}>🛡️</span>
        <span style={{ fontWeight: 600 }}>{t.sources_badge}</span>
        <span style={{ color: "var(--muted)", fontSize: "11px" }}>ⓘ Open-Meteo · IMD · Sentinel-2</span>
      </div>

      {/* Pipeline Navigation Footer */}
      <div className="pipeline-footer-nav">
        <button className="nav-prev-btn" onClick={() => go("farm")}>
          {t.btn_back_farm}
        </button>
        <button className="nav-next-btn" onClick={() => go("soil")}>
          {t.btn_proceed_soil}
        </button>
      </div>
    </section>
  );
}
