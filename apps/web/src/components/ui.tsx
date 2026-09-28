import React from "react";
import { AlertTriangle, Loader2, MapPin, RefreshCw } from "lucide-react";
import { T, View } from "../types";

/** Where a number came from. Every figure shown to a farmer carries one of these. */
export function SourceBadge({ kind, t, title }: { kind: string; t: T; title?: string }) {
  return (
    <span className={`src-badge src-${kind}`} title={title || t(`src_${kind}_hint`)}>
      {t(`src_${kind}`)}
    </span>
  );
}

const STATUS_TONE: Record<string, string> = {
  good: "good", ready: "good", not_needed: "good", normal: "good", low: "good", open: "good", worked: "good", safe: "good",
  fair: "fair", caution: "fair", monitor: "fair", watch: "fair", moderate: "fair", upcoming: "fair", wait_for_rain: "fair", partly: "fair",
  irrigate_first: "fair", info: "info", not_applicable: "info",
  limiting: "warn", irrigate: "warn", deficit: "warn", wait: "warn",
  blocking: "bad", avoid: "bad", high: "bad", did_not_work: "bad",
};

export function StatusPill({ status, label }: { status: string; label: string }) {
  return <span className={`status-pill tone-${STATUS_TONE[status] || "info"}`}>{label}</span>;
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="state-box" role="status">
      <Loader2 className="spin" size={22} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorNote({ message, onRetry, t }: { message: string; onRetry?: () => void; t: T }) {
  return (
    <div className="error-note" role="alert">
      <AlertTriangle size={18} />
      <span>{message}</span>
      {onRetry && (
        <button className="secondary small" onClick={onRetry}>
          <RefreshCw size={14} /> {t("retry")}
        </button>
      )}
    </div>
  );
}

export function NeedFarm({ t, go }: { t: T; go: (v: View) => void }) {
  return (
    <section className="panel empty-panel">
      <MapPin size={40} />
      <h2>{t("add_farm_first")}</h2>
      <p>{t("add_farm_first_desc")}</p>
      <button className="primary" onClick={() => go("farm")}>{t("add_farm")}</button>
    </section>
  );
}

export function StageHeader({ icon, step, title, subtitle }: { icon: React.ReactNode; step?: string; title: string; subtitle?: string }) {
  return (
    <div className="section-title">
      {icon}
      <div>
        {step && <small>{step}</small>}
        <h2>{title}</h2>
        {subtitle && <p className="stage-sub">{subtitle}</p>}
      </div>
    </div>
  );
}

export function formatDate(value: string | null | undefined, locale: string, withTime = false): string {
  if (!value) return "";
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale, withTime
    ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }
    : { day: "numeric", month: "short" });
}

export function pct(value: number | null | undefined): string {
  return value == null ? "-" : `${Math.round(value * 100)}%`;
}
