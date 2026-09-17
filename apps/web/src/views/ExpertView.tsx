import React, { useState, useEffect, FormEvent } from "react";
import {
  BookOpen,
  FileText,
  Download,
  Users,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ExternalLink,
  Sprout,
  Calendar,
  Droplets,
  MapPin,
  ChevronDown,
  ChevronUp,
  Search,
  Upload,
  Send
} from "lucide-react";
import { api } from "../api";
import { Json } from "../types";

export interface Practice {
  id: string;
  node_id: string;
  created_by: string;
  version: number;
  title: string;
  summary: string;
  country_codes: string[];
  state_codes: string[];
  crops: string[];
  seasons: string[];
  water_contexts: string[];
  steps: string[];
  contraindications: string[];
  source_urls: string[];
  license: "CC0-1.0" | "CC-BY-4.0" | string;
  review_status: "draft" | "reviewed" | string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at: string;
}

export interface ExchangeImport {
  id: string;
  node_id: string;
  imported_by: string;
  digest: string;
  bundle: {
    title?: string;
    summary?: string;
    origin?: {
      node_id?: string;
      country_code?: string;
      organization_label?: string;
    };
    applicability?: {
      crops?: string[];
      seasons?: string[];
      water_contexts?: string[];
      country_codes?: string[];
      state_codes?: string[];
    };
    steps?: Array<{ instruction: string }>;
    contraindications?: string[];
    evidence?: Array<{ citation_url: string }>;
  };
  compatibility_findings: string[];
  local_review_status: "pending" | "approved" | "rejected" | string;
  local_review_note?: string | null;
  local_reviewed_by?: string | null;
  created_at: string;
}

export interface ExpertCase {
  id: string;
  node_id: string;
  owner_subject: string;
  farm_id: string;
  diagnosis_id: string;
  status: "open" | "in_review" | "resolved" | string;
  assigned_subject?: string | null;
  review_text?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  version: number;
  created_at: string;
}

export interface ExpertViewProps {
  t: Record<string, string>;
}

