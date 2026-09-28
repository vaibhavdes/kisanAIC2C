import React, { FormEvent, useEffect, useState } from "react";
import { BarChart3, BookOpen, ClipboardList, KeyRound, Network, RefreshCw } from "lucide-react";
import { api, apiBlob, expertCode, setExpertCode } from "../api";
import { useCropName } from "../hooks";
import { Json, Locale, T } from "../types";
import { ErrorNote, formatDate, Loading, StageHeader, StatusPill } from "../components/ui";

type Tab = "dashboard" | "cases" | "practices" | "network";

export function ExpertView({ t, locale }: { t: T; locale: Locale }) {
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [tab, setTab] = useState<Tab>("dashboard");

  const check = async () => {
    try {
      await api("/api/v1/expert/packs", {}, true);
      setAllowed(true);
    } catch {
      setAllowed(false);
    }
  };
  useEffect(() => { check(); }, []);

  if (allowed === null) return <Loading label={t("loading")} />;
  if (!allowed) return <AccessGate t={t} onDone={check} />;

  const tabs: Array<{ id: Tab; icon: React.ReactNode; label: string }> = [
    { id: "dashboard", icon: <BarChart3 size={16} />, label: t("ex_tab_dashboard") },
    { id: "cases", icon: <ClipboardList size={16} />, label: t("ex_tab_cases") },
    { id: "practices", icon: <BookOpen size={16} />, label: t("ex_tab_practices") },
    { id: "network", icon: <Network size={16} />, label: t("ex_tab_network") },
  ];
  return (
    <section className="panel">
      <StageHeader icon={<BookOpen />} title={t("expert_title")} subtitle={t("expert_sub")} />
      <div className="tab-row">
        {tabs.map((item) => (
          <button key={item.id} className={`tab-btn ${tab === item.id ? "active" : ""}`} onClick={() => setTab(item.id)}>{item.icon} {item.label}</button>
        ))}
        {expertCode() && <button className="link-btn" onClick={() => { setExpertCode(null); setAllowed(false); }}>{t("ex_sign_out")}</button>}
      </div>
      {tab === "dashboard" && <Dashboard t={t} />}
      {tab === "cases" && <Cases t={t} locale={locale} />}
      {tab === "practices" && <Practices t={t} />}
      {tab === "network" && <NetworkTab t={t} locale={locale} />}
    </section>
  );
}

function AccessGate({ t, onDone }: { t: T; onDone: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setExpertCode(code.trim());
    try {
      await api("/api/v1/expert/packs", {}, true);
      onDone();
    } catch (err) {
      setExpertCode(null);
      setError((err as Error).message);
    }
  };
  return (
    <section className="panel narrow">
      <StageHeader icon={<KeyRound />} title={t("expert_title")} subtitle={t("ex_gate_desc")} />
      <form className="form-block" onSubmit={submit}>
        <label className="field">
          <span>{t("ex_access_code")}</span>
          <input type="password" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" required />
        </label>
        {error && <ErrorNote t={t} message={error} />}
        <button className="primary" type="submit">{t("ex_enter")}</button>
      </form>
    </section>
  );
}

function useExpert<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setData(await api<T>(path, {}, true));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [path]);
  return { data, error, loading, reload: load };
}

