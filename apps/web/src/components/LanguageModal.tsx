import React from "react";
import { Languages } from "lucide-react";
import { Locale, NodeLanguage, T } from "../types";

export function LanguageModal({ t, locale, languages, choose }: { t: T; locale: Locale; languages: NodeLanguage[]; choose: (l: Locale) => void }) {
  const machine = languages.some((l) => l.machine_translated);
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="lang-title">
      <div className="modal-card">
        <Languages size={28} />
        <h2 id="lang-title">{t("choose_language")}</h2>
        <p>{t("choose_language_desc")}</p>
        <div className="lang-grid">
          {languages.map((item) => (
            <button key={item.locale} className={`lang-option ${item.locale === locale ? "active" : ""}`} onClick={() => choose(item.locale)}>
              {item.name}{item.machine_translated ? " *" : ""}
            </button>
          ))}
        </div>
        {machine && <p className="small-print">* {t("machine_translated_note")}</p>}
      </div>
    </div>
  );
}
