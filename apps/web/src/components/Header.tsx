import React from "react";
import { BookOpen, Languages, Microscope, Sprout } from "lucide-react";
import { Json, Locale, T, View } from "../types";

export const LANGUAGE_LABELS: Record<Locale, string> = {
  "en-IN": "English",
  "hi-IN": "हिन्दी",
  "mr-IN": "मराठी",
  "te-IN": "తెలుగు",
  "kn-IN": "ಕನ್ನಡ",
};

interface HeaderProps {
  t: T;
  locale: Locale;
  view: View;
  setView: (v: View) => void;
  openLanguage: () => void;
  farms: Json[];
  selected: string;
  onSelect: (id: string) => void;
}

export function Header({ t, locale, view, setView, openLanguage, farms, selected, onSelect }: HeaderProps) {
  return (
    <header>
      <button className="brand" onClick={() => setView("home")} aria-label={t("go_home")}>
        <span className="mark"><Sprout size={24} /></span>
        <span>
          KISANAI
          <small>{t("brand_sub")}</small>
        </span>
      </button>
      <div className="top-actions">
        {farms.length > 1 && (
          <select className="farm-switcher" value={selected} onChange={(e) => onSelect(e.target.value)} aria-label={t("switch_farm")}>
            {farms.map((f) => <option key={f.id} value={f.id}>{f.name} · {f.district}</option>)}
          </select>
        )}
        <button className={`doctor-link ${view === "diagnose" ? "active" : ""}`} onClick={() => setView("diagnose")}>
          <Microscope size={16} />
          <span>{t("plant_doctor")}</span>
        </button>
        <button className="lang-toggle-btn" onClick={openLanguage} aria-label={t("change_language")}>
          <Languages size={15} />
          <span>{LANGUAGE_LABELS[locale]}</span>
        </button>
        <button className={`expert-link ${view === "expert" ? "active" : ""}`} onClick={() => setView("expert")}>
          <BookOpen size={16} />
          <span>{t("expert_area")}</span>
        </button>
      </div>
    </header>
  );
}
