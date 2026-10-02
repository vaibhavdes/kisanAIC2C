import React, { useState } from "react";
import {
  Activity, ArrowRight, CloudRain, Droplets, FlaskConical, MapPin, Microscope, Plus, RefreshCw,
  Sprout, Thermometer, Trash2, Wind
} from "lucide-react";
import { Json, Locale, TranslationDictionary, View } from "../types";
import { parseWeatherFromEvidence } from "../utils/weather";
import { InfoTip, ListenButton } from "../components/InfoTip";
import { PlatformInfo } from "../components/PlatformInfo";

interface HomeViewProps {
  t: TranslationDictionary;
  locale: Locale;
  farms: Json[];
  selected: string;
  setSelected: (id: string) => void;
  go: (v: View) => void;
  onDeleteFarm?: (id: string) => Promise<void>;
  onNewFarm: () => void;
  evidence: Json[];
  operational: Json | null;
  cropRecs: Json | null;
  loadingWeather: boolean;
  loadingRecs: boolean;
}

// Status from the API -> tag colour class (same mapping as the weather view).
const TAG_CLASS: Record<string, string> = {
  ready: "safe", safe: "safe", not_needed: "safe", low: "safe", normal: "safe",
  marginal: "caution", caution: "caution", monitor: "caution", moderate: "moderate", conserve: "caution", cold: "caution",
  wait: "avoid", avoid: "avoid", irrigate: "avoid", high: "high", unknown: "hold",
};

// Open-Meteo (WMO) weather code -> icon; the number alone means nothing to a farmer.
const weatherIcon = (code?: number | null) => {
  if (code == null) return "🌡️";
  if (code === 0) return "☀️";
  if (code <= 2) return "🌤️";
  if (code === 3) return "☁️";
  if (code <= 48) return "🌫️";
  if (code >= 95) return "⛈️";
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "❄️";
  return "🌧️";
};

