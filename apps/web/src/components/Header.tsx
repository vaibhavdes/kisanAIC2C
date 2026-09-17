import React from "react";
import { BookOpen, Languages, Microscope, Sprout } from "lucide-react";
import { Locale, TranslationDictionary, View } from "../types";
import { copy } from "../constants/localization";

interface HeaderProps {
  t: TranslationDictionary;
  locale: Locale;
  view: View;
  setView: (v: View) => void;
  setShowLangModal: (show: boolean) => void;
}

export const Header: React.FC<HeaderProps> = ({
  t,
  locale,
  view,
  setView,
  setShowLangModal
}) => {
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
