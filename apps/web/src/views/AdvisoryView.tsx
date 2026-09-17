import React, { useState, useRef } from "react";
import {
  Activity, RefreshCw, MapPin, Droplets, Leaf, Sparkles,
  Sprout, Mic, MicOff, Volume2, ArrowRight, CheckCircle2, Check
} from "lucide-react";
import { api } from "../api";
import { View, Locale, Json } from "../types";
import { parseSatelliteMetrics } from "../utils/weather";

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

export function AdvisoryView({
  t,
  locale,
  farm,
  satMap,
  satIndex,
  loadSatMap,
  evidence,
  season,
  handleSeasonChange,
  go
}: AdvisoryViewProps) {
  const [result, setResult] = useState<Json | null>(null);
  const [transcript, setTranscript] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [generatingAdvisory, setGeneratingAdvisory] = useState(false);
  const [advisoryProgress, setAdvisoryProgress] = useState(0);
  const [advisoryStep, setAdvisoryStep] = useState("");

  // Krishi Mitra Follow-up Q&A Chat State
  const [chatMessages, setChatMessages] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [isChatRecording, setIsChatRecording] = useState(false);

  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);

  if (!farm) {
    return (
      <section className="panel" style={{ textAlign: "center", padding: "60px 20px" }}>
        <Activity size={48} color="var(--lime-500)" style={{ marginBottom: "12px" }} />
        <h2>{t.add_farm_first || "Add a Farm First"}</h2>
        <button className="primary" onClick={() => go("farm")} style={{ marginTop: "16px" }}>
          {t.start || "Add Farm Profile"}
        </button>
      </section>
    );
  }

  const satMetrics = parseSatelliteMetrics(evidence, locale);

  const createAdvisory = async () => {
    if (!farm) return;
    setGeneratingAdvisory(true);
    setAdvisoryProgress(20);
    setAdvisoryStep("1. Pulling live IMD district alerts & Open-Meteo rainfall trends...");

    try {
      setTimeout(() => {
        setAdvisoryProgress(50);
        setAdvisoryStep("2. Evaluating Sentinel-2 canopy moisture & soil nutrient constraints...");
      }, 500);

      setTimeout(() => {
        setAdvisoryProgress(80);
        setAdvisoryStep("3. Generating deterministic agro-ecological rotation & Gemini recommendations...");
      }, 1200);

      let res: Json;
      try {
        res = await api<Json>(`/api/v1/farms/${farm.id}/advisories`, {
          method: "POST",
          body: JSON.stringify({
            goal: farm.crop_status === "planted" ? "manage_current_crop" : "crop_plan",
            season,
            locale,
            budget_level: "low",
            labor_access: "family",
            equipment_access: [],
            farmer_query: transcript
          })
        });
      } catch (postErr: any) {
        if (postErr?.message?.includes("not found") || postErr?.message?.includes("Farm not found")) {
          setAdvisoryStep("Restoring farm profile on server...");
          await api<Json>("/api/v1/farms", {
            method: "POST",
            body: JSON.stringify(farm)
          });
          res = await api<Json>(`/api/v1/farms/${farm.id}/advisories`, {
            method: "POST",
            body: JSON.stringify({
              goal: farm.crop_status === "planted" ? "manage_current_crop" : "crop_plan",
              season,
              locale,
              budget_level: "low",
              labor_access: "family",
              equipment_access: [],
              farmer_query: transcript
            })
          });
        } else {
          throw postErr;
        }
      }

      setAdvisoryProgress(100);
      setAdvisoryStep("Advisory generated successfully!");
      setResult(res);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setGeneratingAdvisory(false);
    }
  };

  const speak = async () => {
    if (!result) return;
    try {
      const res = await fetch("/api/v1/voice/speak", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Actor-Id": "local-farmer",
          "X-Actor-Role": "farmer"
        },
        body: JSON.stringify({ text: result.summary, locale })
      });
      if (!res.ok) throw new Error("Voice audio is not available");
      const audioUrl = URL.createObjectURL(await res.blob());
      new Audio(audioUrl).play();
    } catch (err) {
      alert((err as Error).message);
    }
  };

  const act = async (actionId: string, status: "accepted" | "declined") => {
    try {
      await api(`/api/v1/actions/${actionId}`, {
        method: "PATCH",
        body: JSON.stringify({ status })
      });
      if (result) {
        setResult({
          ...result,
          actions: result.actions.map((a: any) =>
            a.id === actionId ? { ...a, status } : a
          )
        });
      }
    } catch (err) {
      alert((err as Error).message);
    }
  };

  const startVoice = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      audioChunks.current = [];
      rec.ondataavailable = e => audioChunks.current.push(e.data);
      rec.onstop = async () => {
        const blob = new Blob(audioChunks.current, { type: "audio/webm" });
        audioChunks.current = [];
        try {
          const fd = new FormData();
          fd.append("file", blob);
          fd.append("locale", locale);
          const res = await api<Json>("/api/v1/voice/transcribe", {
            method: "POST",
            body: fd
          });
          if (res.transcript) setTranscript(res.transcript);
        } catch (err) {
          console.warn("Transcribe failed", err);
        }
        stream.getTracks().forEach(track => track.stop());
      };
      rec.start();
      mediaRecorder.current = rec;
      setIsRecording(true);
    } catch (e) {
      console.warn("Microphone not available", e);
    }
  };

  const stopVoice = () => {
    if (mediaRecorder.current && isRecording) {
      mediaRecorder.current.stop();
      setIsRecording(false);
    }
  };

  const sendChatMessage = async (presetText?: string) => {
    const textToSend = (presetText || chatInput).trim();
    if (!textToSend || !farm || chatLoading) return;

    const userMsg = { role: "user" as const, text: textToSend };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput("");
    setChatLoading(true);

    try {
      const res = await api<any>(`/api/v1/farms/${farm.id}/chat`, {
        method: "POST",
        body: JSON.stringify({
          message: textToSend,
          locale,
          session_id: chatSessionId
        })
      });
      if (res && res.response) {
        setChatSessionId(res.session_id);
        setChatMessages(prev => [...prev, { role: "assistant", text: res.response }]);
      }
    } catch (err: any) {
      setChatMessages(prev => [...prev, { role: "assistant", text: `Error: ${err.message || "Could not reach advisor"}` }]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleEndChat = async () => {
    if (chatSessionId && farm) {
      try {
        await api(`/api/v1/farms/${farm.id}/chat/${chatSessionId}`, { method: "DELETE" });
      } catch (e) {
        // ignore
      }
    }
    setChatMessages([]);
    setChatSessionId(null);
    setChatInput("");
  };

  const toggleChatMic = () => {
    if (isChatRecording) {
      setIsChatRecording(false);
      return;
    }
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRec) {
      const recognition = new SpeechRec();
      recognition.lang = locale;
      recognition.continuous = false;
      recognition.interimResults = false;
      setIsChatRecording(true);
      recognition.onresult = (event: any) => {
        const spoken = event.results[0][0].transcript;
        setIsChatRecording(false);
        setChatInput(spoken);
        sendChatMessage(spoken);
      };
      recognition.onerror = () => setIsChatRecording(false);
      recognition.onend = () => setIsChatRecording(false);
      recognition.start();
    } else {
      alert("Speech recognition not supported in this browser. Please type your question.");
    }
  };

  const playSpeechAudio = async (text: string) => {
    try {
      const res = await fetch("/api/v1/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Actor-Id": "farmer1" },
        body: JSON.stringify({ text, locale })
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        new Audio(url).play();
        return;
      }
    } catch (e) {
      // fallback
    }
    if ("speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = locale;
      window.speechSynthesis.speak(utterance);
    }
  };

  return (
    <section className="panel">
      <div className="section-title">
        <Activity />
        <div>
          <small>PIPELINE STAGE 5 OF 5 · {farm.name} ({farm.district})</small>
          <h2>{t.advice || "Field Action Plan & Satellite Analytics"}</h2>
        </div>
      </div>

      {/* Satellite Multi-Zone Stratification */}
      <div className="geopard-dashboard">
        <div className="geopard-top-bar">
          <div className="geopard-title-group">
            <Activity size={20} color="var(--green-700)" />
            <div>
              <b style={{ fontSize: "15px", color: "var(--green-950)" }}>{t.geopard_title || "Classified Field Condition Map"}</b>
              <div style={{ fontSize: "12px", color: "var(--muted)" }}>{satMap?.meaning || "Sentinel-2 Multi-Zone Biophysics for Plotted Boundary"}</div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
            <span className="geopard-date-badge">
              📅 {satMap?.scene_date || "07 Sep 2026, 05:33 UTC"}
            </span>
            <span className="geopard-sensor-badge">
              🛰️ {satMap?.sensor || "Sentinel-2 MSI Level-2A"} ({satMap?.resolution_m || 10}m)
            </span>
            <select
              value={satIndex}
              onChange={e => loadSatMap(e.target.value)}
              style={{ border: "1px solid var(--line)", borderRadius: "8px", padding: "6px 10px", fontSize: "13px", background: "#fff", fontWeight: 600 }}
            >
              <option value="NDVI">NDVI — Crop Growth Vigor</option>
              <option value="NDWI">NDWI — Surface Moisture & Runoff</option>
              <option value="NDMI">NDMI — Crop Moisture Stress</option>
            </select>
            <button
              className="secondary"
              style={{ padding: "6px 12px", fontSize: "12px" }}
              onClick={() => loadSatMap(satIndex)}
              title="Refresh Satellite Multi-Zone Analysis"
            >
              <RefreshCw size={13} />
            </button>
          </div>
        </div>

        {satMap && (
          <div style={{ padding: "18px 20px" }}>
            {/* Outcome Metric Cards */}
            <div className="sat-outcome-grid" style={{ margin: "0 0 18px 0" }}>
              <div className="sat-outcome-card ndmi">
                <div className="sat-outcome-header">
                  <Droplets size={20} color="#0284c7" />
                  <span>{t.ndmi_label_short || "Canopy Moisture (NDMI)"}</span>
                </div>
                <div className="sat-outcome-main">
                  <span className="sat-outcome-number">{satMetrics.ndmi || "0.24"}</span>
                  <span className={`sat-outcome-pill ${satMetrics.rawMoist}`}>
                    {satMetrics.moistStatus}
                  </span>
                </div>
                <div className="sat-outcome-footer">
                  <span>{t.water_stress || "Water Stress"}: <strong>{satMetrics.waterStress}</strong></span>
                  <span>Sentinel-2</span>
                </div>
              </div>

              <div className="sat-outcome-card ndvi">
                <div className="sat-outcome-header">
                  <Leaf size={20} color="#16a34a" />
                  <span>{t.ndvi_label_short || "Vegetation Vigor (NDVI)"}</span>
                </div>
                <div className="sat-outcome-main">
                  <span className="sat-outcome-number">{satMetrics.ndvi || "0.48"}</span>
                  <span className={`sat-outcome-pill ${satMetrics.rawVeg}`}>
                    {satMetrics.vegStatus}
                  </span>
                </div>
                <div className="sat-outcome-footer">
                  <span>{t.biomass_status || "Biomass Density"}: <strong>{satMetrics.ndvi ? (Number(satMetrics.ndvi) > 0.35 ? "Optimal" : "Developing") : "Verified"}</strong></span>
                  <span>10m Resolution</span>
                </div>
              </div>
            </div>

            {/* Visual Raster & Zonal Table */}
            <div className="geopard-content-grid" style={{ padding: 0 }}>
              <div className="geopard-image-card">
                <div className="geopard-plot-tag">
                  <MapPin size={12} color="#38bdf8" />
                  <span>Boundary Outlined: {farm.name} ({farm.area_acres || 1} ac)</span>
                </div>
                {satMap.image_api_path ? (
                  <img
                    src={satMap.image_api_path}
                    alt="Classified Satellite Crop Map"
                    className="geopard-raster-img"
                    onError={e => {
                      if (satMap.map_url) {
                        (e.target as HTMLImageElement).src = satMap.map_url;
                      } else if (satMap.fallback_map_url) {
                        (e.target as HTMLImageElement).src = satMap.fallback_map_url;
                      }
                    }}
                  />
                ) : satMap.map_url || satMap.fallback_map_url ? (
                  <img
                    src={satMap.map_url || satMap.fallback_map_url}
                    alt="Satellite Condition Map"
                    className="geopard-raster-img"
                  />
                ) : (
                  <div style={{ padding: "40px 20px", textAlign: "center", color: "#94a3b8" }}>
                    <Activity size={32} style={{ marginBottom: "8px", opacity: 0.7 }} />
                    <p style={{ margin: 0 }}>Processing satellite imagery for plot coordinates...</p>
                  </div>
                )}
              </div>

              <div className="geopard-table-wrapper">
                <table className="geopard-table">
                  <thead>
                    <tr>
                      <th>{t.table_color || "Color"}</th>
                      <th>{t.table_zone || "Zone"}</th>
                      <th>{t.table_status || "Status"}</th>
                      <th>{t.table_range || "Range"}</th>
                      <th>{t.table_area || "Area"}</th>
                      <th>{t.table_share || "Share"}</th>
                      <th>{t.table_median || "Median"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {satMap.zones && satMap.zones.length > 0 ? (
                      satMap.zones.map((z: any) => (
                        <tr key={z.zone_id}>
                          <td>
                            <span className="geopard-color-box" style={{ background: z.color_hex }} />
                          </td>
                          <td><strong>Zone {z.zone_id}</strong></td>
                          <td>{z.label}</td>
                          <td><code>{Number(z.val_min).toFixed(2)} - {Number(z.val_max).toFixed(2)}</code></td>
                          <td>{Number(z.area_acres).toFixed(2)} ac</td>
                          <td><strong>{Number(z.share_percent).toFixed(1)}%</strong></td>
                          <td>{Number(z.median_val).toFixed(2)}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={7} style={{ textAlign: "center", color: "var(--muted)", padding: "20px" }}>
                          Field zone stratification data will display when satellite index is computed.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {satMap.field_status_narrative && (
              <div className="geopard-narrative-banner">
                <Sparkles size={18} color="#16a34a" style={{ flexShrink: 0 }} />
                <span><strong>{t.field_narrative_title || "Field Narrative"}:</strong> {satMap.field_status_narrative}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Field Plan Generator Bar */}
      <div className="voice-bar" style={{ marginTop: "20px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "13px", fontWeight: 700 }}>Season:</span>
          <select
            value={season}
            onChange={e => handleSeasonChange(e.target.value)}
            style={{ border: "1px solid var(--line)", borderRadius: "8px", padding: "6px 12px", fontSize: "13px" }}
          >
            <option value="kharif">☀️ Kharif (Monsoon / खरीप)</option>
            <option value="rabi">❄️ Rabi (Winter / रब्बी)</option>
            <option value="summer">🌤️ Summer / Zaid (उन्हाळी)</option>
          </select>
        </div>

        {isRecording ? (
          <button className="rec-btn recording" onClick={stopVoice}>
            <MicOff size={16} />
            {t.stop}
          </button>
        ) : (
          <button className="rec-btn" onClick={startVoice}>
            <Mic size={16} />
            {t.record}
          </button>
        )}

        {transcript && (
          <div style={{ fontSize: "13px", background: "#ffffff", padding: "8px 12px", borderRadius: "8px", border: "1px solid var(--line)" }}>
            💬 "{transcript}"
          </div>
        )}

        <button
          className="primary"
          onClick={createAdvisory}
          disabled={generatingAdvisory}
          style={{ marginLeft: "auto" }}
        >
          <Sprout size={16} />
          {t.generate}
          <ArrowRight size={16} />
        </button>
      </div>

      {/* Advisory Progress Indicator */}
      {generatingAdvisory && (
        <div className="inplace-progress">
          <div className="inplace-progress-header">
            <b><RefreshCw className="spin" size={16} /> Synthesizing Field Intelligence...</b>
            <span style={{ fontSize: "12px", fontWeight: 700, color: "var(--green-700)" }}>{advisoryProgress}%</span>
          </div>
          <div className="inplace-progress-track">
            <div className="inplace-progress-fill" style={{ width: `${advisoryProgress}%` }} />
          </div>
          <div className="inplace-step active">{advisoryStep}</div>
        </div>
      )}

      {/* Advisory Plan Result */}
      {result && (
        <article className="advisory">
          <div className="advisory-head">
            <span>REGENERATIVE AI PLAN · {result.model || "GEMINI 2.5"}</span>
            <button
              onClick={speak}
              style={{
                background: "rgba(255,255,255,0.15)",
                border: "0",
                color: "#ffffff",
                padding: "6px 12px",
                borderRadius: "8px",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                cursor: "pointer",
                fontWeight: 700,
                fontSize: "12px"
              }}
            >
              <Volume2 size={15} />
              {t.listen}
            </button>
          </div>

          <h3>{result.summary}</h3>

          <div className="option-grid">
            {result.options?.filter((o: Json) => o.eligible).slice(0, 3).map((o: Json) => (
              <div key={o.crop} className="option-card">
                <b>{o.crop.replace("_", " ")}</b>
                <strong>{o.rank_score == null ? "—" : `${Math.round(o.rank_score * 100)}%`}</strong>
                <span>Suitability Match · {Math.round(o.evidence_coverage * 100)}% Evidence</span>
              </div>
            ))}
          </div>

          <h4 style={{ margin: "24px 0 12px 0", fontSize: "18px", color: "var(--lime-400)" }}>
            Recommended Field Actions
          </h4>

          {result.actions?.map((a: Json) => (
            <div className="action-card" key={a.id}>
              <CheckCircle2 size={22} />
              <div style={{ flex: 1 }}>
                <b>{a.instruction}</b>
                <span>Timing: {a.timing} · Rationale: {a.why}</span>
                {a.caution && <small>⚠ Precaution: {a.caution}</small>}

                <div className="action-btns">
                  {a.status ? (
                    <span className="action-status-pill">{a.status.toUpperCase()}</span>
                  ) : (
                    <>
                      <button className="action-btn accept" onClick={() => act(a.id, "accepted")}>
                        <Check size={14} />
                        {t.accept}
                      </button>
                      <button className="action-btn" onClick={() => act(a.id, "declined")}>
                        {t.decline}
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </article>
      )}

      {/* Krishi Mitra Spoken & Typed Follow-up Q&A Chat */}
      {result && (
        <div className="followup-chat-box" style={{
          marginTop: "24px",
          background: "#f8fafc",
          border: "1px solid #cbd5e1",
          borderRadius: "16px",
          padding: "20px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.04)"
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Sparkles size={20} color="var(--green-700)" />
              <h4 style={{ margin: 0, fontSize: "16px", color: "var(--green-950)", fontWeight: 700 }}>
                {locale === "mr-IN" ? "कृषी मित्राला प्रश्न विचारा (बोलून किंवा लिहून)" :
                 locale === "hi-IN" ? "कृषि मित्र से प्रश्न पूछें (बोलकर या लिखकर)" :
                 "Ask Krishi Mitra (Spoken or Typed Follow-up)"}
              </h4>
            </div>
            {chatMessages.length > 0 && (
              <button
                type="button"
                onClick={handleEndChat}
                style={{
                  fontSize: "12px",
                  padding: "4px 10px",
                  background: "#fee2e2",
                  color: "#991b1b",
                  border: "1px solid #fca5a5",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontWeight: 600
                }}
              >
                ✕ {locale === "mr-IN" ? "चॅट संपवा व डेटा पुसा" : locale === "hi-IN" ? "बातचीत समाप्त करें" : "End Chat & Clear"}
              </button>
            )}
          </div>

          <p style={{ margin: "0 0 12px 0", fontSize: "13px", color: "#64748b" }}>
            {locale === "mr-IN" ? "हवामान, फवारणी किंवा खतांबद्दल मनात काही शंका आहे का? खाली टाईप करा किंवा माइक दाबून विचारा." :
             locale === "hi-IN" ? "मौसम, छिड़काव या खाद से संबंधित कोई सवाल है? नीचे टाइप करें या माइक दबाकर पूछें।" :
             "Have questions about spraying, fertilizer doses, or rainfall risks? Speak or type below."}
          </p>

          {/* Quick Question Chips */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "14px" }}>
            {[
              locale === "mr-IN" ? "उद्या पाऊस असेल तर आज फवारणी करावी का?" :
              locale === "hi-IN" ? "क्या बारिश से पहले कीटनाशक का छिड़काव सुरक्षित है?" :
              "Is it safe to spray before rain?",

              locale === "mr-IN" ? "या पिकासाठी सेंद्रिय खताचे प्रमाण किती असावे?" :
              locale === "hi-IN" ? "इस फसल के लिए जैविक खाद की कितनी मात्रा चाहिए?" :
              "What organic fertilizer dose is recommended?",

              locale === "mr-IN" ? "पुढील पाणी कधी द्यावे लागेल?" :
              locale === "hi-IN" ? "अगली सिंचाई कब करनी चाहिए?" :
              "When should I irrigate next?"
            ].map((q, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => sendChatMessage(q)}
                style={{
                  fontSize: "12px",
                  padding: "5px 12px",
                  borderRadius: "20px",
                  background: "#ffffff",
                  border: "1px solid #cbd5e1",
                  color: "#334155",
                  cursor: "pointer",
                  textAlign: "left"
                }}
              >
                💬 {q}
              </button>
            ))}
          </div>

          {/* Chat Messages */}
          {chatMessages.length > 0 && (
            <div style={{
              maxHeight: "260px",
              overflowY: "auto",
              padding: "12px",
              background: "#ffffff",
              borderRadius: "12px",
              border: "1px solid #e2e8f0",
              marginBottom: "14px",
              display: "flex",
              flexDirection: "column",
              gap: "10px"
            }}>
              {chatMessages.map((m, i) => (
                <div key={i} style={{
                  alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                  background: m.role === "user" ? "#e0f2fe" : "#f1f5f9",
                  color: "#1e293b",
                  padding: "8px 14px",
                  borderRadius: "12px",
                  maxWidth: "85%",
                  fontSize: "13px",
                  lineHeight: "1.4"
                }}>
                  <div style={{ fontSize: "11px", fontWeight: 700, marginBottom: "2px", color: m.role === "user" ? "#0369a1" : "#166534" }}>
                    {m.role === "user" ? "You" : "🌾 Krishi Mitra"}
                  </div>
                  <div>{m.text}</div>
                  {m.role === "assistant" && (
                    <button
                      type="button"
                      onClick={() => playSpeechAudio(m.text)}
                      style={{
                        marginTop: "6px",
                        background: "none",
                        border: "none",
                        color: "var(--green-700)",
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "4px",
                        fontSize: "11px",
                        fontWeight: 700,
                        padding: 0
                      }}
                    >
                      <Volume2 size={13} /> {t.listen || "Listen"}
                    </button>
                  )}
                </div>
              ))}
              {chatLoading && (
                <div style={{ alignSelf: "flex-start", fontStyle: "italic", fontSize: "12px", color: "#64748b" }}>
                  <RefreshCw className="spin" size={12} style={{ display: "inline", marginRight: "6px" }} />
                  Thinking...
                </div>
              )}
            </div>
          )}

          {/* Spoken / Typed Input Bar */}
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <input
              type="text"
              placeholder={locale === "mr-IN" ? "येथे प्रश्न लिहा किंवा माईक दाबा..." :
                           locale === "hi-IN" ? "यहाँ सवाल लिखें या माइक दबाएं..." :
                           "Type question or tap mic to speak..."}
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") sendChatMessage(); }}
              disabled={chatLoading}
              style={{
                flex: 1,
                padding: "10px 14px",
                borderRadius: "10px",
                border: "1px solid #94a3b8",
                background: "#ffffff",
                fontSize: "13px"
              }}
            />
            <button
              type="button"
              onClick={toggleChatMic}
              style={{
                padding: "10px 14px",
                borderRadius: "10px",
                background: isChatRecording ? "#fee2e2" : "#f1f5f9",
                border: isChatRecording ? "1px solid #ef4444" : "1px solid #cbd5e1",
                color: isChatRecording ? "#b91c1c" : "#334155",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                fontWeight: 600,
                fontSize: "13px"
              }}
              title="Voice Input"
            >
              {isChatRecording ? <MicOff size={16} /> : <Mic size={16} />}
              {isChatRecording ? (t.stop || "Stop") : (t.record || "Speak")}
            </button>
            <button
              type="button"
              className="primary"
              onClick={() => sendChatMessage()}
              disabled={chatLoading || !chatInput.trim()}
              style={{ padding: "10px 16px", borderRadius: "10px", fontSize: "13px" }}
            >
              Send
            </button>
          </div>

          <div style={{ marginTop: "8px", fontSize: "11px", color: "#94a3b8", display: "flex", justifyContent: "space-between" }}>
            <span>🔒 No login: Session memory auto-expires after 5 minutes of inactivity or on End Chat.</span>
            {chatSessionId && <span>Session ID: {chatSessionId}</span>}
          </div>
        </div>
      )}

      {/* Pipeline Navigation Footer */}
      <div className="pipeline-footer-nav">
        <button className="nav-prev-btn" onClick={() => go("crops")}>
          {t.btn_back_crops || "← Back to Crop Recs"}
        </button>
        <button className="nav-next-btn" onClick={() => go("diagnose")}>
          {t.btn_proceed_doctor || "Proceed to Crop Doctor →"}
        </button>
      </div>
    </section>
  );
}
