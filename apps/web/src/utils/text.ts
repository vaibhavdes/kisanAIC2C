import { Json, T } from "../types";
import { formatDate } from "../components/ui";

const n = (value: unknown, digits = 0) => (typeof value === "number" ? value.toFixed(digits) : "-");

function when(t: T, iso: string | undefined, locale: string): string {
  if (!iso) return "";
  const today = new Date();
  const date = new Date(iso);
  const sameDay = date.toDateString() === today.toDateString();
  const tomorrow = new Date(today.getTime() + 86400000).toDateString() === date.toDateString();
  return sameDay ? t("today") : tomorrow ? t("tomorrow") : formatDate(iso, locale);
}

/** Sentence for one field-operation window (sowing / spray / irrigation / drainage). */
export function operationText(t: T, section: string, item: Json | undefined, locale: string): string {
  if (!item) return "";
  const p = item.params || {};
  switch (section) {
    case "sowing":
      if (item.status === "ready") return t("op_sow_ready", { pct: Math.round((p.moisture_ratio || 0) * 100) });
      if (item.status === "wait_for_rain") return t("op_sow_wait_for_rain", { mm: n(p.rain_next_3d_mm), prob: p.probability });
      if (item.status === "irrigate_first") return t("op_sow_irrigate_first");
      if (item.status === "not_applicable") return t("op_sow_na");
      return t("op_sow_wait");
    case "spray": {
      const w = item.window;
      if (item.status === "good" && w) return t("op_spray_good", { when: when(t, w.start, locale), start: w.start.slice(11, 16), end: w.end.slice(11, 16) });
      if (item.status === "caution" && w) return t("op_spray_caution", { when: when(t, w.start, locale), start: w.start.slice(11, 16) });
      return t("op_spray_avoid");
    }
    case "irrigation":
      if (item.status === "not_needed") return t("op_irr_not_needed", { rain: n(p.rain_7d_mm), et: n(p.et0_7d_mm) });
      if (item.status === "irrigate") return t("op_irr_irrigate", { deficit: n(Math.abs(p.balance_mm)) });
      if (item.status === "deficit") return t("op_irr_deficit", { deficit: n(Math.abs(p.balance_mm)) });
      return t("op_irr_monitor", { deficit: n(Math.abs(p.balance_mm)) });
    case "drainage":
      if (item.status === "high") return t("op_drain_high", { mm: n(p.max_3day_mm) });
      if (item.status === "watch") return t("op_drain_watch", { mm: n(p.max_3day_mm) });
      return t("op_drain_normal");
    default:
      return item.message || "";
  }
}

export function riskText(t: T, risk: Json): string {
  const p = risk.params || {};
  switch (risk.id) {
    case "fungal_leaf": return t("risk_fungal_leaf_text", { hours: p.leaf_wet_hours });
    case "late_blight": return t(p.smith_period ? "risk_late_blight_yes" : "risk_late_blight_no");
    case "rice_blast": return t("risk_rice_blast_text", { days: p.favourable_days });
    case "sucking_pests": return t("risk_sucking_pests_text", { days: p.hot_dry_days });
    default: return risk.message || "";
  }
}

/** Sentence for one crop decision factor produced by the recommendation engine. */
export function factorText(t: T, factor: Json, locale: string): string {
  const p = factor.params || {};
  switch (factor.id) {
    case "sowing_window":
      if (p.needs_irrigation) return t("f_sow_needs_irrigation");
      if (p.status === "open") return t("f_sow_open", { end: formatDate(p.end, locale) });
      if (p.status === "upcoming") return t("f_sow_upcoming", { start: formatDate(p.start, locale), days: p.days_until_start });
      return p.next_start ? t("f_sow_closed", { next: formatDate(p.next_start, locale) }) : t("f_sow_none");
    case "temperature":
      if (p.mean_min_c == null) return t("f_no_climate");
      return t(p.frost_risk ? "f_temp_frost" : "f_temp", { min: n(p.mean_min_c), max: n(p.mean_max_c), omin: p.optimal_min_c, omax: p.optimal_max_c });
    case "water":
      if (p.need == null) return t("f_no_climate");
      if (!p.gap) return t("f_water_ok", { need: p.need, available: p.available }) + (p.excess_rain ? " " + t("f_water_excess") : "");
      return t(p.water_access === "rainfed" ? "f_water_gap_rainfed" : "f_water_gap_irrigated", { need: p.need, available: p.available, gap: p.gap })
        + (p.excess_rain ? " " + t("f_water_excess") : "");
    case "soil_ph":
      return t("f_ph", { ph: n(p.ph, 1), omin: p.optimal_min, omax: p.optimal_max, src: t(factor.source === "measured" ? "src_measured" : "src_estimated") });
    case "soil_texture":
      return t("f_texture", { texture: t(`texture_${p.texture}`), preferred: (p.preferred || []).map((x: string) => t(`texture_${x}`)).join(", ") || "-" });
    case "salinity":
      return t("f_salinity", { ec: p.ec_ds_m });
    case "groundwater":
      return t("f_groundwater", { category: t(`gw_${p.category}`), water: t(`water_class_${p.water_class}`) });
    case "rotation":
      return t(`f_rot_${p.pattern}`, { previous: p.previous_name });
    case "nitrogen":
      return t(p.legume ? "f_n_low_legume" : "f_n_low");
    case "organic_carbon":
      return t("f_oc_low");
    case "field_state":
      return p.ndvi != null ? t("f_field_green", { ndvi: n(p.ndvi, 2) }) : t("f_field_moist", { ndmi: n(p.ndmi, 2) });
    default:
      return factor.message || "";
  }
}

export function rejectionText(t: T, code: string): string {
  return t(`rej_${code}`);
}
