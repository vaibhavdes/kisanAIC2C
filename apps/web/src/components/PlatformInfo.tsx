import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { ABOUT_TITLE, FEATURES, QUESTIONS, SOURCES, TABS, pick } from "../constants/platformInfo";
import { Locale, View } from "../types";

type Tab = keyof typeof TABS;

/** One compact "about" panel on the homepage, with three tabs. */
export function PlatformInfo({ locale, go, hasFarm }: { locale: Locale; go: (v: View) => void; hasFarm: boolean }) {
  const [tab, setTab] = useState<Tab>("features");
  // Without a farm, every screen except the plant doctor needs one first.
  const open = (view: View) => go(hasFarm || view === "diagnose" ? view : "farm");

  return (
    <section className="about-panel">
      <div className="about-head">
        <h2>{pick(ABOUT_TITLE, locale)}</h2>
        <div className="about-tabs" role="tablist">
          {(Object.keys(TABS) as Tab[]).map(key => (
            <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
              {pick(TABS[key], locale)}
            </button>
          ))}
        </div>
      </div>

      {tab === "features" && (
        <div className="about-grid">
          {FEATURES.map(f => (
            <button key={f.title[0]} className="about-item" onClick={() => open(f.view)}>
              <span className="about-icon">{f.icon}</span>
              <span>
                <b>{pick(f.title, locale)}</b>
                <small>{pick(f.text, locale)}</small>
              </span>
            </button>
          ))}
        </div>
      )}

      {tab === "questions" && (
        <div className="about-list">
          {QUESTIONS.map(q => (
            <button key={q.question[0]} className="about-row" onClick={() => open(q.view)}>
              <span>
                <b>{pick(q.question, locale)}</b>
                <small>{pick(q.answer, locale)}</small>
              </span>
              <ChevronRight size={16} />
            </button>
          ))}
        </div>
      )}

      {tab === "sources" && (
        <div className="about-grid">
          {SOURCES.map(s => (
            <div key={s.name} className="about-item static">
              <span className="about-icon">{s.icon}</span>
              <span>
                <b>{s.name}</b>
                <small>{pick(s.text, locale)}</small>
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