export function ExpertView({ t }: ExpertViewProps) {
  const [tab, setTab] = useState<"library" | "exchange" | "cases" | "draft">("library");
  const [practices, setPractices] = useState<Practice[]>([]);
  const [imports, setImports] = useState<ExchangeImport[]>([]);
  const [cases, setCases] = useState<ExpertCase[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>("practice_bbf_drainage");
  const [actionLoading, setActionLoading] = useState(false);
  const [notice, setNotice] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Search & filter for Library
  const [searchQuery, setSearchQuery] = useState("");
  const [cropFilter, setCropFilter] = useState("all");

  // Inline Case Resolution State
  const [caseNoteMap, setCaseNoteMap] = useState<Record<string, string>>({});

  // Draft Practice Form State
  const [draftTitle, setDraftTitle] = useState("");
  const [draftSummary, setDraftSummary] = useState("");
  const [draftCrops, setDraftCrops] = useState("soybean, cotton, pigeon_pea");
  const [draftSeasons, setDraftSeasons] = useState<string[]>(["kharif"]);
  const [draftWater, setDraftWater] = useState<string[]>(["rainfed"]);
  const [draftStates, setDraftStates] = useState("MH, TS, KA, MP");
  const [draftSteps, setDraftSteps] = useState(
    "1. Prepare seedbed with broad beds (100-150cm wide) separated by 30cm furrows before monsoon onset.\n2. Sow 2-4 rows of crops on elevated bed tops while keeping furrows unplanted.\n3. Channel excess runoff into farm ponds or grassed waterways.\n4. Apply organic mulch in furrows to conserve residual soil moisture for rabi."
  );
  const [draftContra, setDraftContra] = useState(
    "Not recommended for light sandy soils with high percolation rates.\nAvoid slopes exceeding 1.5% without contour terrace reinforcement."
  );
  const [draftUrls, setDraftUrls] = useState("https://www.icrisat.org\nhttps://icar.org.in");
  const [draftLicense, setDraftLicense] = useState<"CC-BY-4.0" | "CC0-1.0">("CC-BY-4.0");

  const loadData = async () => {
    try {
      const [pData, iData, cData] = await Promise.all([
        api<Practice[]>("/api/v1/expert/practices", {}, true).catch(() => []),
        api<ExchangeImport[]>("/api/v1/expert/exchange/imports", {}, true).catch(() => []),
        api<ExpertCase[]>("/api/v1/expert/cases", {}, true).catch(() => [])
      ]);
      setPractices(pData);
      setImports(iData);
      setCases(cData);
    } catch (e) {
      console.warn("Load expert data error", e);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const exportPractice = async (practiceId: string) => {
    try {
      const bundle = await api<Json>(`/api/v1/expert/practices/${practiceId}/export`, {}, true);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `practice_bundle_${practiceId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setNotice({ type: "success", message: "Practice bundle exported as privacy-preserving JSON." });
    } catch (err) {
      setNotice({ type: "error", message: (err as Error).message });
    }
  };

  const approvePractice = async (practiceId: string) => {
    setActionLoading(true);
    try {
      await api(`/api/v1/expert/practices/${practiceId}/review`, {
        method: "POST",
        body: JSON.stringify({
          approve: true,
          note: "Verified by agronomist for regional agro-climatic efficacy."
        })
      }, true);
      setNotice({ type: "success", message: "Practice reviewed and marked as ICAR Verified!" });
      await loadData();
    } catch (err) {
      setNotice({ type: "error", message: (err as Error).message });
    } finally {
      setActionLoading(false);
    }
  };

  const loadSampleBundle = async () => {
    setActionLoading(true);
    try {
      const sample = await api<Json>("/api/v1/expert/exchange/sample-bundle", {}, true);
      await api("/api/v1/expert/exchange/imports", {
        method: "POST",
        body: JSON.stringify(sample)
      }, true);
      setNotice({ type: "success", message: "Sample practice bundle imported successfully!" });
      await loadData();
    } catch (err) {
      setNotice({ type: "error", message: (err as Error).message });
    } finally {
      setActionLoading(false);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const bundle = JSON.parse(reader.result as string);
        setActionLoading(true);
        await api("/api/v1/expert/exchange/imports", {
          method: "POST",
          body: JSON.stringify(bundle)
        }, true);
        setNotice({ type: "success", message: "Practice bundle imported into exchange successfully." });
        await loadData();
      } catch (err) {
        setNotice({ type: "error", message: (err as Error).message || "Invalid JSON bundle schema." });
      } finally {
        setActionLoading(false);
        e.target.value = "";
      }
    };
    reader.readAsText(file);
  };

  const reviewImport = async (id: string, approve: boolean) => {
    setActionLoading(true);
    try {
      await api(`/api/v1/expert/exchange/imports/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          approve,
          note: approve
            ? "Approved: Compatible with local agro-climatic conditions and soil profiles."
            : "Rejected: Incompatible with regional soil moisture or crop rotation constraints."
        })
      }, true);
      setNotice({ type: "success", message: approve ? "Bundle approved for local node use." : "Bundle rejected." });
      await loadData();
    } catch (err) {
      setNotice({ type: "error", message: (err as Error).message });
    } finally {
      setActionLoading(false);
    }
  };

  const submitCaseResolution = async (c: ExpertCase) => {
    const note = (caseNoteMap[c.id] || "").trim();
    if (!note) return;
    setActionLoading(true);
    try {
      await api(`/api/v1/expert/cases/${c.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          version: c.version,
          review_text: note,
          status: "resolved"
        })
      }, true);
      setCaseNoteMap((prev) => {
        const copy = { ...prev };
        delete copy[c.id];
        return copy;
      });
      setNotice({ type: "success", message: `Case #${c.id.slice(0, 10)} resolved with agronomist recommendation.` });
      await loadData();
    } catch (err) {
      setNotice({ type: "error", message: (err as Error).message });
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreatePractice = async (e: FormEvent) => {
    e.preventDefault();
    if (!draftTitle.trim() || !draftSummary.trim() || !draftSteps.trim()) {
      setNotice({ type: "error", message: "Please fill in all required fields (title, summary, steps)." });
      return;
    }

    const cropsList = draftCrops.split(",").map((c) => c.trim().toLowerCase()).filter(Boolean);
    const statesList = draftStates.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
    const stepsList = draftSteps.split("\n").map((s) => s.trim()).filter(Boolean);
    const contraList = draftContra.split("\n").map((s) => s.trim()).filter(Boolean);
    const urlsList = draftUrls.split("\n").map((u) => u.trim()).filter(Boolean);

    if (cropsList.length === 0) {
      setNotice({ type: "error", message: "Please specify at least one crop." });
      return;
    }
    if (draftSeasons.length === 0) {
      setNotice({ type: "error", message: "Please select at least one season." });
      return;
    }
    if (draftWater.length === 0) {
      setNotice({ type: "error", message: "Please select at least one water context." });
      return;
    }

    setActionLoading(true);
    try {
      await api("/api/v1/expert/practices", {
        method: "POST",
        body: JSON.stringify({
          title: draftTitle.trim(),
          summary: draftSummary.trim(),
          country_codes: ["IN"],
          state_codes: statesList,
          crops: cropsList,
          seasons: draftSeasons,
          water_contexts: draftWater,
          steps: stepsList,
          contraindications: contraList,
          source_urls: urlsList.length > 0 ? urlsList : ["https://icar.org.in"],
          license: draftLicense
        })
      }, true);
      setNotice({ type: "success", message: "New practice drafted and saved to Knowledge Bank!" });
      setDraftTitle("");
      setDraftSummary("");
      setDraftSteps("");
      setDraftContra("");
      setTab("library");
      await loadData();
    } catch (err) {
      setNotice({ type: "error", message: (err as Error).message });
    } finally {
      setActionLoading(false);
    }
  };

  // Filtered practices for library tab
  const filteredPractices = practices.filter((p) => {
    const matchesSearch =
      searchQuery.trim() === "" ||
      p.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.summary.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.crops?.some((c) => c.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesCrop =
      cropFilter === "all" ||
      p.crops?.some((c) => c.toLowerCase() === cropFilter.toLowerCase());

    return matchesSearch && matchesCrop;
  });

  return (
    <section className="panel">
      <div className="section-title">
        <BookOpen />
        <div>
          <small>ICAR & CRIDA PEER VERIFIED</small>
          <h2>{t.expert || "Knowledge Bank & Peer Exchange"}</h2>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="tabs-nav">
        <button
          type="button"
          className={`tab-btn ${tab === "library" ? "active" : ""}`}
          onClick={() => setTab("library")}
        >
          <FileText size={16} />
          {t.practice_library || "Verified Practices"}
          <em>{practices.length}</em>
        </button>

        <button
          type="button"
          className={`tab-btn ${tab === "exchange" ? "active" : ""}`}
          onClick={() => setTab("exchange")}
        >
          <Download size={16} />
          {t.exchange || "Community Exchange"}
          <em>{imports.length}</em>
        </button>

        <button
          type="button"
          className={`tab-btn ${tab === "cases" ? "active" : ""}`}
          onClick={() => setTab("cases")}
        >
          <Users size={16} />
          {t.cases || "Review Cases"}
          <em>{cases.length}</em>
        </button>

        <button
          type="button"
          className={`tab-btn ${tab === "draft" ? "active" : ""}`}
          onClick={() => setTab("draft")}
        >
          <Sparkles size={16} />
          {t.draft_practice || "Draft Practice"}
        </button>
      </div>

      {/* Action Progress Bar */}
      {actionLoading && (
        <div className="inplace-progress">
          <div className="inplace-progress-header">
            <b>
              <RefreshCw className="spin" size={16} /> Processing Knowledge Action...
            </b>
          </div>
          <div className="inplace-progress-track">
            <div className="inplace-progress-fill" style={{ width: "70%" }} />
          </div>
        </div>
      )}

      {/* Notification Banner */}
      {notice && (
        <div
          style={{
            padding: "12px 18px",
            borderRadius: "10px",
            marginBottom: "16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontSize: "14px",
            background: notice.type === "success" ? "#f0fdf4" : "#fef2f2",
            border: `1px solid ${notice.type === "success" ? "#86efac" : "#fca5a5"}`,
            color: notice.type === "success" ? "#166534" : "#991b1b"
          }}
        >
          <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
            {notice.type === "success" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            {notice.message}
          </span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            style={{ background: "transparent", border: 0, cursor: "pointer", color: "inherit", fontWeight: 700 }}
          >
            ✕
          </button>
        </div>
      )}

      {/* TAB 1: VERIFIED PRACTICES LIBRARY */}
      {tab === "library" && (
        <div>
          {/* Search & Filter Toolbar */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
              marginBottom: "18px",
              padding: "12px 16px",
              background: "#fbfbf7",
              border: "1px solid var(--line)",
              borderRadius: "12px"
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flex: 1, minWidth: "220px" }}>
              <Search size={16} color="var(--muted)" />
              <input
                type="text"
                placeholder="Search practices by crop, title, or method..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  border: 0,
                  background: "transparent",
                  width: "100%",
                  fontSize: "14px",
                  outline: "none"
                }}
              />
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600 }}>Filter Crop:</span>
              <select
                value={cropFilter}
                onChange={(e) => setCropFilter(e.target.value)}
                style={{
                  padding: "6px 12px",
                  borderRadius: "8px",
                  border: "1px solid var(--line)",
                  background: "#ffffff",
                  fontSize: "13px"
                }}
              >
                <option value="all">All Crops ({practices.length})</option>
                <option value="soybean">Soybean</option>
                <option value="cotton">Cotton</option>
                <option value="pigeon_pea">Pigeon Pea (Tur)</option>
                <option value="sorghum">Sorghum (Jowar)</option>
                <option value="gram">Gram (Chana)</option>
                <option value="rice">Rice (Paddy)</option>
              </select>
            </div>
          </div>

          {/* Practices List */}
          {filteredPractices.length === 0 ? (
            <div
              style={{
                textAlign: "center",
                padding: "48px 24px",
                color: "var(--muted)",
                background: "#ffffff",
                border: "1px dashed var(--line)",
                borderRadius: "14px"
              }}
            >
              <FileText size={36} style={{ marginBottom: "12px", opacity: 0.5 }} />
              <h4 style={{ margin: "0 0 6px 0", color: "var(--green-900)" }}>No Practices Found</h4>
              <p style={{ margin: 0, fontSize: "14px" }}>
                {searchQuery || cropFilter !== "all"
                  ? "No practices match the current search or crop filter."
                  : "No practices currently registered in this node."}
              </p>
            </div>
          ) : (
            <div className="practice-list">
              {filteredPractices.map((p) => {
                const isExpanded = expandedId === p.id;
                const isReviewed = p.review_status === "reviewed";

                return (
                  <div className="practice-card" key={p.id}>
                    <div className="practice-card-header">
                      <div style={{ flex: 1, paddingRight: "16px" }}>
                        <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap", marginBottom: "6px" }}>
                          <h3 style={{ margin: 0 }}>{p.title}</h3>
                          {isReviewed ? (
                            <span
                              className="source-tag"
                              style={{ color: "#16a34a", borderColor: "#86efac", background: "#f0fdf4" }}
                            >
                              <CheckCircle2 size={13} /> ICAR VERIFIED
                            </span>
                          ) : (
                            <span
                              className="source-tag"
                              style={{ color: "#d97706", borderColor: "#fde68a", background: "#fffbeb" }}
                            >
                              <Clock size={13} /> DRAFT REVIEW
                            </span>
                          )}
                        </div>

                        {/* Tag Pills */}
                        <div className="practice-tags">
                          {p.crops?.map((c) => (
                            <span key={c} className="practice-tag crop">
                              <Sprout size={11} /> {c}
                            </span>
                          ))}
                          {p.seasons?.map((s) => (
                            <span key={s} className="practice-tag season">
                              <Calendar size={11} /> {s}
                            </span>
                          ))}
                          {p.water_contexts?.map((w) => (
                            <span key={w} className="practice-tag water">
                              <Droplets size={11} /> {w}
                            </span>
                          ))}
                          {p.state_codes?.map((st) => (
                            <span key={st} className="practice-tag">
                              <MapPin size={11} /> {st}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Card Action Buttons */}
                      <div style={{ display: "flex", gap: "8px", alignItems: "center", flexShrink: 0 }}>
                        <button
                          type="button"
                          className="secondary"
                          style={{
                            padding: "6px 12px",
                            fontSize: "12px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "6px"
                          }}
                          onClick={() => exportPractice(p.id)}
                          title="Download privacy-preserving JSON bundle"
                        >
                          <Download size={14} />
                          Export Bundle
                        </button>

                        {!isReviewed && (
                          <button
                            type="button"
                            className="primary"
                            style={{ padding: "6px 12px", fontSize: "12px" }}
                            onClick={() => approvePractice(p.id)}
                          >
                            Approve & Verify
                          </button>
                        )}

                        <button
                          type="button"
                          className="secondary"
                          style={{
                            padding: "6px 12px",
                            fontSize: "12px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px"
                          }}
                          onClick={() => setExpandedId(isExpanded ? null : p.id)}
                        >
                          {isExpanded ? (
                            <>
                              <ChevronUp size={14} /> Hide Details
                            </>
                          ) : (
                            <>
                              <ChevronDown size={14} /> View Steps & Evidence
                            </>
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Summary */}
                    <p style={{ margin: "10px 0 12px 0", color: "#334155", fontSize: "14px", lineHeight: 1.55 }}>
                      {p.summary}
                    </p>

                    {/* Expanded Content: Steps, Contraindications, Citations */}
                    {isExpanded && (
                      <div style={{ marginTop: "14px", paddingTop: "14px", borderTop: "1px solid var(--line)" }}>
                        {/* Implementation Steps */}
                        {p.steps && p.steps.length > 0 && (
                          <div className="step-list">
                            <strong style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px", color: "var(--green-950)" }}>
                              <FileText size={15} /> Recommended Implementation Steps:
                            </strong>
                            <ol>
                              {p.steps.map((step, idx) => (
                                <li key={idx}>{step}</li>
                              ))}
                            </ol>
                          </div>
                        )}

                        {/* Contraindications & Cautions */}
                        {p.contraindications && p.contraindications.length > 0 && (
                          <div className="contraindications-box">
                            <strong style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "6px" }}>
                              <AlertTriangle size={15} /> Soil & Topography Contraindications:
                            </strong>
                            <ul style={{ margin: "0", paddingLeft: "18px" }}>
                              {p.contraindications.map((contra, idx) => (
                                <li key={idx} style={{ marginBottom: "4px" }}>
                                  {contra}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Scientific Citations / Source URLs */}
                        {p.source_urls && p.source_urls.length > 0 && (
                          <div style={{ marginTop: "12px", fontSize: "13px" }}>
                            <strong style={{ color: "var(--green-900)" }}>Scientific Citations & Provenance:</strong>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginTop: "6px" }}>
                              {p.source_urls.map((url, idx) => (
                                <a
                                  key={idx}
                                  href={url}
                                  target="_blank"
                                  rel="noreferrer"
                                  style={{
                                    color: "var(--green-700)",
                                    textDecoration: "underline",
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "4px"
                                  }}
                                >
                                  <ExternalLink size={12} />
                                  {url.replace(/^https?:\/\//, "").slice(0, 48)}...
                                </a>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Metadata Footer */}
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginTop: "14px",
                            paddingTop: "10px",
                            borderTop: "1px dashed var(--line)",
                            fontSize: "11px",
                            color: "var(--muted)"
                          }}
                        >
                          <span>
                            License: <strong>{p.license}</strong> · Node ID: <code>{p.node_id}</code> · Version: v{p.version}
                          </span>
                          <span>
                            {p.reviewed_at
                              ? `Reviewed on ${new Date(p.reviewed_at).toLocaleDateString()} by ${p.reviewed_by || "Expert"}`
                              : "Review Pending"}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: COMMUNITY PRACTICE EXCHANGE */}
      {tab === "exchange" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {/* Exchange Info & Upload Card */}
          <div
            style={{
              background: "#fbfbf6",
              border: "1px solid var(--line)",
              borderRadius: "14px",
              padding: "20px"
            }}
          >
            <h4 style={{ margin: "0 0 8px 0", fontFamily: "Fraunces, serif", fontSize: "18px", color: "var(--green-950)" }}>
              Import Verified Practice Bundle
            </h4>
            <p style={{ fontSize: "13px", color: "var(--muted)", margin: "0 0 16px 0", lineHeight: 1.5 }}>
              Exchange cryptographically validated, privacy-preserving agronomic practice bundles from agricultural
              extension universities and partner community nodes. <strong>No farmer personal identity or exact coordinates are ever transmitted.</strong>
            </p>

            <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
              <label
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "8px 16px",
                  borderRadius: "10px",
                  border: "1px solid var(--line)",
                  background: "#ffffff",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: "pointer"
                }}
              >
                <Upload size={15} />
                <span>Upload Practice JSON</span>
                <input type="file" accept=".json" onChange={handleFileUpload} style={{ display: "none" }} />
              </label>

              <button
                type="button"
                className="secondary"
                onClick={loadSampleBundle}
                disabled={actionLoading}
                style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "13px", padding: "8px 16px" }}
              >
                <RefreshCw size={14} />
                Try Sample Bundle
              </button>
            </div>
          </div>

          {/* Imported Bundles List */}
          <div>
            <h4 style={{ margin: "0 0 12px 0", fontSize: "16px", color: "var(--green-950)" }}>
              Imported Practice Bundles ({imports.length})
            </h4>

            {imports.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  padding: "36px 20px",
                  color: "var(--muted)",
                  background: "#ffffff",
                  border: "1px dashed var(--line)",
                  borderRadius: "12px"
                }}
              >
                No bundles imported yet. Use the upload button or click &quot;Try Sample Bundle&quot; above to simulate peer exchange.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                {imports.map((imp) => {
                  const isApproved = imp.local_review_status === "approved";
                  const isRejected = imp.local_review_status === "rejected";
                  const isPending = imp.local_review_status === "pending";

                  return (
                    <div className="exchange-bundle-card" key={imp.id}>
                      <div style={{ flex: 1, paddingRight: "16px" }}>
                        <h4 style={{ margin: "0 0 4px 0", fontSize: "15px", color: "var(--green-900)" }}>
                          {imp.bundle?.title || `Bundle #${imp.id.slice(0, 12)}`}
                        </h4>
                        <div style={{ fontSize: "12px", color: "var(--muted)" }}>
                          Origin: <strong>{imp.bundle?.origin?.organization_label || imp.bundle?.origin?.node_id || imp.node_id}</strong> ·
                          Imported: {new Date(imp.created_at).toLocaleDateString()}
                        </div>
                        <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "2px" }}>
                          Target Crops: <strong>{(imp.bundle?.applicability?.crops || []).join(", ") || "Universal"}</strong>
                        </div>

                        {imp.compatibility_findings && imp.compatibility_findings.length > 0 && (
                          <div style={{ fontSize: "12px", color: "#b45309", marginTop: "6px" }}>
                            ⚠️ Compatibility checks: {imp.compatibility_findings.join("; ")}
                          </div>
                        )}

                        {imp.local_review_note && (
                          <div style={{ fontSize: "12px", color: "#475569", marginTop: "6px", fontStyle: "italic" }}>
                            Agronomist Note: &quot;{imp.local_review_note}&quot;
                          </div>
                        )}
                      </div>

                      <div style={{ flexShrink: 0 }}>
                        {isApproved && (
                          <span
                            style={{
                              color: "#16a34a",
                              fontWeight: 700,
                              padding: "4px 12px",
                              background: "#f0fdf4",
                              borderRadius: "20px",
                              border: "1px solid #86efac",
                              fontSize: "12px"
                            }}
                          >
                            ✓ APPROVED
                          </span>
                        )}
                        {isRejected && (
                          <span
                            style={{
                              color: "#dc2626",
                              fontWeight: 700,
                              padding: "4px 12px",
                              background: "#fef2f2",
                              borderRadius: "20px",
                              border: "1px solid #fca5a5",
                              fontSize: "12px"
                            }}
                          >
                            ✕ REJECTED
                          </span>
                        )}
                        {isPending && (
                          <div style={{ display: "flex", gap: "8px" }}>
                            <button
                              type="button"
                              className="primary"
                              style={{ padding: "6px 14px", fontSize: "12px" }}
                              onClick={() => reviewImport(imp.id, true)}
                            >
                              Approve
                            </button>
                            <button
                              type="button"
                              className="secondary"
                              style={{ padding: "6px 14px", fontSize: "12px" }}
                              onClick={() => reviewImport(imp.id, false)}
                            >
                              Reject
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: DIAGNOSTIC CASES AWAITING REVIEW */}
      {tab === "cases" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <div style={{ marginBottom: "6px" }}>
            <p style={{ margin: "0", fontSize: "14px", color: "var(--muted)" }}>
              Crop health and pest diagnoses submitted by farmers that exhibited high uncertainty or flagged severe pathogen
              symptoms requiring human agronomist verification.
            </p>
          </div>

          {cases.length === 0 ? (
            <div
              style={{
                textAlign: "center",
                padding: "48px 20px",
                color: "var(--muted)",
                background: "#ffffff",
                border: "1px dashed var(--line)",
                borderRadius: "14px"
              }}
            >
              <Users size={36} style={{ marginBottom: "12px", opacity: 0.5 }} />
              <h4 style={{ margin: "0 0 6px 0", color: "var(--green-900)" }}>No Escalated Cases</h4>
              <p style={{ margin: 0, fontSize: "14px" }}>
                When a farmer requests expert confirmation during plant disease diagnosis, escalated cases will appear here for your review.
              </p>
            </div>
          ) : (
            cases.map((c) => {
              const isResolved = c.status === "resolved";

              return (
                <div className="case-card" key={c.id}>
                  <div className="case-card-header">
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                        <strong style={{ fontSize: "15px", color: "var(--green-950)" }}>
                          Case #{c.id.slice(0, 12)}
                        </strong>
                        {isResolved ? (
                          <span
                            className="source-tag"
                            style={{ color: "#16a34a", borderColor: "#86efac", background: "#f0fdf4" }}
                          >
                            <CheckCircle2 size={12} /> RESOLVED
                          </span>
                        ) : (
                          <span
                            className="source-tag"
                            style={{ color: "#d97706", borderColor: "#fde68a", background: "#fffbeb" }}
                          >
                            <Clock size={12} /> OPEN / PENDING REVIEW
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: "12px", color: "var(--muted)" }}>
                        Farm ID: <code>{c.farm_id}</code> · Diagnosis Ref: <code>{c.diagnosis_id}</code> · Queued:{" "}
                        {new Date(c.created_at).toLocaleString()}
                      </div>
                    </div>
                  </div>

                  {isResolved ? (
                    <div
                      style={{
                        background: "#f0fdf4",
                        border: "1px solid #bbf7d0",
                        borderRadius: "10px",
                        padding: "12px 16px",
                        marginTop: "12px"
                      }}
                    >
                      <strong style={{ color: "#166534", fontSize: "13px" }}>
                        Agronomist Prescription & Recommendation:
                      </strong>
                      <p style={{ margin: "6px 0 0 0", color: "#14532d", fontSize: "14px", whiteSpace: "pre-wrap" }}>
                        {c.review_text}
                      </p>
                      <small style={{ display: "block", marginTop: "6px", color: "#15803d" }}>
                        Verified by: {c.reviewed_by || "Expert"} on{" "}
                        {c.reviewed_at ? new Date(c.reviewed_at).toLocaleDateString() : "N/A"}
                      </small>
                    </div>
                  ) : (
                    <div className="case-inline-resolve">
                      <label
                        style={{
                          display: "block",
                          fontSize: "13px",
                          fontWeight: 600,
                          color: "var(--green-900)",
                          marginBottom: "6px"
                        }}
                      >
                        Provide Verified Agronomic Advice:
                      </label>
                      <textarea
                        placeholder="Enter confirmed diagnosis, recommended biological or chemical treatment dosages, and safe cultural practices..."
                        rows={3}
                        style={{
                          width: "100%",
                          padding: "10px 12px",
                          borderRadius: "8px",
                          border: "1px solid var(--line)",
                          fontSize: "13px",
                          outline: "none"
                        }}
                        value={caseNoteMap[c.id] || ""}
                        onChange={(e) =>
                          setCaseNoteMap({ ...caseNoteMap, [c.id]: e.target.value })
                        }
                      />
                      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "10px" }}>
                        <button
                          type="button"
                          className="primary"
                          style={{
                            padding: "8px 16px",
                            fontSize: "13px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "6px"
                          }}
                          disabled={actionLoading || !(caseNoteMap[c.id] || "").trim()}
                          onClick={() => submitCaseResolution(c)}
                        >
                          <Send size={13} />
                          Submit Agronomist Resolution
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* TAB 4: DRAFT NEW PRACTICE */}
      {tab === "draft" && (
        <form
          onSubmit={handleCreatePractice}
          style={{
            background: "#ffffff",
            border: "1px solid var(--line)",
            borderRadius: "14px",
            padding: "24px"
          }}
        >
          <div style={{ marginBottom: "18px" }}>
            <h4 style={{ margin: "0 0 6px 0", fontFamily: "Fraunces, serif", fontSize: "18px", color: "var(--green-950)" }}>
              Draft New Regenerative Agricultural Practice
            </h4>
            <p style={{ margin: 0, fontSize: "13px", color: "var(--muted)" }}>
              All drafted practices are checked against ICAR standards and will be saved in draft state until reviewed.
            </p>
          </div>

          <div className="form-grid">
            <label className="field">
              <span>Practice Title *</span>
              <input
                type="text"
                placeholder="e.g. Broad Bed and Furrow (BBF) in Deep Black Soils"
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                required
                minLength={3}
                maxLength={160}
              />
            </label>

            <label className="field">
              <span>Target Crops (Comma-Separated) *</span>
              <input
                type="text"
                placeholder="e.g. soybean, cotton, pigeon_pea, sorghum"
                value={draftCrops}
                onChange={(e) => setDraftCrops(e.target.value)}
                required
              />
            </label>

            <label className="field">
              <span>Applicable States (Codes) *</span>
              <input
                type="text"
                placeholder="e.g. MH, TS, KA, MP, GJ"
                value={draftStates}
                onChange={(e) => setDraftStates(e.target.value)}
                required
              />
            </label>

            <label className="field">
              <span>Open Knowledge License *</span>
              <select
                value={draftLicense}
                onChange={(e) => setDraftLicense(e.target.value as "CC-BY-4.0" | "CC0-1.0")}
              >
                <option value="CC-BY-4.0">CC-BY-4.0 (Creative Commons Attribution)</option>
                <option value="CC0-1.0">CC0-1.0 (Public Domain Dedication)</option>
              </select>
            </label>
          </div>

          {/* Season & Water Multi-Selects */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginTop: "14px" }}>
            <div>
              <span style={{ display: "block", fontSize: "13px", fontWeight: 600, marginBottom: "8px", color: "var(--green-900)" }}>
                Applicable Seasons *
              </span>
              <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
                {["kharif", "rabi", "summer"].map((s) => (
                  <label key={s} style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "13px", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={draftSeasons.includes(s)}
                      onChange={(e) => {
                        if (e.target.checked) setDraftSeasons([...draftSeasons, s]);
                        else setDraftSeasons(draftSeasons.filter((item) => item !== s));
                      }}
                    />
                    <span style={{ textTransform: "capitalize" }}>{s}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <span style={{ display: "block", fontSize: "13px", fontWeight: 600, marginBottom: "8px", color: "var(--green-900)" }}>
                Water Contexts *
              </span>
              <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
                {["rainfed", "irrigated", "supplemental_irrigation"].map((w) => (
                  <label key={w} style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "13px", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={draftWater.includes(w)}
                      onChange={(e) => {
                        if (e.target.checked) setDraftWater([...draftWater, w]);
                        else setDraftWater(draftWater.filter((item) => item !== w));
                      }}
                    />
                    <span style={{ textTransform: "capitalize" }}>{w.replace("_", " ")}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          <label className="field" style={{ marginTop: "16px" }}>
            <span>Summary & Biophysical Principles * (10-1200 characters)</span>
            <textarea
              rows={3}
              placeholder="Detail the operational summary, moisture conservation mechanisms, and expected agro-ecological outcomes..."
              value={draftSummary}
              onChange={(e) => setDraftSummary(e.target.value)}
              required
              minLength={10}
              maxLength={1200}
            />
          </label>

          <label className="field" style={{ marginTop: "14px" }}>
            <span>Implementation Steps * (One step per line)</span>
            <textarea
              rows={4}
              placeholder="1. Field preparation and grading...\n2. Bed formation using tractor or bullock-drawn implement...\n3. Crop sowing pattern on raised beds...\n4. Mulching and drainage outlet connection..."
              value={draftSteps}
              onChange={(e) => setDraftSteps(e.target.value)}
              required
            />
          </label>

          <label className="field" style={{ marginTop: "14px" }}>
            <span>Contraindications & Soil Restrictions (One per line)</span>
            <textarea
              rows={2}
              placeholder="e.g. Do not construct on slopes > 1.5% without contour bunding.\nNot suitable for shallow gravelly soils."
              value={draftContra}
              onChange={(e) => setDraftContra(e.target.value)}
            />
          </label>

          <label className="field" style={{ marginTop: "14px" }}>
            <span>Scientific Citations & ICAR Provenance URLs (One per line)</span>
            <textarea
              rows={2}
              placeholder="https://www.icrisat.org/...\nhttps://icar.org.in/..."
              value={draftUrls}
              onChange={(e) => setDraftUrls(e.target.value)}
            />
          </label>

          <div style={{ marginTop: "20px", display: "flex", justifyContent: "flex-end" }}>
            <button
              type="submit"
              className="primary"
              disabled={actionLoading}
              style={{ padding: "10px 24px", fontSize: "14px", display: "inline-flex", alignItems: "center", gap: "8px" }}
            >
              <Sparkles size={16} />
              Save & Draft Practice
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
