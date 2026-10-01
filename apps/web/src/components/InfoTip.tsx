import { useEffect, useRef, useState } from "react";
import { Info, Volume2, X } from "lucide-react";
import { explain } from "../constants/glossary";
import { Locale } from "../types";
import { speakText } from "../utils/voice";

/** (i) button that explains a technical word in plain language, with read-aloud. */
export function InfoTip({ term, locale }: { term: string; locale: Locale }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const entry = explain(term, locale);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!entry) return null;
  return (
    <span className="info-tip" ref={box} onClick={e => e.stopPropagation()}>
      <button type="button" className="info-tip-btn" aria-label={entry.title} aria-expanded={open} onClick={() => setOpen(!open)}>
        <Info size={14} />
      </button>
      {open && (
        <span className="info-tip-pop" role="dialog">
          <span className="info-tip-head">
            <b>{entry.title}</b>
            <button type="button" aria-label="Close" onClick={() => setOpen(false)}><X size={14} /></button>
          </span>
          <span className="info-tip-text">{entry.text}</span>
          <button type="button" className="info-tip-listen" onClick={() => speakText(`${entry.title}. ${entry.text}`, locale)}>
            <Volume2 size={14} /> 🔊
          </button>
        </span>
      )}
    </span>
  );
}

/** Small speaker button that reads the given text in the farmer's language. */
export function ListenButton({ text, locale, label }: { text: string; locale: Locale; label?: string }) {
  if (!text) return null;
  return (
    <button
      type="button"
      className="listen-inline"
      onClick={e => { e.stopPropagation(); speakText(text, locale); }}
      aria-label={label || "Listen"}
    >
      <Volume2 size={14} />{label ? <span>{label}</span> : null}
    </button>
  );
}