// ------------------------------------------------------------------ dashboard
function Dashboard({ t }: { t: T }) {
  const dash = useExpert<Json>("/api/v1/expert/dashboard");
  const [brief, setBrief] = useState<Json | null>(null);
  const [briefBusy, setBriefBusy] = useState(false);
  const d = dash.data;
  const makeBrief = async () => {
    setBriefBusy(true);
    try {
      setBrief(await api<Json>("/api/v1/expert/dashboard/brief", { method: "POST" }, true));
    } catch (err) {
      setBrief({ brief: null, reason: (err as Error).message });
    } finally {
      setBriefBusy(false);
    }
  };
  if (dash.loading && !d) return <Loading label={t("loading")} />;
  if (dash.error) return <ErrorNote t={t} message={dash.error} onRetry={dash.reload} />;
  if (!d) return null;
  return (
    <div className="dashboard">
      <div className="kpi-row">
        {Object.entries(d.totals).map(([key, value]) => (
          <div key={key} className="kpi"><b>{String(value)}</b><span>{t(`kpi_${key}`)}</span></div>
        ))}
      </div>
      <div className="card-block">
        <div className="block-head">
          <h3>{t("ex_ai_brief")}</h3>
          <button className="secondary small" onClick={makeBrief} disabled={briefBusy}>{briefBusy ? t("working") : t("ex_make_brief")}</button>
        </div>
        {brief && (brief.brief ? <pre className="brief">{brief.brief}</pre> : <p className="muted">{brief.reason}</p>)}
      </div>
      <DataTable t={t} title={t("ex_reports_by_district")} rows={d.diagnoses_by_district} cols={["district", "crop", "category", "reports"]} empty={t("ex_no_reports")} />
      <DataTable t={t} title={t("ex_top_conditions")} rows={d.top_conditions} cols={["condition", "reports"]} empty={t("ex_no_reports")} />
      <DataTable t={t} title={t("ex_practice_adoption")} rows={d.practice_adoption} cols={["name", "accepted", "declined", "worked", "partly", "did_not_work"]} empty={t("ex_no_adoption")} />
      <DataTable t={t} title={t("ex_farms_by_district")} rows={d.farms_by_district} cols={["state", "district", "farms"]} empty={t("ex_no_farms")} />
      <div className="card-block subtle">
        <h4>{t("ex_shared_signals")}</h4>
        <p className="muted">{t("ex_shared_signals_desc", { n: d.minimum_group_size })}</p>
        {d.shared_signals_preview.length ? (
          <ul>{d.shared_signals_preview.map((s: Json, i: number) => <li key={i}>{s.district} · {s.crop} · {s.category}: {s.reports}</li>)}</ul>
        ) : <p className="muted">{t("ex_no_signals")}</p>}
      </div>
    </div>
  );
}

