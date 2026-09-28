import React from "react";
import { Languages } from "lucide-react";
import { Locale, LOCALES, T } from "../types";
import { LANGUAGE_LABELS } from "./Header";

export function LanguageModal({ t, locale, choose }: { t: T; locale: Locale; choose: (l: Locale) => void }) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="lang-title">
      <div className="modal-card">
        <Languages size={28} />
        <h2 id="lang-title">{t("choose_language")}</h2>
        <p>{t("choose_language_desc")}</p>
        <div className="lang-grid">
          {LOCALES.map((code) => (
            <button key={code} className={`lang-option ${code === locale ? "active" : ""}`} onClick={() => choose(code)}>
              {LANGUAGE_LABELS[code]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