export const HomeView: React.FC<HomeViewProps> = ({
  t, locale, farms, selected, setSelected, go, onDeleteFarm, onNewFarm, evidence, operational, cropRecs, loadingWeather, loadingRecs
}) => {
  const farm = farms.find(f => f.id === selected) || farms[0];
  const [showFarms, setShowFarms] = useState(false);

  if (!farm) {
    return (
      <>
      <section className="home-empty">
        <h1>{t.home_no_farm_title}</h1>
        <p>{t.home_no_farm_desc}</p>
        <button className="primary" onClick={() => go("farm")}>
          <MapPin size={18} />
          <span>{t.home_add_farm}</span>
          <ArrowRight size={18} />
        </button>
        <ul className="feature-chips">
          <li><CloudRain size={15} />{t.feat_weather}</li>
          <li><Sprout size={15} />{t.feat_crops}</li>
          <li><FlaskConical size={15} />{t.feat_soil}</li>
          <li><Microscope size={15} />{t.feat_doctor}</li>
          <li>🎙️ {t.feat_voice}</li>
        </ul>
        <button className="link-btn" onClick={() => go("diagnose")}>{t.plant_doctor} →</button>
        </section>
        <div className="home-info"><PlatformInfo locale={locale} go={go} hasFarm={false} /></div>
      </>
    );
  }

  const now = parseWeatherFromEvidence(evidence, locale);
  const week: Json[] = operational?.daily || [];
  const today: Json | undefined = week[0];
  const statusLabel = (status?: string) => t[`st_${status || "unknown"}`] || status || "";
  const cards: Array<[string, string, string, string]> = [
    ["sowing", "🌱", t.sowing_window, "sowing"],
    ["spraying", "🧪", t.spraying_window, "spray"],
    ["irrigation", "💧", t.irrigation_advisory, "water_balance"],
    ["disease", "🍂", t.disease_window, "disease"],
  ];
  // Everything on the advice card as one text, for farmers who prefer to listen.
  const todayText = cards
    .map(([key, , title]) => (operational?.[key]?.summary ? `${title}: ${operational[key].summary}` : ""))
    .filter(Boolean)
    .join(" ");
  const topCrops: Json[] = (cropRecs?.recommendations || []).slice(0, 3);
  const seasonName = cropRecs?.season ? String(cropRecs.season).replace(/^./, c => c.toUpperCase()) : "";

  return (
    <section className="home-today">
      <div className="home-farm-bar">
        <div>
          <small>{t.home_today}</small>
          <h2>{farm.name}</h2>
          <span className="muted">
            <MapPin size={13} /> {[farm.village, farm.district, farm.state_name].filter(Boolean).join(", ")} · {farm.area_value} {farm.area_unit}
            {farm.soil_type && farm.soil_type !== "unknown" ? ` · ${(t[`soil_${farm.soil_type}`] || farm.soil_type).replace(/^\S+\s/, "")}` : ""}
          </span>
        </div>
        <div className="home-farm-actions">
          <button className="secondary small" onClick={() => setShowFarms(!showFarms)} aria-expanded={showFarms}>
            {t.home_your_farms} ({farms.length}) {showFarms ? "▴" : "▾"}
          </button>
          <button className="secondary small" onClick={onNewFarm}><Plus size={14} />{t.home_new_farm}</button>
        </div>
      </div>

      {showFarms && (
        <ul className="farm-list">
          {farms.map(f => (
            <li key={f.id} className={f.id === farm.id ? "active" : ""}>
              <button className="farm-list-pick" onClick={() => { setSelected(f.id); setShowFarms(false); }}>
                <b>{f.name}</b>
                <small>{[f.village, f.district].filter(Boolean).join(", ")} · {f.area_value} {f.area_unit}</small>
              </button>
              {f.is_mine && onDeleteFarm ? (
                <button
                  className="secondary small danger"
                  onClick={() => window.confirm(`${f.name}: ${t.home_delete_confirm}`) && onDeleteFarm(f.id)}
                  aria-label={`${t.home_delete} ${f.name}`}
                >
                  <Trash2 size={14} /> {t.home_delete}
                </button>
              ) : (
                <small className="muted">{t.home_not_yours}</small>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="home-grid">
        <button className="home-weather" onClick={() => go("weather")}>
          {loadingWeather && !operational ? (
            <span className="muted"><RefreshCw size={14} className="spin" /> {t.loading}</span>
          ) : (
            <>
              <div className="home-weather-now">
                <span className="home-weather-icon" aria-hidden>{weatherIcon(today?.weather_code)}</span>
                <strong>{now.temp || (today ? `${Math.round(today.temp_max)}°C` : "--")}</strong>
                <span>{t.home_now}</span>
              </div>
              <dl className="home-weather-stats">
                <div><dt><Thermometer size={13} /> {t.col_temp}</dt><dd>{today ? `${Math.round(today.temp_max)}° / ${Math.round(today.temp_min)}°` : "--"}</dd></div>
                <div><dt><CloudRain size={13} /> {t.col_rain}</dt><dd>{today ? `${Math.round(today.rain_prob ?? 0)}% · ${(today.rain_mm ?? 0).toFixed(1)} mm` : "--"}</dd></div>
                <div><dt><Wind size={13} /> {t.col_wind}</dt><dd>{today?.wind_max != null ? `${Math.round(today.wind_max)} km/h` : "--"}</dd></div>
                <div><dt><Droplets size={13} /> {t.col_humidity}</dt><dd>{now.humidity || (today?.humidity != null ? `${Math.round(today.humidity)}%` : "--")}</dd></div>
              </dl>
              {week.length > 1 && (
                <div className="home-week" aria-label={t.forecast_7d}>
                  {week.map(day => (
                    <div key={day.date} className={day.rain_mm >= 1 ? "rainy" : ""}>
                      <small>{String(day.label).split(" ")[0]}</small>
                      <span aria-hidden>{weatherIcon(day.weather_code)}</span>
                      <b>{Math.round(day.temp_max)}°</b>
                      <small>{day.rain_mm >= 1 ? `${Math.round(day.rain_mm)} mm` : "–"}</small>
                    </div>
                  ))}
                </div>
              )}
              <div className="home-weather-total">
                <span>{t.rain_7d_label}</span>
                <b>{operational?.rain_7d_total_mm != null ? `${operational.rain_7d_total_mm} mm` : "--"}</b>
              </div>
            </>
          )}
        </button>

        <div className="home-advice">
          {todayText && (
            <div className="home-listen"><ListenButton text={todayText} locale={locale} label={t.listen_today} /></div>
          )}
          {cards.map(([key, icon, title, term]) => {
            const card: Json = operational?.[key] || {};
            return (
              <div key={key} className="home-advice-row" role="button" tabIndex={0} onClick={() => go("weather")}>
                <span className="home-advice-title">{icon} {title} <InfoTip term={term} locale={locale} /></span>
                <span className={`agri-tag ${TAG_CLASS[card.status] || "hold"}`}>{statusLabel(card.status)}</span>
                <span className="home-advice-text">{card.summary || (loadingWeather ? t.loading : "")}</span>
              </div>
            );
          })}
        </div>

        <div className="home-crops">
          <div className="home-crops-head">
            <b>{t.home_top_crops}{seasonName ? ` · ${seasonName}` : ""} <InfoTip term="match_score" locale={locale} /></b>
            <button className="link-btn" onClick={() => go("crops")}>{t.home_view_all} →</button>
          </div>
          {loadingRecs && !cropRecs ? (
            <span className="muted"><RefreshCw size={14} className="spin" /> {t.loading}</span>
          ) : topCrops.length ? (
            topCrops.map((crop, index) => (
              <button key={crop.crop} className="home-crop-row" onClick={() => go("crops")}>
                <span className="home-crop-rank">{index + 1}</span>
                <span className="home-crop-name">{crop.crop_name || crop.crop}</span>
                <span className="home-crop-score">{Math.round((crop.rank_score || 0) * 100)}%</span>
              </button>
            ))
          ) : (
            <span className="muted">{t.home_no_crops}</span>
          )}
        </div>
      </div>

      <div className="quick-actions">
        <button onClick={() => go("weather")}><CloudRain size={18} /><span>{t.weather}</span></button>
        <button onClick={() => go("soil")}><FlaskConical size={18} /><span>{t.soil_title}</span></button>
        <button onClick={() => go("crops")}><Sprout size={18} /><span>{t.crops}</span></button>
        <button onClick={() => go("advice")}><Activity size={18} /><span>{t.plan_title}</span></button>
        <button onClick={() => go("diagnose")}><Microscope size={18} /><span>{t.plant_doctor}</span></button>
      </div>

      <PlatformInfo locale={locale} go={go} hasFarm />

      <footer className="home-footer">
        <span className="sources-line">{t.sources_line}</span>
        <button className="link-btn" onClick={() => go("expert")}>{t.expert_review_link}</button>
      </footer>
    </section>
  );
};
