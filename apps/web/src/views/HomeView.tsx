import {
  Activity,
  ArrowRight,
  ChevronRight,
  CloudRain,
  Leaf,
  MapPin,
  Microscope,
  ShieldCheck,
  Sparkles,
  Sprout,
  Trash2,
  User
} from "lucide-react";
import { Json, TranslationDictionary, View } from "../types";
import { VerifiedDataSourcesPanel } from "../components/VerifiedDataSourcesPanel";

interface HomeViewProps {
  t: TranslationDictionary;
  farms: Json[];
  selected: string;
  setSelected: (id: string) => void;
  go: (v: View) => void;
  onDeleteFarm?: (id: string) => Promise<void>;
}

export const HomeView: React.FC<HomeViewProps> = ({
  t,
  farms,
  selected,
  setSelected,
  go,
  onDeleteFarm
}) => {
  const activeFarm = farms.find((f) => f.id === selected) || farms[0];

  const isFarmMine = (f: Json) => {
    if (f.is_mine) return true;
    try {
      const myIds = JSON.parse(localStorage.getItem("kisanai_my_farm_ids") || "[]");
      return Array.isArray(myIds) && myIds.includes(f.id);
    } catch {
      return false;
    }
  };

  return (
    <>
      <section className="hero">
        <div className="eyebrow">
          <Sparkles size={13} />
          AG-02 LOCALIZED AGRO-CLIMATE · COMMUNITY AGRICULTURAL INTELLIGENCE
        </div>
        <h1>{t.hello || "KISANAI"}</h1>
        <p>
          {t.sub ||
            "Hyperlocal weather warnings from IMD, 10-meter Sentinel-2 satellite canopy scans, and verified regenerative practices tailored to your exact coordinates — with zero guesswork."}
        </p>

        {/* If Active Farm Exists: Welcoming Quick-Resume Card */}
        {activeFarm ? (
          <div className="active-farm-resume-card">
            <div className="resume-card-header">
              <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                <span className="resume-card-badge">
                  <span className="pulse-dot" />
                  ACTIVE FARM LOADED
                </span>
                {isFarmMine(activeFarm) ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", background: "#e8f5e9", color: "#1b5e20", padding: "2px 8px", borderRadius: "12px", fontSize: "11px", fontWeight: 700, border: "1px solid #c8e6c9" }}>
                    <User size={12} />
                    My Farm
                  </span>
                ) : (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", background: "#f0f4f8", color: "#334155", padding: "2px 8px", borderRadius: "12px", fontSize: "11px", fontWeight: 600, border: "1px solid #cbd5e1" }}>
                    🌱 Community Farm
                  </span>
                )}
                {isFarmMine(activeFarm) && onDeleteFarm && (
                  <button
                    onClick={() => {
                      if (window.confirm(`Are you sure you want to delete "${activeFarm.name}"? This action cannot be undone.`)) {
                        onDeleteFarm(activeFarm.id);
                      }
                    }}
                    style={{
                      background: "#fff",
                      border: "1px solid #fca5a5",
                      color: "#dc2626",
                      borderRadius: "6px",
                      padding: "3px 8px",
                      fontSize: "11px",
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px"
                    }}
                    title="Delete your farm (only creator can delete)"
                  >
                    <Trash2 size={12} />
                    <span>Delete</span>
                  </button>
                )}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600 }}>
                  Switch Farm:
                </span>
                <select
                  value={selected}
                  onChange={(e) => {
                    setSelected(e.target.value);
                    const match = farms.find((f) => f.id === e.target.value);
                    if (match)
                      localStorage.setItem("kisanai_cached_farm", JSON.stringify(match));
                  }}
                  className="active-farm-select"
                  style={{ padding: "6px 12px", fontSize: "13px" }}
                >
                  {farms.map((f) => {
                    const mine = isFarmMine(f);
                    return (
                      <option key={f.id} value={f.id}>
                        {mine ? "👤 [My Farm] " : "🌱 "}
                        {f.name} · {f.district}, {f.state_code}
                      </option>
                    );
                  })}
                </select>
              </div>
            </div>

            <div className="resume-farm-meta">
              <h3>{activeFarm.name}</h3>
              <span className="resume-meta-tag">
                📍 {activeFarm.district},{" "}
                {activeFarm.state_name || activeFarm.state_code}
              </span>
              <span className="resume-meta-tag">
                📐 {activeFarm.area_acres || activeFarm.area_value || 1} Acres
              </span>
              {activeFarm.current_crop && (
                <span className="resume-meta-tag">
                  🌾 Crop: {String(activeFarm.current_crop).replace("_", " ")}
                </span>
              )}
              <span className="resume-meta-tag">
                🌱 Soil: {activeFarm.soil_type || "Medium Deep Black"}
              </span>
            </div>

            <div className="resume-actions-grid">
              <button
                className="resume-action-btn primary-resume"
                onClick={() => go("weather")}
              >
                <CloudRain size={16} />
                <span>2. Local Weather & Alerts</span>
                <ArrowRight size={14} style={{ marginLeft: "auto" }} />
              </button>
              <button className="resume-action-btn" onClick={() => go("crops")}>
                <Sprout size={16} />
                <span>3. Recommended Crops</span>
                <ArrowRight size={14} style={{ marginLeft: "auto" }} />
              </button>
              <button className="resume-action-btn" onClick={() => go("advice")}>
                <Activity size={16} />
                <span>4. Field Action Plan</span>
                <ArrowRight size={14} style={{ marginLeft: "auto" }} />
              </button>
              <button className="resume-action-btn" onClick={() => go("diagnose")}>
                <Microscope size={16} />
                <span>5. Plant Doctor</span>
                <ArrowRight size={14} style={{ marginLeft: "auto" }} />
              </button>
              <button className="resume-action-btn" onClick={() => go("farm")}>
                <MapPin size={16} />
                <span>Edit Field Boundary</span>
                <ArrowRight size={14} style={{ marginLeft: "auto" }} />
              </button>
            </div>
          </div>
        ) : (
          <div className="cta-row" style={{ marginTop: "24px" }}>
            <button
              className="primary"
              onClick={() => go("farm")}
              style={{ padding: "16px 28px", fontSize: "16px", borderRadius: "14px" }}
            >
              <MapPin size={20} />
              <span>Get Started — Plot Your Field</span>
              <ArrowRight size={18} />
            </button>
          </div>
        )}
      </section>

      {/* Platform Mission & Overview */}
      <section className="home-section">
        <div className="home-section-header">
          <div className="section-eyebrow">
            <Leaf size={13} />
            WHY KISANAI C2C
          </div>
          <h2>Empowering Smallholder Farmers with Ground-Truth Science</h2>
        </div>

        {/* 4 Core Features Showcase */}
        <div className="features-grid">
          <div
            className="feature-card clickable"
            onClick={() => go(activeFarm ? "weather" : "farm")}
          >
            <div className="feature-icon-box">
              <Activity size={26} />
            </div>
            <h3>10m Satellite Biophysics</h3>
            <p>
              Copernicus Sentinel-2 multispectral passes analyze canopy vigor (NDVI) and
              moisture stress (NDMI) across 5 quantile field zones to identify stressed patches
              before visible wilting.
            </p>
            <div className="feature-tags">
              <span className="feature-tag">10m Optical</span>
              <span className="feature-tag">NDVI Vigor</span>
              <span className="feature-tag">5-Zone Map</span>
            </div>
          </div>

          <div
            className="feature-card clickable"
            onClick={() => go(activeFarm ? "weather" : "farm")}
          >
            <div className="feature-icon-box">
              <CloudRain size={26} />
            </div>
            <h3>Localized Meteorology & Windows</h3>
            <p>
              Real station observations and 7-day rainfall forecasts power 4 practical
              operational windows: Sowing Readiness, Foliar Spraying, Irrigation Advisory, and
              Field Drainage Runoff Risk.
            </p>
            <div className="feature-tags">
              <span className="feature-tag">Live IMD Alerts</span>
              <span className="feature-tag">7-Day Rain Bars</span>
              <span className="feature-tag">Spraying Window</span>
            </div>
          </div>

          <div
            className="feature-card clickable"
            onClick={() => go(activeFarm ? "crops" : "farm")}
          >
            <div className="feature-icon-box">
              <Sprout size={26} />
            </div>
            <h3>7-Factor Crop Match Engine</h3>
            <p>
              Evaluates 12 major crops against 7 agronomic constraints including soil texture,
              water access, rain forecast, rotation history, and Maharashtra 36-district
              baseline normals with full explainability.
            </p>
            <div className="feature-tags">
              <span className="feature-tag">7 Decision Factors</span>
              <span className="feature-tag">Rotation Fit</span>
              <span className="feature-tag">Vernacular Rationale</span>
            </div>
          </div>

          <div
            className="feature-card clickable"
            onClick={() => go(activeFarm ? "diagnose" : "farm")}
          >
            <div className="feature-icon-box">
              <Microscope size={26} />
            </div>
            <h3>Visual Crop Doctor</h3>
            <p>
              Gemini Multimodal AI inspects leaf symptoms, diagnoses bacterial blight vs.
              fungal leaf spot, provides low-risk organic remedies, and escalates uncertain
              cases to real agronomists.
            </p>
            <div className="feature-tags">
              <span className="feature-tag">Gemini Vision</span>
              <span className="feature-tag">Bio-Pesticides</span>
              <span className="feature-tag">Expert Review</span>
            </div>
          </div>
        </div>
      </section>

      {/* Real-World Smallholder Use Cases */}
      <section className="home-section">
        <div className="home-section-header">
          <div className="section-eyebrow">
            <Sparkles size={13} />
            REAL-WORLD SCENARIOS
          </div>
          <h2>Practical Use Cases on the Field</h2>
          <p>
            Designed specifically for practical day-to-day decisions faced by Indian
            smallholder farmers throughout the crop cycle.
          </p>
        </div>

        <div className="use-cases-grid">
          <div className="use-case-card">
            <span className="use-case-badge weather-badge">Sowing Decision</span>
            <h4>"Should I sow my seeds this week or wait?"</h4>
            <p>
              Avoid dry sowing or seed washouts. KISANAI checks 7-day cumulative rainfall
              against soil moisture retention to signal whether topsoil is primed for
              germination.
            </p>
            <button
              className="use-case-action-link"
              onClick={() => go(activeFarm ? "weather" : "farm")}
            >
              <span>Check Sowing Readiness</span>
              <ChevronRight size={14} />
            </button>
          </div>

          <div className="use-case-card">
            <span className="use-case-badge weather-badge">Spraying Window</span>
            <h4>"Is today safe to spray foliar bio-nutrients?"</h4>
            <p>
              Prevent chemical wastage and runoff. The Spraying Window flags wind speeds
              exceeding 15 km/h or incoming rain within 6 hours that would wash away your spray.
            </p>
            <button
              className="use-case-action-link"
              onClick={() => go(activeFarm ? "weather" : "farm")}
            >
              <span>Check Spray Window</span>
              <ChevronRight size={14} />
            </button>
          </div>

          <div className="use-case-card">
            <span className="use-case-badge crop-badge">Rotation Planning</span>
            <h4>"What should I plant after harvesting cotton?"</h4>
            <p>
              Prevent soil exhaustion. The recommendation engine applies crop rotation
              penalties and recommends restorative legumes like Pigeon Pea or Harbara to
              naturally replenish nitrogen.
            </p>
            <button
              className="use-case-action-link"
              onClick={() => go(activeFarm ? "crops" : "farm")}
            >
              <span>View Crop Recommendations</span>
              <ChevronRight size={14} />
            </button>
          </div>

          <div className="use-case-card">
            <span className="use-case-badge doctor-badge">Pest & Blight Alert</span>
            <h4>"What are these yellow and brown spots on my leaves?"</h4>
            <p>
              Take a leaf photograph. Gemini Vision identifies the pathogen, estimates
              severity, provides organic biocontrol recipes, and dispatches uncertain cases to
              local extension officers.
            </p>
            <button
              className="use-case-action-link"
              onClick={() => go(activeFarm ? "diagnose" : "farm")}
            >
              <span>Open Plant Doctor</span>
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </section>

      {/* Verified Data Sources & Provenance Panel */}
      <VerifiedDataSourcesPanel t={t} />
    </>
  );
};
