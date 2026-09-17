import React from "react";
import { Languages } from "lucide-react";
import { Locale, TranslationDictionary } from "../types";

interface LanguageModalProps {
  t: TranslationDictionary;
  locale: Locale;
  selectLanguage: (locale: Locale) => void;
}

export const LanguageModal: React.FC<LanguageModalProps> = ({
  t,
  locale,
  selectLanguage
}) => {
  const languages = [
    { code: "en-IN", name: "English", native: "English", region: "All-India & Global" },
    { code: "hi-IN", name: "Hindi", native: "हिन्दी", region: "उत्तर एवं मध्य भारत" },
    { code: "mr-IN", name: "Marathi", native: "मराठी", region: "महाराष्ट्र" },
    { code: "te-IN", name: "Telugu", native: "తెలుగు", region: "తెలంగాణ & ఆంధ్రప్రదేశ్" },
    { code: "kn-IN", name: "Kannada", native: "ಕನ್ನಡ", region: "ಕರ್ನಾಟಕ" }
  ];

  return (
    <div className="lang-modal-overlay">
      <div className="lang-modal-card">
        <div className="lang-modal-header">
          <Languages size={28} color="var(--green-700)" />
          <div>
            <h3>{t.select_lang_title || "Choose Your Language"}</h3>
            <p>
              {t.select_lang_sub ||
                "Select your preferred language for advice, weather alerts & voice guidance."}
            </p>
          </div>
        </div>
        <div className="lang-modal-grid">
          {languages.map((l) => (
            <button
              key={l.code}
              type="button"
              className={`lang-card-btn ${locale === l.code ? "selected" : ""}`}
              onClick={() => selectLanguage(l.code as Locale)}
            >
              <div className="lang-card-native">{l.native}</div>
              <div className="lang-card-name">{l.name}</div>
              <div className="lang-card-region">{l.region}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
