import React, { useEffect, useRef, useState } from "react";
import { Activity, Check, Mic, MicOff, Satellite, Send, Sparkles, Volume2, X } from "lucide-react";
import { api, apiBlob, speakText } from "../api";
import { useResource } from "../hooks";
import { Json, Locale, T, View } from "../types";
import { ErrorNote, formatDate, Loading, NeedFarm, SourceBadge, StageHeader, StatusPill } from "../components/ui";

interface Props {
  t: T;
  locale: Locale;
  farm?: Json;
  go: (v: View) => void;
}

export function AdvisoryView({ t, locale, farm, go }: Props) {
  if (!farm) return <NeedFarm t={t} go={go} />;
  return (
    <section className="panel">
      <StageHeader icon={<Activity />} step={t("step_n", { n: 5 })} title={t("plan_title")} subtitle={`${farm.name} · ${farm.district}`} />
      <PlanSection t={t} locale={locale} farm={farm} />
      <SatelliteSection t={t} locale={locale} farm={farm} />
      <ChatSection t={t} locale={locale} farm={farm} />
      <div className="pipeline-footer-nav">
        <button className="nav-prev-btn" onClick={() => go("crops")}>{t("back")}</button>
        <button className="nav-next-btn" onClick={() => go("diagnose")}>{t("plant_doctor")}</button>
      </div>
    </section>
  );
}

/** Voice input: records audio and transcribes it with Google Cloud Speech-to-Text on the server;
 *  falls back to the browser's speech recognition when the server voice service is unavailable. */
function useSpeechInput(locale: string, onText: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const hasRecorder = typeof window !== "undefined" && "MediaRecorder" in window && Boolean(navigator.mediaDevices?.getUserMedia);
  const BrowserRec = typeof window !== "undefined" ? ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition) : null;
  const supported = hasRecorder || Boolean(BrowserRec);

  const browserListen = () => {
    if (!BrowserRec) return;
    const rec = new BrowserRec();
    rec.lang = locale;
    rec.onresult = (event: any) => onText(event.results[0][0].transcript);
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    rec.start();
    setListening(true);
  };

  const toggle = async () => {
    if (listening) {
      recorder.current?.stop();
      setListening(false);
      return;
    }
    if (!hasRecorder) return browserListen();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunks.current = [];
      rec.ondataavailable = (e) => chunks.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const form = new FormData();
        form.append("file", new Blob(chunks.current, { type: rec.mimeType || "audio/webm" }), "question.webm");
        form.append("locale", locale);
        try {
          const res = await api<Json>("/api/v1/voice/transcribe", { method: "POST", body: form });
          if (res.transcript) onText(res.transcript);
        } catch {
          browserListen();
        }
      };
      recorder.current = rec;
      rec.start();
      setListening(true);
    } catch {
      browserListen();
    }
  };
  return { listening, toggle, supported };
}

