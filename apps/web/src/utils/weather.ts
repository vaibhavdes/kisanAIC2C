import { Json, Locale } from "../types";
import { STATUS_TRANSLATIONS } from "../constants/statusTranslations";

export interface WeatherSummary {
  temp: string;
  wind: string;
  humidity: string;
  rainfall: string;
  forecast: Array<{ day: string; date: string; mm: number; prob: number }>;
  hasData: boolean;
}

export function parseWeatherFromEvidence(evidence: Json[], locale: Locale): WeatherSummary {
  let temp = "";
  let wind = "";
  let humidity = "";
  let rainfall = "";
  const dailyRainMap = new Map<string, { date: string; mm: number; prob: number }>();
  let hasData = false;

  // Prioritize newer snapshots first
  const weatherSnaps = [...evidence]
    .filter(snap => snap.kind === "weather_forecast" || snap.kind === "weather_nowcast")
    .sort((a, b) => {
      const timeA = new Date((a.fetched_at || a.issued_at || 0) as string).getTime();
      const timeB = new Date((b.fetched_at || b.issued_at || 0) as string).getTime();
      return timeB - timeA;
    });

  for (const snap of weatherSnaps) {
    const vals = (snap.values as Json[]) || [];
    for (const v of vals) {
      const name = (v.name as string) || "";
      const val = v.value;
      const unit = (v.unit as string) || "";

      // Temperature
      if (!temp && ["current_temperature", "temperature_2m", "temp_c", "temperature"].includes(name) && val !== null && val !== undefined) {
        temp = `${val}${unit === "C" ? "°C" : unit || "°C"}`;
        hasData = true;
      }
      // Wind speed
      else if (!wind && ["current_wind_speed", "wind_speed_10m", "wind_kph", "wind_speed"].includes(name) && val !== null && val !== undefined) {
        wind = `${val} ${unit || "km/h"}`;
        hasData = true;
      }
      // Relative humidity
      else if (!humidity && ["current_humidity", "relative_humidity_2m", "humidity_pct", "humidity"].includes(name) && val !== null && val !== undefined) {
        humidity = `${val}${unit === "percent" ? "%" : unit || "%"}`;
        hasData = true;
      }
      // Current rainfall
      else if (!rainfall && ["current_rainfall", "precipitation", "rainfall_today_mm", "rainfall_today"].includes(name) && val !== null && val !== undefined) {
        rainfall = `${val} ${unit || "mm"}`;
        hasData = true;
      }
      // Daily rainfall: rainfall_YYYY-MM-DD or rain_day_N
      else if (name.startsWith("rainfall_") && !name.includes("today") && !name.includes("7d") && val !== null && val !== undefined) {
        const dateStr = name.replace("rainfall_", "");
        hasData = true;
        const entry = dailyRainMap.get(dateStr) || { date: dateStr, mm: 0, prob: 0 };
        entry.mm = Number(val) || 0;
        dailyRainMap.set(dateStr, entry);
      }
      // Daily rain probability: rain_probability_YYYY-MM-DD
      else if (name.startsWith("rain_probability_") && val !== null && val !== undefined) {
        const dateStr = name.replace("rain_probability_", "");
        hasData = true;
        const entry = dailyRainMap.get(dateStr) || { date: dateStr, mm: 0, prob: 0 };
        entry.prob = Number(val) || 0;
        dailyRainMap.set(dateStr, entry);
      }
      // Also support legacy rain_day_N format
      else if (name.startsWith("rain_day_") && val !== null && val !== undefined) {
        hasData = true;
        const extra = (v.extra as Json) || {};
        const dStr = (extra.date as string) || name;
        const entry = dailyRainMap.get(dStr) || { date: dStr, mm: 0, prob: 0 };
        entry.mm = Number(val) || 0;
        if (extra.prob) entry.prob = Number(extra.prob) || 0;
        dailyRainMap.set(dStr, entry);
      }
    }
  }

  // Convert dailyRainMap to sorted forecast array (up to 7 days, sorted chronologically)
  const entries = Array.from(dailyRainMap.values())
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(0, 7);

  const forecast: Array<{ day: string; date: string; mm: number; prob: number }> = [];
  const todayStr = new Date().toISOString().slice(0, 10);

  for (let idx = 0; idx < entries.length; idx++) {
    const item = entries[idx];
    let dayLabel = `Day ${idx + 1}`;
    if (item.date && !isNaN(Date.parse(item.date))) {
      const dt = new Date(item.date);
      if (item.date === todayStr) {
        dayLabel = locale.startsWith("mr") ? "आज" : locale.startsWith("hi") ? "आज" : "Today";
      } else {
        dayLabel = dt.toLocaleDateString(locale, { weekday: "short" });
      }
    }
    forecast.push({
      day: dayLabel,
      date: item.date,
      mm: item.mm,
      prob: item.prob
    });
  }

  return { temp, wind, humidity, rainfall, forecast, hasData };
}

