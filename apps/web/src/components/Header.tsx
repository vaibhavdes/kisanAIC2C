import React from "react";
import { Languages, Microscope, Sprout } from "lucide-react";
import { Json, Locale, TranslationDictionary, View } from "../types";

interface HeaderProps {
  t: TranslationDictionary;
  locale: Locale;
  view: View;
  setView: (v: View) => void;
  setShowLangModal: (show: boolean) => void;
  farms?: Json[];
  selected?: string;
  setSelected?: (id: string) => void;
}

const LANGUAGE_LABELS: Record<Locale, string> = {
  "en-IN": "English",
  "hi-IN": "हिन्दी",
  "mr-IN": "मराठी",
  "te-IN": "తెలుగు",
  "kn-IN": "ಕನ್ನಡ"
};

export const Header: React.FC<HeaderProps> = ({
  t,
  locale,
  view,
  setView,
  setShowLangModal,
  farms,
  selected,
  setSelected
}) => (
  <header>
    <button className="brand" onClick={() => setView("home")}>
      <span className="mark">
        <Sprout size={22} />
      </span>
      <span>
        KISANAI
        <small>{t.brand_sub}</small>
      </span>
    </button>
    <div className="top-actions">
      {farms && farms.length > 1 && selected && setSelected && (
        <select
          className="header-farm-select"
          value={selected}
          onChange={e => {
            setSelected(e.target.value);
            const match = farms.find(f => f.id === e.target.value);
            if (match) localStorage.setItem("kisanai_cached_farm", JSON.stringify(match));
          }}
          aria-label="Farm"
        >
          {farms.map(f => (
            <option key={f.id} value={f.id}>
              {f.name} · {f.district}
            </option>
          ))}
        </select>
      )}
      <button
        className={`doctor-link ${view === "diagnose" ? "active" : ""}`}
        onClick={() => setView("diagnose")}
      >
        <Microscope size={16} />
        <span>{t.plant_doctor || t.diagnose}</span>
      </button>
      <button className="lang-toggle-btn" onClick={() => setShowLangModal(true)} aria-label="Language">
        <Languages size={15} />
        <span>{LANGUAGE_LABELS[locale]}</span>
      </button>
    </div>
  </header>
);