function DataTable({ t, title, rows, cols, empty }: { t: T; title: string; rows: Json[]; cols: string[]; empty: string }) {
  return (
    <div className="card-block">
      <h3>{title}</h3>
      {rows.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr>{cols.map((c) => <th key={c}>{t(`col_${c}`)}</th>)}</tr></thead>
            <tbody>{rows.map((row, i) => <tr key={i}>{cols.map((c) => <td key={c}>{String(row[c] ?? "")}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : <p className="muted">{empty}</p>}
    </div>
  );
}

// ------------------------------------------------------------------ cases
function Cases({ t, locale }: { t: T; locale: Locale }) {
  const cases = useExpert<Json[]>("/api/v1/expert/cases");
  if (cases.loading && !cases.data) return <Loading label={t("loading")} />;
  if (cases.error) return <ErrorNote t={t} message={cases.error} onRetry={cases.reload} />;
  if (!cases.data?.length) return <p className="muted">{t("ex_no_cases")}</p>;
  return (
    <div className="case-grid">
      {cases.data.map((c) => <CaseCard key={c.id} t={t} locale={locale} item={c} onChange={cases.reload} />)}
    </div>
  );
}

function CaseCard({ t, locale, item, onChange }: { t: T; locale: Locale; item: Json; onChange: () => void }) {
  const [image, setImage] = useState<string | null>(null);
  const [text, setText] = useState(item.review_text || "");
  const [error, setError] = useState("");
  const d = item.diagnosis || {};
  const cropName = useCropName(locale);
  useEffect(() => {
    if (!item.image_path) return;
    let url: string | null = null;
    apiBlob(item.image_path, {}, true).then((blob) => { url = URL.createObjectURL(blob); setImage(url); }).catch(() => undefined);
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [item.image_path]);
  const save = async (status: string) => {
    setError("");
    try {
      await api(`/api/v1/expert/cases/${item.id}`, { method: "PATCH", body: JSON.stringify({ version: item.version, status, review_text: text }) }, true);
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <article className="case-card">
      {image && <img src={image} alt={t("leaf_photo")} />}
      <div>
        <div className="block-head">
          <span><b>{d.suspected_condition || t("no_clear_problem")}</b>{d.condition_en && d.condition_en !== d.suspected_condition && <small> ({d.condition_en})</small>}</span>
          <StatusPill status={item.status === "resolved" ? "good" : "fair"} label={t(`case_${item.status}`)} />
        </div>
        <small className="muted">{formatDate(item.created_at, locale, true)} · {d.district || t("no_location")} · {d.crop === "auto-detect" ? d.detected_crop || "-" : cropName(d.crop)} · {t(`confidence_${d.confidence || "low"}`)}</small>
        {d.visible_findings?.length > 0 && <p>{d.visible_findings.join("; ")}</p>}
        {d.uncertainty_reasons?.length > 0 && <p className="muted">{d.uncertainty_reasons.join("; ")}</p>}
        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("ex_reply_placeholder")} rows={3} />
        {error && <ErrorNote t={t} message={error} />}
        <div className="action-btns">
          <button className="small secondary" disabled={text.trim().length < 3} onClick={() => save("in_review")}>{t("ex_save_note")}</button>
          <button className="small primary" disabled={text.trim().length < 3} onClick={() => save("resolved")}>{t("ex_send_resolve")}</button>
        </div>
      </div>
    </article>
  );
}

// ------------------------------------------------------------------ practices
function Practices({ t }: { t: T }) {
  const list = useExpert<Json[]>("/api/v1/expert/practices");
  const [exported, setExported] = useState<Json | null>(null);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState({ title: "", summary: "", crops: "", states: "", seasons: "kharif", water: "rainfed", steps: "", contra: "", urls: "", code: "" });

  const act = async (fn: () => Promise<unknown>) => {
    setError("");
    try {
      await fn();
      await list.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const lines = (value: string) => value.split("\n").map((s) => s.trim()).filter(Boolean);
  const csv = (value: string) => value.split(",").map((s) => s.trim()).filter(Boolean);
  const create = (e: FormEvent) => {
    e.preventDefault();
    act(() => api("/api/v1/expert/practices", {
      method: "POST",
      body: JSON.stringify({
        title: draft.title, summary: draft.summary, crops: csv(draft.crops), state_codes: csv(draft.states).map((s) => s.toUpperCase()),
        seasons: csv(draft.seasons), water_contexts: csv(draft.water), steps: lines(draft.steps), contraindications: lines(draft.contra),
        source_urls: lines(draft.urls), license: "CC-BY-4.0", practice_code: draft.code || null,
      }),
    }, true).then(() => setDraft({ ...draft, title: "", summary: "", steps: "", contra: "", urls: "" })));
  };

  return (
    <div>
      {error && <ErrorNote t={t} message={error} />}
      {list.loading && !list.data && <Loading label={t("loading")} />}
      <div className="practice-list">
        {(list.data || []).map((p) => (
          <article key={p.id} className="practice-card">
            <div className="block-head">
              <h4>{p.title}</h4>
              <StatusPill status={p.review_status === "reviewed" ? "good" : "fair"} label={t(`review_${p.review_status}`)} />
              {p.created_by?.startsWith("imported:") && <span className="muted">{t("imported_from", { node: p.created_by.slice(9) })}</span>}
            </div>
            <p>{p.summary}</p>
            <small className="muted">{p.crops.join(", ")} · {p.state_codes.join(", ")} · {p.seasons.join(", ")}</small>
            <div className="action-btns">
              {p.review_status !== "reviewed" ? (
                <button className="small primary" onClick={() => act(() => api(`/api/v1/expert/practices/${p.id}/review`, { method: "POST", body: JSON.stringify({ approve: true, note: "Reviewed" }) }, true))}>{t("ex_approve")}</button>
              ) : (
                <button className="small secondary" onClick={() => act(async () => setExported(await api(`/api/v1/expert/practices/${p.id}/export`, {}, true)))}>{t("ex_export")}</button>
              )}
            </div>
          </article>
        ))}
      </div>
      {exported && (
        <div className="card-block">
          <div className="block-head">
            <h4>{t("ex_bundle")}</h4>
            <button className="small secondary" onClick={() => navigator.clipboard?.writeText(JSON.stringify(exported, null, 2))}>{t("ex_copy")}</button>
            <button className="link-btn" onClick={() => setExported(null)}>{t("close")}</button>
          </div>
          <pre className="json-view">{JSON.stringify(exported, null, 2)}</pre>
        </div>
      )}
      <form className="card-block" onSubmit={create}>
        <h3>{t("ex_new_practice")}</h3>
        <div className="form-grid">
          <label className="field"><span>{t("ex_f_title")}</span><input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} required minLength={3} /></label>
          <label className="field"><span>{t("ex_f_code")}</span><input value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} placeholder="legume-rotation" /></label>
          <label className="field"><span>{t("ex_f_crops")}</span><input value={draft.crops} onChange={(e) => setDraft({ ...draft, crops: e.target.value })} placeholder="chickpea, wheat" required /></label>
          <label className="field"><span>{t("ex_f_states")}</span><input value={draft.states} onChange={(e) => setDraft({ ...draft, states: e.target.value })} placeholder="MH, PB" /></label>
          <label className="field"><span>{t("ex_f_seasons")}</span><input value={draft.seasons} onChange={(e) => setDraft({ ...draft, seasons: e.target.value })} /></label>
          <label className="field"><span>{t("ex_f_water")}</span><input value={draft.water} onChange={(e) => setDraft({ ...draft, water: e.target.value })} /></label>
        </div>
        <label className="field"><span>{t("ex_f_summary")}</span><textarea value={draft.summary} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} required minLength={10} rows={2} /></label>
        <label className="field"><span>{t("ex_f_steps")}</span><textarea value={draft.steps} onChange={(e) => setDraft({ ...draft, steps: e.target.value })} required rows={3} /></label>
        <label className="field"><span>{t("ex_f_contra")}</span><textarea value={draft.contra} onChange={(e) => setDraft({ ...draft, contra: e.target.value })} required rows={2} /></label>
        <label className="field"><span>{t("ex_f_urls")}</span><textarea value={draft.urls} onChange={(e) => setDraft({ ...draft, urls: e.target.value })} required rows={2} placeholder="https://" /></label>
        <button className="primary" type="submit">{t("ex_save_draft")}</button>
      </form>
    </div>
  );
}

// ------------------------------------------------------------------ network
function NetworkTab({ t, locale }: { t: T; locale: Locale }) {
  const packs = useExpert<Json[]>("/api/v1/expert/packs");
  const peers = useExpert<Json>("/api/v1/expert/network/peers");
  const imports = useExpert<Json[]>("/api/v1/expert/exchange/imports");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [paste, setPaste] = useState("");

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setError("");
    setNotice("");
    try {
      await fn();
      setNotice(ok);
      await Promise.all([packs.reload(), imports.reload()]);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const importFromPeer = (peer: string, kind: string, id: string) =>
    run(() => api("/api/v1/expert/network/import", { method: "POST", body: JSON.stringify({ peer_url: peer, kind, item_id: id }) }, true), t("ex_imported_for_review"));
  const importPasted = () => run(async () => {
    let parsed: Json;
    try {
      parsed = JSON.parse(paste);
    } catch {
      throw new Error(t("ex_invalid_json"));
    }
    await api("/api/v1/expert/exchange/imports", { method: "POST", body: JSON.stringify(parsed) }, true);
    setPaste("");
  }, t("ex_imported_for_review"));
  const review = (id: string, approve: boolean) =>
    run(() => api(`/api/v1/expert/exchange/imports/${id}`, { method: "PATCH", body: JSON.stringify({ approve, note: approve ? "Approved after local review" : "Rejected after local review" }) }, true),
      approve ? t("ex_approved") : t("ex_rejected"));

  return (
    <div>
      {error && <ErrorNote t={t} message={error} />}
      {notice && <div className="info-banner ok">{notice}</div>}

      <div className="card-block">
        <h3>{t("ex_packs_here")}</h3>
        <p className="muted">{t("ex_packs_desc")}</p>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>{t("col_region")}</th><th>{t("col_version")}</th><th>{t("col_crops")}</th><th>{t("col_origin")}</th><th>{t("col_review")}</th></tr></thead>
            <tbody>
              {(packs.data || []).map((p) => (
                <tr key={`${p.pack_id}-${p.origin}`}>
                  <td>{p.name} ({p.subdivision_code})</td>
                  <td>v{p.pack_version}</td>
                  <td>{p.crops}</td>
                  <td>{p.origin === "imported" ? t("imported_from", { node: p.origin_node }) : t("ex_published_here")}</td>
                  <td>{t(`review_${p.review_status}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card-block">
        <div className="block-head">
          <h3>{t("ex_peers")}</h3>
          <button className="secondary small" onClick={peers.reload}><RefreshCw size={14} /> {t("refresh")}</button>
        </div>
        {peers.loading && !peers.data && <Loading label={t("loading")} />}
        {peers.data && !peers.data.peers.length && <p className="muted">{t("ex_no_peers")}</p>}
        {(peers.data?.peers || []).map((peer: Json) => (
          <div key={peer.url} className="peer-card">
            <div className="block-head">
              <b>{peer.manifest?.label || peer.url}</b>
              <StatusPill status={peer.status === "online" ? "good" : "blocking"} label={t(`peer_${peer.status}`)} />
              <small className="muted">{peer.url}</small>
            </div>
            {peer.manifest && (
              <>
                <p className="muted">{peer.manifest.privacy}</p>
                <ul className="peer-items">
                  {peer.manifest.packs.map((p: Json) => (
                    <li key={p.pack_id}>
                      <span>{t("ex_pack_item", { name: p.name, version: p.pack_version, crops: p.crops })}</span>
                      <button className="small secondary" onClick={() => importFromPeer(peer.url, "packs", p.pack_id)}>{t("ex_import")}</button>
                    </li>
                  ))}
                  {peer.manifest.practices.map((p: Json) => (
                    <li key={p.bundle_id}>
                      <span>{t("ex_practice_item", { title: p.title })}</span>
                      <button className="small secondary" onClick={() => importFromPeer(peer.url, "practices", p.bundle_id)}>{t("ex_import")}</button>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {peer.error && <p className="muted">{peer.error}</p>}
          </div>
        ))}
      </div>

      <div className="card-block">
        <h3>{t("ex_review_queue")}</h3>
        {!(imports.data || []).length && <p className="muted">{t("ex_no_imports")}</p>}
        {(imports.data || []).map((item) => (
          <div key={item.id} className="import-card">
            <div className="block-head">
              <b>{item.bundle_type === "agronomy_pack" ? item.bundle.region?.name : item.bundle.title}</b>
              <span className="muted">{t(`bundle_${item.bundle_type}`)} · {item.bundle.origin?.node_id || "-"} · {formatDate(item.created_at, locale)}</span>
              <StatusPill status={item.local_review_status === "approved" ? "good" : item.local_review_status === "rejected" ? "blocking" : "fair"} label={t(`import_${item.local_review_status}`)} />
            </div>
            {item.compatibility_findings.length > 0 && <ul className="warn-text">{item.compatibility_findings.map((f: string) => <li key={f}>{f}</li>)}</ul>}
            {item.bundle_type === "agronomy_pack" && (
              <small className="muted">{t("ex_pack_summary", { crops: item.bundle.crops.length, sources: item.bundle.sources.length, gw: String(item.bundle.groundwater?.category || "unknown").replace(/_/g, "-") })}</small>
            )}
            {item.local_review_status === "pending" && (
              <div className="action-btns">
                <button className="small primary" disabled={item.compatibility_findings.length > 0} onClick={() => review(item.id, true)}>{t("ex_approve")}</button>
                <button className="small secondary" onClick={() => review(item.id, false)}>{t("ex_reject")}</button>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="card-block subtle">
        <h4>{t("ex_paste_bundle")}</h4>
        <textarea value={paste} onChange={(e) => setPaste(e.target.value)} rows={4} placeholder='{"schema_version": "1.0.0", ...}' />
        <button className="secondary small" disabled={!paste.trim()} onClick={importPasted}>{t("ex_import")}</button>
      </div>
    </div>
  );
}
