import { useRef, useState } from "react";
import { Activity, ArrowRight, Check, CheckCircle2, Droplets, Leaf, Mic, MicOff, RefreshCw, Satellite, Sparkles, Sprout, Volume2 } from "lucide-react";
import { api } from "../api";
import { Json, Locale, View } from "../types";
import { parseSatelliteMetrics } from "../utils/weather";
import { InfoTip, ListenButton } from "../components/InfoTip";
import { FieldMap } from "../components/FieldMap";
import { explain } from "../constants/glossary";
import { speakText } from "../utils/voice";

export interface AdvisoryViewProps {
  t: Record<string, string>;
  locale: Locale;
  farm?: Json;
  satMap: Json | null;
  satIndex: string;
  loadSatMap: (index: string) => Promise<void>;
  evidence: Json[];
  season: string;
  handleSeasonChange: (s: string) => void;
  go: (v: View) => void;
}

/** Records audio and returns Google Cloud Speech-to-Text's transcript. */
function useRecorder(locale: Locale, onText: (text: string) => void, onError: (message: string) => void) {
  const recorder = useRef<MediaRecorder | null>(null);
  const [recording, setRecording] = useState(false);

  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = e => chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach(track => track.stop());
        const body = new FormData();
        body.append("file", new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
        body.append("locale", locale);
        try {
          const res = await api<Json>("/api/v1/voice/transcribe", { method: "POST", body });
          if (res.transcript) onText(res.transcript);
        } catch (err) {
          onError((err as Error).message);
        }
      };
      rec.start();
      recorder.current = rec;
      setRecording(true);
    } catch (err) {
      onError((err as Error).message);
    }
  };
  const stop = () => {
    recorder.current?.stop();
    setRecording(false);
  };
  return { recording, toggle: () => (recording ? stop() : start()) };
}