export interface SatelliteMetrics {
  ndvi: string;
  ndwi: string;
  ndmi: string;
  rawMoist: string;
  rawVeg: string;
  waterStress: string;
  vegStatus: string;
  moistStatus: string;
  hasData: boolean;
}

export function parseSatelliteMetrics(evidence: Json[], locale: Locale): SatelliteMetrics {
  let ndvi = "";
  let ndwi = "";
  let ndmi = "";
  let rawMoist = "";
  let rawVeg = "";
  let waterStress = "";
  let vegStatus = "";
  let moistStatus = "";
  let hasData = false;

  const tr = STATUS_TRANSLATIONS[locale] || STATUS_TRANSLATIONS["en-IN"];

  for (const snap of evidence) {
    if (snap.kind === "satellite_indices" || snap.kind === "satellite_observation") {
      hasData = true;
      const vals = (snap.values as Json[]) || [];
      for (const v of vals) {
        const name = (v.name as string) || "";
        const val = v.value;
        if (name === "ndvi_median" || name === "ndvi") {
          if (val !== null && val !== undefined) ndvi = Number(val).toFixed(2);
        } else if (name === "ndwi_median" || name === "ndwi") {
          if (val !== null && val !== undefined) ndwi = Number(val).toFixed(2);
        } else if (name === "ndmi_median" || name === "ndmi") {
          if (val !== null && val !== undefined) ndmi = Number(val).toFixed(2);
        } else if (name === "water_stress") {
          const sVal = String(val).toLowerCase();
          waterStress = tr[sVal] || sVal.replace("_", " ");
        } else if (name === "vegetation_status") {
          rawVeg = String(val).toLowerCase();
          vegStatus = tr[rawVeg] || rawVeg.replace("_", " ");
        } else if (name === "moisture_status") {
          rawMoist = String(val).toLowerCase();
          moistStatus = tr[rawMoist] || rawMoist.replace("_", " ");
        }
      }
    }
  }

  return { ndvi, ndwi, ndmi, rawMoist, rawVeg, waterStress, vegStatus, moistStatus, hasData };
}

export function getImdWarningLevel(
  evidence: Json[],
  locale: Locale
): { level: "red" | "orange" | "yellow" | null; msg: string } {
  for (const snap of evidence) {
    if (snap.kind === "official_warning" || snap.kind === "weather_nowcast") {
      const values = (snap.values as Json[]) || [];
      for (const v of values) {
        const name = (v.name as string) || "";
        const val = Number(v.value);
        if ((name.includes("color_code") || name.includes("warning_code")) && !isNaN(val)) {
          if (val === 1)
            return {
              level: "red",
              msg: "⚠ RED ALERT: Extreme rainfall or thunderstorm warning. Take protective action immediately."
            };
          if (val === 2)
            return {
              level: "orange",
              msg: "⚠ ORANGE ALERT: Heavy rainfall or strong wind advisory. Postpone spraying and secure field drainage."
            };
          if (val === 3)
            return {
              level: "yellow",
              msg: "⚡ YELLOW WATCH: Moderate weather variation. Monitor field conditions."
            };
        }
      }
    }
  }
  return { level: null, msg: "" };
}
