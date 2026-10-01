import { useEffect, useState } from "react";
import { CheckCircle2, Clock, RefreshCw, Send, Stethoscope } from "lucide-react";
import { api } from "../api";
import { Json } from "../types";

/** Agronomist queue: Plant Doctor diagnoses the AI flagged as uncertain. */
export function ExpertView({ t }: { t: Record<string, string> }) {
  const [cases, setCases] = useState<Json[] | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [images, setImages] = useState<Record<string, string>>({});

  const load = async () => {
    try {
      const list = await api<Json[]>("/api/v1/expert/cases", {}, true);
      setCases(list);
      // Photos need the expert headers, so they are fetched as blobs rather than plain <img src>.
      for (const c of list) {
        if (c.image_url && !images[c.id]) {
          fetch(c.image_url, { headers: { "X-Actor-Id": "local-expert", "X-Actor-Role": "expert" } })
            .then(r => (r.ok ? r.blob() : Promise.reject()))
            .then(blob => setImages(prev => ({ ...prev, [c.id]: URL.createObjectURL(blob) })))
            .catch(() => undefined);
        }
      }
    } catch (e) {
      setError((e as Error).message);
      setCases([]);
    }
  };

  useEffect(() => { load(); }, []);

  const resolve = async (c: Json) => {
    setBusy(c.id);
    try {
      await api(`/api/v1/expert/cases/${c.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "resolved", review_text: notes[c.id], version: c.version }),
      }, true);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  return (
    <section className="panel">
      <div className="section-title">
        <Stethoscope />
        <div>
          <small>{t.plant_doctor}</small>
          <h2>{t.expert_title}</h2>
        </div>
      </div>
      <p className="muted">{t.expert_desc}</p>
      {error && <div className="notice error" onClick={() => setError("")}>{error}</div>}

      {cases === null ? (
        <p className="muted"><RefreshCw size={14} className="spin" /> {t.loading}</p>
      ) : cases.length === 0 ? (
        <p className="empty-note">{t.expert_none}</p>
      ) : (
        cases.map(c => {
          const resolved = c.status === "resolved";
          const d: Json = c.diagnosis || {};
          return (
            <article key={c.id} className="case-card">
              <div className="case-head">
                <b>{d.crop && d.crop !== "auto-detect" ? d.crop : t.plant_doctor}{c.farm ? ` · ${c.farm.district}` : ""}</b>
                <span className={`agri-tag ${resolved ? "safe" : "caution"}`}>
                  {resolved ? <CheckCircle2 size={12} /> : <Clock size={12} />} {resolved ? t.expert_answered : t.expert_waiting}
                </span>
                <small className="muted">{new Date(c.created_at).toLocaleString()}</small>
              </div>
              <div className="case-body">
                {images[c.id] && <img src={images[c.id]} alt="" className="case-photo" />}
                <div>
                  {d.visible_findings?.length > 0 && (<><h5>{t.findings}</h5><ul>{d.visible_findings.map((x: string) => <li key={x}>{x}</li>)}</ul></>)}
                  {d.plausible_causes?.length > 0 && (<><h5>{t.causes}</h5><ul>{d.plausible_causes.map((x: string) => <li key={x}>{x}</li>)}</ul></>)}
                  {d.uncertainty_reasons?.length > 0 && <small className="muted">ⓘ {d.uncertainty_reasons.join(" · ")}</small>}
                </div>
              </div>
              {resolved ? (
                <div className="case-answer">
                  <p>{c.review_text}</p>
                  <small className="muted">{c.reviewed_by} · {c.reviewed_at ? new Date(c.reviewed_at).toLocaleDateString() : ""}</small>
                </div>
              ) : (
                <div className="case-reply">
                  <textarea
                    rows={3}
                    placeholder={t.expert_reply}
                    value={notes[c.id] || ""}
                    onChange={e => setNotes({ ...notes, [c.id]: e.target.value })}
                  />
                  <button className="primary" disabled={busy === c.id || !(notes[c.id] || "").trim()} onClick={() => resolve(c)}>
                    <Send size={14} /> {t.expert_submit}
                  </button>
                </div>
              )}
            </article>
          );
        })
      )}
    </section>
  );
}
