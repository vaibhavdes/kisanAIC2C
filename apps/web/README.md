# KISANAI C2C Web Application (`apps/web`)

Responsive React 18 + TypeScript single-page application built with Vite and Lucide icons. Designed for smallholder farmers and extension workers with mobile-first usability and 5-language localization.

## Features

- **Language Support**: 100% complete translations in English (`en-IN`), Hindi (`hi-IN`), Marathi (`mr-IN`), Telugu (`te-IN`), and Kannada (`kn-IN`).
- **Dynamic Field Setup**:
  - 1-click GPS detection with OpenStreetMap Nominatim reverse geocoding to auto-fill State, District, and Village.
  - Interactive leaflet-based field coordinate pin placement.
  - Dynamic land size input with unit conversion (acres, hectares, gunthas).
  - Maharashtra & Indian crop catalog with vernacular aliases.
  - Dual soil context: upload Soil Health Card for OCR extraction or select 1-click ICAR/NBSS&LUP regional baseline.
- **GeoPard Multi-Zone Satellite Dashboard**:
  - High-contrast 5-zone quantile stratification table (Color, Zone, Canopy status label, Range, Area in acres, Share %, Median).
  - Real Sentinel-2 NDVI, NDMI, and NDWI indices served via server-side image proxy (`GET /api/v1/farms/{id}/satellite/image`).
  - Plot boundary overlay tag and automated biophysical canopy narrative.
- **Observation Timestamps Strip**: Explicit scene acquisition, weather observation, and soil testing dates to ensure transparency.
- **Operational Weather Action Windows**: Real-time evaluation of Sowing Readiness, Foliar Spraying Window, Irrigation Advisory, and Field Drainage & Runoff Risk.
- **Visual Plant Doctor**: Multimodal leaf disease diagnostics with Gemini Vision, optional growth stage & symptom selection, and escalation to agronomist review cases.
- **Regenerative Knowledge Bank & Sovereign C2C Exchange**:
  - Pre-seeded verified practices with 1-click JSON bundle export.
  - Sample bundle importer with schema validation, cryptographic SHA-256 verification, and destination node review.

## Scripts

```bash
# Start development server
npm run dev

# Run TypeScript typecheck
npm run typecheck

# Build optimized production bundle to dist/
npm run build
```
