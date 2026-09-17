import React from "react";
import { ShieldCheck } from "lucide-react";
import { TranslationDictionary } from "../types";

interface VerifiedDataSourcesPanelProps {
  t?: TranslationDictionary;
}

export const VerifiedDataSourcesPanel: React.FC<VerifiedDataSourcesPanelProps> = ({ t }) => {
  const sources = [
    {
      name: "India Meteorological Dept. (IMD)",
      icon: "🏛️",
      mode: "Live Feed",
      modeClass: "",
      desc: "Official district weather warnings, rainfall alerts, and 30-year agro-climatic baseline normals.",
      attr: "api.imd.gov.in · Ministry of Earth Sciences"
    },
    {
      name: "Copernicus Sentinel-2 MSI",
      icon: "🛰️",
      mode: "10m Optical",
      modeClass: "",
      desc: "Multispectral satellite passes tracking canopy vegetative vigor (NDVI) and moisture stress (NDMI).",
      attr: "European Space Agency (ESA) & Earth Engine"
    },
    {
      name: "ICAR-NBSS & LUP Database",
      icon: "🌱",
      mode: "Soil Grids",
      modeClass: "baseline",
      desc: "1:250,000 national soil resource mapping providing regional pH and N-P-K nutrient profiles.",
      attr: "National Bureau of Soil Survey & Land Use Planning"
    },
    {
      name: "Open-Meteo Atmospheric Model",
      icon: "🌦️",
      mode: "7-Day ECMWF",
      modeClass: "",
      desc: "Hourly station interpolation for wind speeds, relative humidity, and 7-day cumulative precipitation.",
      attr: "High-resolution seamless weather engine"
    },
    {
      name: "Google Gemini 2.5 Flash",
      icon: "✨",
      mode: "Multimodal AI",
      modeClass: "ai",
      desc: "Zero-hallucination multimodal leaf pathology analysis and vernacular agro-ecological planning.",
      attr: "Google Cloud Vertex AI & Google AI Studio"
    }
  ];

  return (
    <div className="data-sources-panel">
      <div className="data-sources-header">
        <div className="data-sources-title">
          <ShieldCheck size={26} color="var(--green-700)" />
          <div>
            <h3>{t?.data_sources_title || "Verified Data Sources & Regional Provenance"}</h3>
            <p>
              {t?.data_sources_sub ||
                "100% transparent ground truth: official meteorological APIs, satellite constellations, and research databases."}
            </p>
          </div>
        </div>
      </div>
      <div className="data-sources-grid">
        {sources.map((s) => (
          <div key={s.name} className="data-source-card">
            <div className="data-source-head">
              <span style={{ fontSize: "20px" }}>{s.icon}</span>
              <span className={`data-source-mode ${s.modeClass}`}>{s.mode}</span>
            </div>
            <div className="data-source-name">{s.name}</div>
            <p className="data-source-desc">{s.desc}</p>
            <div className="data-source-attr">✓ {s.attr}</div>
          </div>
        ))}
      </div>
    </div>
  );
};