function PlanSection({ t, locale, farm }: { t: T; locale: Locale; farm: Json }) {
  const history = useResource<Json[]>(`/api/v1/farms/${farm.id}/advisories`);
  const [plan, setPlan] = useState<Json | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const speech = useSpeechInput(locale, (text) => setQuestion(text));

  useEffect(() => {
    if (!plan && history.data?.length) setPlan(history.data[0]);
  }, [history.data]);

  const generate = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api<Json>(`/api/v1/farms/${farm.id}/advisories`, {
        method: "POST",
        body: JSON.stringify({ goal: farm.crop_status === "planted" ? "manage_current_crop" : "crop_plan", locale, farmer_question: question || null }),
      });
      setPlan(result);
      setQuestion("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const updateAction = async (id: string, status: string, outcome?: string) => {
    try {
      const updated = await api<Json>(`/api/v1/actions/${id}`, { method: "PATCH", body: JSON.stringify({ status, outcome: outcome || null }) });
      setPlan((current) => current && { ...current, actions: current.actions.map((a: Json) => (a.id === id ? updated : a)) });
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const listenText = plan ? [plan.summary, ...plan.actions.map((a: Json) => `${a.instruction} ${a.timing}`)].join(". ") : "";

  return (
    <div className="card-block">
      <h3><Sparkles size={18} /> {farm.crop_status === "planted" ? t("plan_care_title") : t("plan_make_title")}</h3>
      <p className="muted">{t("plan_desc")}</p>
      <div className="ask-row">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={t("plan_question_placeholder")} maxLength={500} />
        {speech.supported && (
          <button className={`icon-btn ${speech.listening ? "recording" : ""}`} onClick={speech.toggle} aria-label={t("speak")}>
            {speech.listening ? <MicOff size={18} /> : <Mic size={18} />}
          </button>
        )}
        <button className="primary" onClick={generate} disabled={busy}>{busy ? t("making_plan") : plan ? t("new_plan") : t("make_plan")}</button>
      </div>
      {busy && <Loading label={t("making_plan_long")} />}
      {error && <ErrorNote t={t} message={error} onRetry={generate} />}

      {plan && (
        <article className="plan">
          <div className="plan-head">
            <span className="muted">{formatDate(plan.created_at, locale, true)} · <SourceBadge t={t} kind="ai" /></span>
            <button className="icon-btn" onClick={() => speakText(listenText, locale).catch((err) => setError(err.message))}>
              <Volume2 size={16} /> {t("listen")}
            </button>
          </div>
          <p className="plan-summary">{plan.summary}</p>
          {plan.options?.length > 0 && (
            <div className="practice-chips">{plan.options.map((o: Json) => <span key={o.crop} className="practice-chip crop">{o.crop_name}</span>)}</div>
          )}
          <ol className="action-list">
            {plan.actions.map((a: Json) => (
              <li key={a.id} className={`action a-${a.status}`}>
                <div>
                  <b>{a.instruction}</b>
                  <span className="action-when">{a.timing}</span>
                  <p>{a.why}</p>
                  {a.caution && <p className="warn-text">{a.caution}</p>}
                </div>
                <ActionControls t={t} action={a} update={updateAction} />
              </li>
            ))}
          </ol>
          {plan.uncertainty_reasons?.length > 0 && (
            <div className="uncertainty">
              <b>{t("plan_limits")}</b>
              <ul>{plan.uncertainty_reasons.map((u: string) => <li key={u}>{u}</li>)}</ul>
            </div>
          )}
          <p className="small-print">{t("plan_disclaimer")}</p>
        </article>
      )}
    </div>
  );
}

function ActionControls({ t, action, update }: { t: T; action: Json; update: (id: string, status: string, outcome?: string) => void }) {
  if (action.status === "proposed") {
    return (
      <div className="action-btns">
        <button className="small primary" onClick={() => update(action.id, "accepted")}><Check size={14} /> {t("will_do")}</button>
        <button className="small secondary" onClick={() => update(action.id, "declined")}><X size={14} /> {t("not_for_me")}</button>
      </div>
    );
  }
  if (action.status === "accepted") {
    return (
      <div className="action-btns">
        <span className="muted">{t("did_it_work")}</span>
        {["worked", "partly", "did_not_work"].map((o) => (
          <button key={o} className="small secondary" onClick={() => update(action.id, "completed", o)}>{t(`outcome_${o}`)}</button>
        ))}
      </div>
    );
  }
  if (action.status === "completed") return <StatusPill status={action.outcome || "good"} label={action.outcome ? t(`outcome_${action.outcome}`) : t("done")} />;
  return <StatusPill status="info" label={t("declined")} />;
}

const INDICES = ["NDVI", "NDMI", "NDWI"];

function SatelliteSection({ t, locale, farm }: { t: T; locale: Locale; farm: Json }) {
  const [index, setIndex] = useState("NDVI");
  const map = useResource<Json>(`/api/v1/farms/${farm.id}/satellite/map?index=${index}`);
  const [image, setImage] = useState<string | null>(null);
  const [imageError, setImageError] = useState(false);
  const m = map.data;

  useEffect(() => {
    setImage(null);
    setImageError(false);
    if (!m || m.data_mode !== "live") return;
    let url: string | null = null;
    apiBlob(m.image_api_path).then((blob) => {
      url = URL.createObjectURL(blob);
      setImage(url);
    }).catch(() => setImageError(true));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [m?.image_api_path, m?.data_mode]);

  return (
    <div className="card-block">
      <div className="block-head">
        <h3><Satellite size={18} /> {t("satellite_title")}</h3>
        <SourceBadge t={t} kind="satellite" />
      </div>
      <div className="tab-row">
        {INDICES.map((i) => (
          <button key={i} className={`tab-btn ${index === i ? "active" : ""}`} onClick={() => setIndex(i)}>{t(`index_${i}`)}</button>
        ))}
      </div>
      {map.loading && !m && <Loading label={t("loading_satellite")} />}
      {map.error && <ErrorNote t={t} message={map.error} onRetry={map.reload} />}
      {m && m.data_mode !== "live" && <div className="info-banner">{m.note || t("satellite_unavailable")}</div>}
      {m?.data_mode === "live" && (
        <div className="sat-grid">
          <div className="sat-image">
            {image ? <img src={image} alt={t(`index_${index}`)} /> : imageError ? <p className="muted">{t("satellite_image_failed")}</p> : <Loading label={t("loading_satellite")} />}
            <p className="small-print">{t("satellite_scene", { date: formatDate(m.scene_date, locale), n: m.scene_count, cloud: m.cloud_coverage_percent ?? "-" })}</p>
          </div>
          <div>
            {m.field_median != null && (
              <p className="sat-stat">{t("field_median", { index, value: m.field_median.toFixed(2) })}
                {m.neighbour_cropland_median != null && <> · {t("neighbour_median", { value: m.neighbour_cropland_median.toFixed(2) })}</>}</p>
            )}
            {m.field_status && (
              <p className="sat-compare">
                {t(m.field_status === "below_neighbours" && index === "NDVI" && farm.crop_status !== "planted" ? "sat_below_neighbours_unplanted" : `sat_${m.field_status}`)}
              </p>
            )}
            <table className="zone-table">
              <thead><tr><th>{t("zone_class")}</th><th>{t("zone_range")}</th><th>{t("area")}</th><th>%</th></tr></thead>
              <tbody>
                {(m.zones as Json[]).map((z) => (
                  <tr key={z.id} className={z.percentage ? "" : "empty"}>
                    <td><span className="swatch" style={{ background: z.color }} /> {t(`zone_${z.label}`)}</td>
                    <td>{z.min_val} – {z.max_val}</td>
                    <td>{z.area_acres} {t("unit_acre")}</td>
                    <td>{z.percentage}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {m.note && <p className="hint">{t("no_boundary_satellite")}</p>}
            <p className="small-print">{t(`index_${index}_help`)}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function ChatSection({ t, locale, farm }: { t: T; locale: Locale; farm: Json }) {
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);
  const [input, setInput] = useState("");
  const [session, setSession] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const speech = useSpeechInput(locale, (text) => send(text));

  const send = async (preset?: string) => {
    const text = (preset ?? input).trim();
    if (!text || busy) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setBusy(true);
    setError("");
    try {
      const res = await api<Json>(`/api/v1/farms/${farm.id}/chat`, { method: "POST", body: JSON.stringify({ message: text, locale, session_id: session }) });
      setSession(res.session_id);
      setMessages((m) => [...m, { role: "assistant", text: res.response }]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const end = async () => {
    if (session) await api(`/api/v1/farms/${farm.id}/chat/${session}`, { method: "DELETE" }).catch(() => undefined);
    setSession(null);
    setMessages([]);
  };

  return (
    <div className="card-block chat">
      <div className="block-head">
        <h3>{t("chat_title")}</h3>
        {messages.length > 0 && <button className="link-btn" onClick={end}>{t("chat_end")}</button>}
      </div>
      <p className="muted">{t("chat_desc")}</p>
      <div className="chip-group">
        {["chat_q_spray", "chat_q_irrigate", "chat_q_sow"].map((k) => (
          <button key={k} className="chip" onClick={() => send(t(k))}>{t(k)}</button>
        ))}
      </div>
      {messages.length > 0 && (
        <div className="chat-log" aria-live="polite">
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              <span>{m.text}</span>
              {m.role === "assistant" && (
                <button className="link-btn" onClick={() => speakText(m.text, locale).catch(() => undefined)}><Volume2 size={13} /> {t("listen")}</button>
              )}
            </div>
          ))}
          {busy && <div className="bubble assistant muted">{t("thinking")}</div>}
        </div>
      )}
      {error && <ErrorNote t={t} message={error} />}
      <div className="ask-row">
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder={t("chat_placeholder")} maxLength={1000} />
        {speech.supported && (
          <button className={`icon-btn ${speech.listening ? "recording" : ""}`} onClick={speech.toggle} aria-label={t("speak")}>
            {speech.listening ? <MicOff size={18} /> : <Mic size={18} />}
          </button>
        )}
        <button className="primary" onClick={() => send()} disabled={busy || !input.trim()} aria-label={t("send")}><Send size={16} /></button>
      </div>
      <p className="small-print">{t("chat_privacy")}</p>
    </div>
  );
}
