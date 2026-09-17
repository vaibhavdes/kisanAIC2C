import React from "react";
import { BookOpen, Languages, Microscope, Sprout } from "lucide-react";
import { Json, Locale, TranslationDictionary, View } from "../types";
import { copy } from "../constants/localization";

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

export const Header: React.FC<HeaderProps> = ({
  t,
  locale,
  view,
  setView,
  setShowLangModal,
  farms,
  selected,
  setSelected
}) => {
  const isFarmMine = (f: Json) => {
    if (f.is_mine) return true;
    try {
      const myIds = JSON.parse(localStorage.getItem("kisanai_my_farm_ids") || "[]");
      return Array.isArray(myIds) && myIds.includes(f.id);
    } catch {
      return false;
    }
  };
  const languageLabels: Record<Locale, string> = {
    "en-IN": "English",
    "hi-IN": "हिन्दी",
    "mr-IN": "मराठी",
    "te-IN": "తెలుగు",
    "kn-IN": "ಕನ್ನಡ"
  };

  return (
    <header>
      <button className="brand" onClick={() => setView("home")}>
        <span className="mark">
          <Sprout size={24} />
        </span>
        <span>
          {t.brand_title} <b>C2C</b>
          <small>{t.brand_sub}</small>
        </span>
      </button>
      <div className="top-actions">
        {farms && farms.length > 0 && selected && setSelected && (
          <div className="header-farm-switcher" style={{ display: "flex", alignItems: "center" }}>
            <select
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value);
                const match = farms.find((f) => f.id === e.target.value);
                if (match) localStorage.setItem("kisanai_cached_farm", JSON.stringify(match));
              }}
              style={{
                padding: "4px 8px",
                fontSize: "12px",
                borderRadius: "16px",
                border: "1px solid var(--line, #e2e8f0)",
                background: "rgba(255,255,255,0.9)",
                fontWeight: 600,
                color: "#1e293b",
                maxWidth: "160px",
                cursor: "pointer"
              }}
              title="Switch Active Farm"
            >
              {farms.map((f) => {
                const mine = isFarmMine(f);
                return (
                  <option key={f.id} value={f.id}>
                    {mine ? "👤 " : "🌱 "}
                    {f.name} {mine ? "(My Farm)" : ""}
                  </option>
                );
              })}
            </select>
          </div>
        )}
        <button
          className={`doctor-link ${view === "diagnose" ? "active" : ""}`}
          onClick={() => setView("diagnose")}
          title="Instant AI Plant Doctor (No Location Needed)"
        >
          <Microscope size={16} />
          <span>{t.plant_doctor || t.diagnose || "Plant Doctor"}</span>
        </button>
        <button
          className="lang-toggle-btn"
          onClick={() => setShowLangModal(true)}
          title="Select Language / भाषा निवडा / अपनी भाषा चुनें"
        >
          <Languages size={15} />
          <span>
            {copy[locale]?.change_lang || "Language"}: {languageLabels[locale] || "English"}
          </span>
        </button>
        <button
          className={`expert-link ${view === "expert" ? "active" : ""}`}
          onClick={() => setView("expert")}
        >
          <BookOpen size={16} />
          <span>{t.expert}</span>
        </button>
      </div>
    </header>
  );
};