export function AdvisoryView({ t, locale, farm, satMap, satIndex, loadSatMap, evidence, season, handleSeasonChange, go }: AdvisoryViewProps) {
  const [result, setResult] = useState<Json | null>(null);
  const [question, setQuestion] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [chat, setChat] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [overlayOpacity, setOverlayOpacity] = useState(0.75);

  const planMic = useRecorder(locale, setQuestion, setError);
  const chatMic = useRecorder(locale, text => sendChat(text), setError);

  if (!farm) {
    return (
      <section className="panel empty-state">
        <Activity size={40} />
        <h2>{t.add_farm_first}</h2>
        <button className="primary" onClick={() => go("farm")}>{t.home_add_farm}</button>
      </section>
    );
  }

  const sat = parseSatelliteMetrics(evidence, locale);

  const createPlan = async () => {
    setGenerating(true);
    setError("");
    try {
      setResult(await api<Json>(`/api/v1/farms/${farm.id}/advisories`, {
        method: "POST",
        body: JSON.stringify({
          goal: farm.crop_status === "planted" && farm.current_crop ? "manage_current_crop" : "crop_plan",
          season,
          locale,
          farmer_query: question || null,
        }),
      }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGenerating(false);
    }
  };

  const act = async (actionId: string, status: "accepted" | "declined") => {
    try {
      await api(`/api/v1/actions/${actionId}`, { method: "PATCH", body: JSON.stringify({ status }) });
      setResult(r => r && { ...r, actions: r.actions.map((a: Json) => (a.id === actionId ? { ...a, status } : a)) });
    } catch (err) {
      setError((err as Error).message);
    }
  };

  async function sendChat(preset?: string) {
    const text = (preset ?? chatInput).trim();
    if (!text || chatLoading) return;
    setChat(prev => [...prev, { role: "user", text }]);
    setChatInput("");
    setChatLoading(true);
    try {
      const res = await api<Json>(`/api/v1/farms/${farm!.id}/chat`, {
        method: "POST",
        body: JSON.stringify({ message: text, locale, session_id: sessionId }),
      });
      setSessionId(res.session_id);
      setChat(prev => [...prev, { role: "assistant", text: res.response }]);
    } catch (err) {
      setChat(prev => [...prev, { role: "assistant", text: (err as Error).message }]);
    } finally {
      setChatLoading(false);
    }
  }

  const endChat = async () => {
    if (sessionId) await api(`/api/v1/farms/${farm.id}/chat/${sessionId}`, { method: "DELETE" }).catch(() => undefined);
    setChat([]);
    setSessionId(null);
  };

  const aiWritten = result && result.model_provider !== "rule_based";

  return (
    <section className="panel">
      <div className="section-title">
        <Activity />
        <div>
          <small>{farm.name} · {farm.district}</small>
          <h2>{t.plan_title}</h2>
        </div>
      </div>
      {error && <div className="notice error" onClick={() => setError("")}>{error}</div>}

      {/* Satellite crop health: plain-language first, numbers under "Technical details" */}
      <div className="sat-card">
        <div className="sat-card-head">
          <h3><Satellite size={18} /> {t.sat_title} <InfoTip term="satellite" locale={locale} /></h3>
          <span className="sat-index-pick">
            <select value={satIndex} onChange={e => loadSatMap(e.target.value)}>
              <option value="NDVI">{explain("ndvi", locale)?.title}</option>
              <option value="NDMI">{explain("ndmi", locale)?.title}</option>
              <option value="NDWI">{explain("ndwi", locale)?.title}</option>
            </select>
            <InfoTip term={satIndex.toLowerCase()} locale={locale} />
          </span>
        </div>

        {/* Latest satellite readings: agronomic value and status, with the plain meaning under each */}
        {sat.hasData && (sat.ndvi || sat.ndmi) && (
          <div className="sat-outcome-grid">
            {sat.ndvi && (
              <div className="sat-outcome-card ndvi">
                <div className="sat-outcome-header"><Leaf size={18} color="#16a34a" /><span>{t.ndvi_label_short} <InfoTip term="ndvi" locale={locale} /></span></div>
                <div className="sat-outcome-main">
                  <span className="sat-outcome-number">{sat.ndvi}</span>
                  <span className={`sat-outcome-pill ${sat.rawVeg}`}>{sat.vegStatus}</span>
                </div>
                <p className="sat-outcome-simple">{sat.vegSimple}</p>
              </div>
            )}
            {sat.ndmi && (
              <div className="sat-outcome-card ndmi">
                <div className="sat-outcome-header"><Droplets size={18} color="#0284c7" /><span>{t.ndmi_label_short} <InfoTip term="ndmi" locale={locale} /></span></div>
                <div className="sat-outcome-main">
                  <span className="sat-outcome-number">{sat.ndmi}</span>
                  <span className={`sat-outcome-pill ${sat.rawMoist}`}>{sat.moistStatus}</span>
                </div>
                <p className="sat-outcome-simple">{sat.moistSimple}</p>
              </div>
            )}
            {sat.waterStress && (
              <div className="sat-outcome-card stress">
                <div className="sat-outcome-header"><Activity size={18} color="#b45309" /><span>{t.water_stress} <InfoTip term="water_stress" locale={locale} /></span></div>
                <div className="sat-outcome-main">
                  <span className={`sat-outcome-pill stress-${sat.rawStress}`}>{sat.waterStress}</span>
                </div>
                <p className="sat-outcome-simple">{sat.stressSimple}</p>
              </div>
            )}
            {sat.observedAt && <small className="muted sat-observed">Sentinel-2 · {new Date(sat.observedAt).toLocaleDateString(locale)}</small>}
          </div>
        )}

        {!satMap || satMap.index !== satIndex ? (
          <p className="muted"><RefreshCw size={14} className="spin" /> {t.sat_loading}</p>
        ) : satMap.data_mode !== "live" ? (
          <p className="notice">{t.sat_unavailable}. {satMap.acquisition_note}</p>
        ) : (
          <>
            {satMap.simple_summary && (
              <div className="sat-simple">
                <p>{satMap.simple_summary}</p>
                <ListenButton text={satMap.simple_summary} locale={locale} label={t.listen} />
              </div>
            )}
            <div className="sat-body">
              <div>
                {satMap.bounds ? (
                  <FieldMap
                    center={[farm.location?.latitude, farm.location?.longitude]}
                    boundary={farm.boundary_coordinates || []}
                    overlay={{ url: satMap.image_api_path, bounds: satMap.bounds, opacity: overlayOpacity }}
                    height={340}
                  />
                ) : (
                  <img src={satMap.image_api_path} alt={satMap.meaning} className="sat-image" />
                )}
                <label className="overlay-opacity">
                  <span>{t.overlay_opacity}</span>
                  <input type="range" min={0} max={100} value={Math.round(overlayOpacity * 100)} onChange={e => setOverlayOpacity(Number(e.target.value) / 100)} />
                </label>
                <small className="muted">{satMap.meaning} · {satMap.scene_date}{satMap.cloud_coverage_percent != null ? ` · ☁ ${satMap.cloud_coverage_percent}%` : ""}</small>
              </div>
              <div>
                <table className="sat-table">
                  <thead>
                    <tr>
                      <th></th>
                      <th>{t.table_status} <InfoTip term="zones" locale={locale} /></th>
                      <th>{t.table_range}</th>
                      <th>{t.sat_area}</th>
                      <th>{t.sat_share}</th>
                      <th>{t.sat_mean} <InfoTip term="mean" locale={locale} /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {satMap.zones.map((z: Json) => (
                      <tr key={z.id}>
                        <td><span className="swatch" style={{ background: z.color }} /></td>
                        <td><b>{z.simple_label || z.label}</b>{z.simple_label && z.simple_label !== z.label && <small className="muted block">{z.label}</small>}</td>
                        <td><code>{Number(z.min_val).toFixed(2)} – {Number(z.max_val).toFixed(2)}</code></td>
                        <td>{Number(z.area_acres).toFixed(2)} ac</td>
                        <td><b>{Number(z.percentage).toFixed(0)}%</b></td>
                        <td>{Number(z.median_val).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {satMap.field_status_narrative && <p className="sat-narrative"><Sparkles size={14} /> {satMap.field_status_narrative}</p>}
                <p className="muted small-text">{satMap.acquisition_note}</p>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Plan generator */}
      <div className="plan-bar">
        <p className="muted">{t.plan_desc}</p>
        <div className="plan-controls">
          <select value={season} onChange={e => handleSeasonChange(e.target.value)}>
            <option value="kharif">Kharif</option>
            <option value="rabi">Rabi</option>
            <option value="summer">Summer</option>
          </select>
          <input
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder={t.plan_question}
            maxLength={500}
          />
          <button className={`secondary mic ${planMic.recording ? "recording" : ""}`} onClick={planMic.toggle} aria-label={t.record}>
            {planMic.recording ? <MicOff size={16} /> : <Mic size={16} />}
          </button>
          <button className="primary" onClick={createPlan} disabled={generating}>
            {generating ? <RefreshCw size={16} className="spin" /> : <Sprout size={16} />}
            {generating ? t.plan_working : t.generate}
          </button>
        </div>
      </div>

      {result && (
        <article className="advisory">
          <div className="advisory-head">
            <span className={`plan-badge ${aiWritten ? "ai" : "rules"}`}>
              {aiWritten ? <Sparkles size={13} /> : null} {aiWritten ? `${t.plan_ai} · ${result.model}` : t.plan_rules}
            </span>
            <button className="listen-btn" onClick={() => speakText(result.summary, locale)}>
              <Volume2 size={15} /> {t.listen}
            </button>
          </div>
          <h3>{result.summary}</h3>
          <div className="option-grid">
            {result.options?.filter((o: Json) => o.eligible).slice(0, 3).map((o: Json) => (
              <div key={o.crop} className="option-card">
                <b>{o.crop_name || o.crop.replace("_", " ")}</b>
                <strong>{o.rank_score == null ? "—" : `${Math.round(o.rank_score * 100)}%`}</strong>
              </div>
            ))}
          </div>
          <h4>{t.actions_title}</h4>
          {result.actions?.map((a: Json) => (
            <div className="action-card" key={a.id}>
              <CheckCircle2 size={20} />
              <div style={{ flex: 1 }}>
                <b>{a.instruction}</b>
                <span>{a.timing.replace(/_/g, " ")} · {a.why}</span>
                {a.caution && <small>⚠ {a.caution}</small>}
                <div className="action-btns">
                  {a.status && a.status !== "proposed" ? (
                    <span className="action-status-pill">{t[`status_${a.status}`] || a.status}</span>
                  ) : (
                    <>
                      <button className="action-btn accept" onClick={() => act(a.id, "accepted")}><Check size={14} /> {t.accept}</button>
                      <button className="action-btn" onClick={() => act(a.id, "declined")}>{t.decline}</button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
          {result.uncertainty_reasons?.length > 0 && (
            <small className="advisory-uncertain">ⓘ {result.uncertainty_reasons.join(" · ")}</small>
          )}
        </article>
      )}

      {/* Krishi Mitra follow-up chat, grounded in this farm's weather advice */}
      <div className="chat-box">
        <div className="chat-head">
          <h3><Sparkles size={18} /> {t.chat_title}</h3>
          {chat.length > 0 && <button className="link-btn" onClick={endChat}>{t.end_chat}</button>}
        </div>
        {chat.length === 0 && (
          <div className="chat-chips">
            {[t.chat_q1, t.chat_q2, t.chat_q3].map(q => (
              <button key={q} onClick={() => sendChat(q)}>{q}</button>
            ))}
          </div>
        )}
        {chat.length > 0 && (
          <div className="chat-log">
            {chat.map((m, i) => (
              <div key={i} className={`chat-msg ${m.role}`}>
                <small>{m.role === "user" ? t.you : "Krishi Mitra"}</small>
                <div>{m.text}</div>
                {m.role === "assistant" && (
                  <button className="link-btn" onClick={() => speakText(m.text, locale)}><Volume2 size={13} /> {t.listen}</button>
                )}
              </div>
            ))}
            {chatLoading && <div className="chat-msg assistant muted"><RefreshCw size={12} className="spin" /> {t.thinking}</div>}
          </div>
        )}
        <div className="chat-input">
          <input
            value={chatInput}
            onChange={e => setChatInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && sendChat()}
            placeholder={t.chat_placeholder}
            disabled={chatLoading}
          />
          <button className={`secondary mic ${chatMic.recording ? "recording" : ""}`} onClick={chatMic.toggle} aria-label={t.record}>
            {chatMic.recording ? <MicOff size={16} /> : <Mic size={16} />}
          </button>
          <button className="primary" onClick={() => sendChat()} disabled={chatLoading || !chatInput.trim()}>{t.send}</button>
        </div>
        <small className="muted">{t.chat_privacy}</small>
      </div>

      <div className="pipeline-footer-nav">
        <button className="nav-prev-btn" onClick={() => go("crops")}>← {t.crops}</button>
        <button className="nav-next-btn" onClick={() => go("diagnose")}>{t.plant_doctor} <ArrowRight size={15} /></button>
      </div>
    </section>
  );
}
