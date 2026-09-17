import React, { useState } from "react";
import { Sprout, RefreshCw, AlertTriangle } from "lucide-react";
import { View, Json } from "../types";

export interface CropRecViewProps {
  t: Record<string, string>;
  farm?: Json;
  cropRecs: Json | null;
  loadingRecs: boolean;
  season: string;
  handleSeasonChange: (s: string) => void;
  loadCropRecs: (s: string) => Promise<void>;
  go: (v: View) => void;
}

export function CropRecView({
  t,
  farm,
  cropRecs,
  loadingRecs,
  season,
  handleSeasonChange,
  loadCropRecs,
  go
}: CropRecViewProps) {
  const [expandedCrop, setExpandedCrop] = useState<string | null>(null);
  const [showUnsuitable, setShowUnsuitable] = useState(false);

  if (!farm) {
    return (
      <section className="panel" style={{ textAlign: "center", padding: "60px 20px" }}>
        <Sprout size={48} color="var(--lime-500)" style={{ marginBottom: "12px" }} />
        <h2>{t.add_farm_first || "Add a Farm First"}</h2>
        <button className="primary" onClick={() => go("farm")} style={{ marginTop: "16px" }}>
          {t.start || "Add Farm Profile"}
        </button>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="section-title">
        <Sprout />
        <div>
          <small>PIPELINE STAGE 4 OF 5 · {farm.name} ({farm.district})</small>
          <h2>{t.crops || "Multi-Factor Crop Recommendation Engine"}</h2>
        </div>
      </div>

      <div className="crop-rec-panel" style={{ marginTop: 0 }}>
        <div className="crop-rec-header">
          <div className="crop-rec-title-group">
            <p style={{ margin: 0, fontSize: "14px", color: "var(--muted)" }}>
              {t.crop_rec_sub || "Dynamic agronomic matching based on soil type, water access, 7-day rainfall forecast, and crop rotation history."}
            </p>
          </div>

          <div className="crop-rec-controls">
            <div className="season-btn-group">
              <button
                className={`season-tab-btn ${season === "kharif" ? "active" : ""}`}
                onClick={() => handleSeasonChange("kharif")}
              >
                ☀️ Kharif
              </button>
              <button
                className={`season-tab-btn ${season === "rabi" ? "active" : ""}`}
                onClick={() => handleSeasonChange("rabi")}
              >
                ❄️ Rabi
              </button>
              <button
                className={`season-tab-btn ${season === "summer" ? "active" : ""}`}
                onClick={() => handleSeasonChange("summer")}
              >
                🌤️ Summer
              </button>
            </div>

            <button
              className="secondary"
              style={{ padding: "6px 12px", fontSize: "12px", display: "inline-flex", alignItems: "center", gap: "6px" }}
              onClick={() => loadCropRecs(season)}
              disabled={loadingRecs}
              title="Recalculate Recommendations"
            >
              <RefreshCw size={13} className={loadingRecs ? "spin" : ""} />
              <span>{t.refresh || "Refresh"}</span>
            </button>
          </div>
        </div>

        {/* Agro-Climatic Baseline & Data Sources Bar */}
        {cropRecs && (
          <div className="crop-rec-baseline-bar">
            <div className="baseline-meta-row">
              <span className="baseline-meta-item">
                📍 <strong>{cropRecs.district as string}</strong> ({cropRecs.state_name as string || "Maharashtra"})
              </span>
              {cropRecs.rainfall_7d_forecast_mm != null && (
                <span className="baseline-meta-item">
                  🌧️ 7-Day Rain Forecast: <strong>{(cropRecs.rainfall_7d_forecast_mm as number).toFixed(1)} mm</strong>
                </span>
              )}
              <span className="baseline-meta-item">
                🌱 Soil: <strong>{cropRecs.soil_type as string}</strong>
              </span>
              <span className="baseline-meta-item">
                💧 Water: <strong>{cropRecs.water_access as string}</strong>
              </span>
              {cropRecs.previous_crop && (
                <span className="baseline-meta-item">
                  🔄 Prev Crop: <strong>{cropRecs.previous_crop as string}</strong>
                </span>
              )}
            </div>

            {cropRecs.regional_notes && (
              <div style={{ fontSize: "12px", color: "var(--muted)", fontStyle: "italic", borderTop: "1px dashed #dbe7d0", paddingTop: "6px" }}>
                🏛️ Regional Agro-Climatic Profile: {cropRecs.regional_notes as string}
              </div>
            )}

            {cropRecs.data_sources_used && (
              <div className="baseline-sources-row">
                <small>{t.sources_badge || "Data Sources Used"}:</small>
                {(cropRecs.data_sources_used as Json[]).map((src: Json, idx: number) => (
                  <span key={idx} className="source-tag">
                    ✓ <strong>{src.name as string}</strong> ({src.type as string})
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {loadingRecs ? (
          <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--muted)" }}>
            <RefreshCw className="spin" size={24} style={{ marginBottom: "8px" }} />
            <p style={{ margin: 0, fontSize: "13px" }}>{t.loading_crop_recs || "Evaluating agronomic suitability for your field..."}</p>
          </div>
        ) : cropRecs && ((cropRecs.recommendations as Json[])?.length > 0 || (cropRecs.unsuitable_crops as Json[])?.length > 0) ? (
          <div>
            {((cropRecs.recommendations as Json[])?.length > 0) && (
              <>
                <h4 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "var(--green-950)", fontWeight: 700 }}>
                  {t.rec_crops_heading || "Recommended Crops for Your Field"} ({(cropRecs.recommendations as Json[]).length})
                </h4>

                <div className="crop-cards-grid">
                  {(cropRecs.recommendations as Json[]).map((cropItem: Json) => {
                    const isExpanded = expandedCrop === cropItem.crop;
                    const matchPct = cropItem.rank_score != null ? Math.round((cropItem.rank_score as number) * 100) : null;
                    const factors = (cropItem.factors as Json[]) || [];

                    return (
                      <div key={cropItem.crop as string} className="crop-rec-card">
                        <div className="crop-rec-card-head">
                          <div className="crop-rec-card-title">
                            <b>{cropItem.crop_name as string || (cropItem.crop as string).replace("_", " ")}</b>
                            <span>{(cropItem.crop as string).replace("_", " ")}</span>
                          </div>
                          <div className="crop-score-badge">
                            <span className="crop-score-pill">
                              {matchPct != null ? `${matchPct}% Match` : "Recommended"}
                            </span>
                            <small style={{ fontSize: "10px", color: "var(--muted)", marginTop: "2px" }}>
                              {Math.round(((cropItem.evidence_coverage as number) || 1) * 100)}% Data-Backed
                            </small>
                          </div>
                        </div>

                        <div className="crop-rec-card-body">
                          {/* Factor Accordion Toggle */}
                          <button
                            className="crop-factors-accordion-btn"
                            onClick={() => setExpandedCrop(isExpanded ? null : (cropItem.crop as string))}
                          >
                            <span>
                              {isExpanded ? (t.hide_factors_btn || "Hide Factors Breakdown") : (t.view_factors_btn || "View Decision Factors Breakdown")} ({factors.length})
                            </span>
                            <span>{isExpanded ? "▲" : "▼"}</span>
                          </button>

                          {/* 7 Decision Factors Breakdown */}
                          {isExpanded && (
                            <div className="crop-factors-list">
                              {factors.map((factor: Json) => (
                                <div key={factor.factor_id as string} className={`crop-factor-item ${factor.status as string}`}>
                                  <div className="crop-factor-header">
                                    <span className="crop-factor-name">{factor.factor_name as string}</span>
                                    <span className={`crop-factor-status ${factor.status as string}`}>
                                      {factor.status === "pass" || factor.status === "optimal" || factor.status === "compatible" ? "✅ Pass" : factor.status === "warning" || factor.status === "caution" || factor.status === "marginal" ? "⚠️ Notice" : "❌ Conflict"}
                                    </span>
                                  </div>

                                  <div className="crop-factor-data">
                                    <span style={{ fontWeight: 600 }}>{t.data_used || "Data Used"}:</span> {factor.data_used as string}
                                  </div>

                                  <div className="crop-factor-reason">
                                    <span style={{ fontWeight: 600 }}>{t.reasoning || "Rationale"}:</span> {factor.reasoning as string}
                                  </div>

                                  {factor.remedy && (
                                    <div className="crop-factor-remedy">
                                      <strong>💡 {t.remedy || "Remedy / Practice"}:</strong> {factor.remedy as string}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {/* Unsuitable Crops Drawer */}
            {(cropRecs.unsuitable_crops as Json[])?.length > 0 && (
              <div className="unsuitable-crops-section">
                <button
                  className="unsuitable-toggle-btn"
                  onClick={() => setShowUnsuitable(!showUnsuitable)}
                >
                  <AlertTriangle size={15} color="#b91c1c" />
                  <span>
                    {showUnsuitable ? (t.hide_unsuitable_btn || "Hide Ineligible Crops") : (t.view_unsuitable_btn || "View Ineligible / High-Risk Crops")} ({(cropRecs.unsuitable_crops as Json[]).length})
                  </span>
                  <span>{showUnsuitable ? "▲" : "▼"}</span>
                </button>

                {showUnsuitable && (
                  <div style={{ marginTop: "12px", display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "12px" }}>
                    {(cropRecs.unsuitable_crops as Json[]).map((cropItem: Json) => (
                      <div key={cropItem.crop as string} className="unsuitable-card">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                          <strong style={{ fontSize: "15px", color: "#991b1b" }}>
                            {cropItem.crop_name as string || (cropItem.crop as string).replace("_", " ")}
                          </strong>
                          <span style={{ fontSize: "11px", fontWeight: 800, background: "#fee2e2", color: "#991b1b", padding: "2px 8px", borderRadius: "6px" }}>
                            ❌ High Risk
                          </span>
                        </div>

                        <div style={{ fontSize: "12px", color: "#7f1d1d", background: "#fef2f2", padding: "8px 10px", borderRadius: "6px", borderLeft: "3px solid #ef4444", marginBottom: "8px" }}>
                          <strong>{t.why_unsuitable || "Why not recommended:"}</strong>
                          <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
                            {((cropItem.rejection_reasons as string[]) || []).map((reason: string, rIdx: number) => (
                              <li key={rIdx}>{reason}</li>
                            ))}
                          </ul>
                        </div>

                        {((cropItem.factors as Json[]) || []).filter((f: Json) => f.status !== "pass").map((f: Json) => (
                          <div key={f.factor_id as string} style={{ fontSize: "11px", color: "#555", marginTop: "4px" }}>
                            <strong>{f.factor_name as string}:</strong> {f.reasoning as string}
                            {f.remedy && <div style={{ color: "#b45309" }}>💡 Remedy: {f.remedy as string}</div>}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div style={{ textAlign: "center", padding: "30px 20px", color: "var(--muted)" }}>
            <p>{t.no_crops_found || "No crops match all constraints for this season and water access."}</p>
          </div>
        )}
      </div>

      {/* Pipeline Navigation Footer */}
      <div className="pipeline-footer-nav">
        <button className="nav-prev-btn" onClick={() => go("soil")}>
          {t.btn_back_soil || "← Back to Soil Health"}
        </button>
        <button className="nav-next-btn" onClick={() => go("advice")}>
          {t.btn_proceed_plan || "Proceed to Field Action Plan →"}
        </button>
      </div>
    </section>
  );
}
