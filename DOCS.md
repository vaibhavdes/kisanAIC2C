# KISANAI C2C — Developer Reference & Architecture Map (DOCS.md)

> **Quick Summary**: KISANAI C2C is built as a high-performance, single-container deployable application combining a Python 3.12 FastAPI modular monolith backend with a React 18 + Vite + TypeScript frontend. This document provides clear, one-liner architectural explanations of every directory, backend subcomponent, and frontend subcomponent.

---

## 1. High-Level Project Structure (Root)

| Path | Purpose / Description |
|---|---|
| [`apps/`](apps/) | Frontend applications workspace (contains the Vite + React TypeScript single-page application). |
| [`services/`](services/) | Backend services workspace (contains the FastAPI application, domain rules, providers, and test suites). |
| [`data/`](data/) | Version-controlled agricultural baselines, ICAR standards, and district agronomic profiles. |
| [`contracts/`](contracts/) | Standardized JSON schemas governing cross-border regenerative practice bundle exports and imports. |
| [`config/`](config/) | Configuration templates for local development and Google Cloud Run deployment. |
| [`infra/`](infra/) | Infrastructure-as-code automation and Cloud Run container deployment scripts. |
| [`static/`](static/) | Pre-built production web bundle served directly by FastAPI for single-origin container deployments. |
| [`Dockerfile`](Dockerfile) | Multi-stage production container build (Stage 1: Node.js frontend build; Stage 2: Python 3.12 API runtime). |
| [`.dockerignore`](.dockerignore) | Declares build context exclusions to optimize container size and image caching. |
| [`.gcloudignore`](.gcloudignore) | Prevents local caches, secrets, and virtual environments from uploading during Cloud Build. |
| [`.gitignore`](.gitignore) | Comprehensive Git exclusion list for credentials, session databases, media caches, and build artifacts. |
| [`.env.example`](.env.example) | Secret-free environment variable template documenting all supported cloud and local configuration flags. |

---

## 2. Backend Subcomponents (`services/api/`)

### Core API & Domain Layer (`services/api/src/kisanai_c2c/`)

| File | One-Liner Description |
|---|---|
| [`main.py`](services/api/src/kisanai_c2c/main.py) | FastAPI application entry point; exposes REST endpoints, CORS middleware, and mounts static SPA delivery. |
| [`models.py`](services/api/src/kisanai_c2c/models.py) | Strongly typed Pydantic v2 schemas defining entities (Farms, Evidence, SoilTests, Advisories, Diagnoses). |
| [`domain.py`](services/api/src/kisanai_c2c/domain.py) | Pure deterministic agronomy rules; computes crop suitability scores, water demands, rotation rules, and operational windows. |
| [`service.py`](services/api/src/kisanai_c2c/service.py) | Application service orchestrator; coordinates storage, provider caching, evidence ingestion, and AI prompt execution. |
| [`settings.py`](services/api/src/kisanai_c2c/settings.py) | Pydantic BaseSettings management reading environment variables with safe offline defaults. |
| [`store.py`](services/api/src/kisanai_c2c/store.py) | Pluggable DocumentStore abstraction supporting both local zero-setup SQLite (`sqlite3`) and Google Cloud Firestore. |
| [`auth.py`](services/api/src/kisanai_c2c/auth.py) | Pluggable actor resolver supporting header-based local development identity and Firebase Authentication JWT tokens. |
| [`media.py`](services/api/src/kisanai_c2c/media.py) | Media storage abstraction supporting local file system storage for development and Google Cloud Storage (GCS) for production. |

### External Sensor & AI Providers (`services/api/src/kisanai_c2c/providers/`)

| File | One-Liner Description |
|---|---|
| [`weather.py`](services/api/src/kisanai_c2c/providers/weather.py) | Meteorological engine; queries live IMD APIs (primary) and Open-Meteo high-resolution ECMWF forecasts (fallback). |
| [`satellite.py`](services/api/src/kisanai_c2c/providers/satellite.py) | Biophysical remote sensing; queries Google Earth Engine Sentinel-2 imagery for median NDVI, NDWI, and NDMI indices. |
| [`gemini.py`](services/api/src/kisanai_c2c/providers/gemini.py) | Multimodal GenAI adapter; grounds Gemini 2.5 Flash on field evidence for crop plans, vision leaf diagnosis, and follow-up chat. |
| [`voice.py`](services/api/src/kisanai_c2c/providers/voice.py) | Vernacular voice gateway; interfaces Google Cloud Speech-to-Text (STT) and Text-to-Speech (TTS) for regional Indian languages. |

### Baseline Context Loaders (`services/api/src/kisanai_c2c/data/`)

| File | One-Liner Description |
|---|---|
| [`maharashtra_agri_context.py`](services/api/src/kisanai_c2c/data/maharashtra_agri_context.py) | In-memory loader caching 32 Maharashtra district profiles, IMD rainfall normals, and ICAR N-P-K benchmarks for instant sub-millisecond retrieval. |

### Data Warehousing & BigQuery Pipelines (`services/api/scripts/`)

| File | One-Liner Description |
|---|---|
| [`ingest_to_bigquery.py`](services/api/scripts/ingest_to_bigquery.py) | Automated ETL pipeline creating datasets, executing dry-run validation, and loading baseline profiles into Google BigQuery. |
| [`ingest_regional_data.py`](services/api/scripts/ingest_regional_data.py) | Ingestion utility enforcing SHA-256 composite-key deduplication on raw government agricultural census CSV records. |

### Automated Test Suites (`services/api/tests/`)

| File | One-Liner Description |
|---|---|
| [`test_domain.py`](services/api/tests/test_domain.py) | Offline unit tests validating crop eligibility, rainfall summing, rotation penalties, and operational weather indicators. |
| [`test_service_integration.py`](services/api/tests/test_service_integration.py) | End-to-end service tests covering farm creation, PIN lookups, soil test persistence, advisory generation, and chat timeouts. |

---

## 3. Frontend Subcomponents (`apps/web/src/`)

### Core App & Communication

| File | One-Liner Description |
|---|---|
| [`App.tsx`](apps/web/src/App.tsx) | Main React root application; manages 5-step pipeline navigation, farm state, background evidence syncing, and language switching. |
| [`main.tsx`](apps/web/src/main.tsx) | React DOM entry point mounting the root `<App />` component to the DOM. |
| [`api.ts`](apps/web/src/api.ts) | Lightweight HTTP wrapper handling JSON requests, multipart file uploads, and session actor identification headers. |
| [`styles.css`](apps/web/src/styles.css) | Custom responsive CSS design system styled with agricultural palette, cards, sliders, and mobile bottom navigation. |

### Pipeline Stage & Feature Views (`apps/web/src/views/`)

| View | One-Liner Description |
|---|---|
| [`HomeView.tsx`](apps/web/src/views/HomeView.tsx) | Landing screen displaying value proposition, 5-stage workflow visualizer, and CTA to start farm profiling. |
| [`FarmFormView.tsx`](apps/web/src/views/FarmFormView.tsx) | **Stage 1**: Interactive Leaflet farm plotter; supports GPS geolocation, 6-digit PIN lookup, village dropdown, and polygon corner plotting. |
| [`WeatherView.tsx`](apps/web/src/views/WeatherView.tsx) | **Stage 2**: Live meteorology dashboard; displays 7-day rainfall forecast bars, IMD alerts, and 4 operational farming action windows. |
| [`SoilView.tsx`](apps/web/src/views/SoilView.tsx) | **Stage 3**: Soil health input view; provides Soil Health Card OCR upload, manual value entry (with partial support), and silent regional baselines. |
| [`CropRecView.tsx`](apps/web/src/views/CropRecView.tsx) | **Stage 4**: Multi-factor crop ranking view; details suitability scores across weather, soil pH, crop rotation, and regenerative practices. |
| [`AdvisoryView.tsx`](apps/web/src/views/AdvisoryView.tsx) | **Stage 5**: Actionable field plan view; presents stratified management zones, actionable tasks with accept/decline buttons, voice playback, and ephemeral chat. |
| [`DiagnoseView.tsx`](apps/web/src/views/DiagnoseView.tsx) | **Plant Doctor**: Standalone leaf pathology scanner; uploads photos to Gemini Multimodal Vision for organic remedies and expert escalation. |
| [`ExpertView.tsx`](apps/web/src/views/ExpertView.tsx) | **Knowledge Bank**: Extension interface for agronomists to review escalated diagnoses, author regenerative practices, and export C2C bundles. |
| [`SoilCardSection.tsx`](apps/web/src/views/SoilCardSection.tsx) | Compact inline component embedded in farm creation for quick Soil Health Card photo upload and OCR verification. |

### Reusable UI Components (`apps/web/src/components/`)

| Component | One-Liner Description |
|---|---|
| [`Header.tsx`](apps/web/src/components/Header.tsx) | Top application bar containing brand logo, live node badge, language modal toggle, and quick shortcut to Plant Doctor. |
| [`PipelineStepper.tsx`](apps/web/src/components/PipelineStepper.tsx) | Visual 5-stage breadcrumb tracker showing the farmer's active position in the decision workflow. |
| [`MobileNav.tsx`](apps/web/src/components/MobileNav.tsx) | Fixed bottom navigation bar optimized for mobile smartphones in the field. |
| [`LanguageModal.tsx`](apps/web/src/components/LanguageModal.tsx) | Interactive modal dialog allowing farmers to switch seamlessly between English, Hindi, Marathi, Telugu, and Kannada. |
| [`VerifiedDataSourcesPanel.tsx`](apps/web/src/components/VerifiedDataSourcesPanel.tsx) | Informational modal listing exact official data providers (IMD, Sentinel-2, ICAR-NBSS&LUP, Open-Meteo). |

### Utilities, Constants & Types

| Path | One-Liner Description |
|---|---|
| [`utils/weather.ts`](apps/web/src/utils/weather.ts) | Parses heterogeneous weather snapshots into typed 7-day forecast series, current metrics, and IMD warning levels. |
| [`utils/geo.ts`](apps/web/src/utils/geo.ts) | Geospatial calculation helpers (e.g. computing boundary acreage from plotted polygon latitude/longitude coordinates). |
| [`constants/localization.ts`](apps/web/src/constants/localization.ts) | Complete multilingual dictionary supporting English (`en-IN`), Hindi (`hi-IN`), Marathi (`mr-IN`), Telugu (`te-IN`), and Kannada (`kn-IN`). |
| [`constants/crops.ts`](apps/web/src/constants/crops.ts) | Canonical crop names, multilingual labels, and default season suitability metadata. |
| [`constants/districts.ts`](apps/web/src/constants/districts.ts) | Complete directory of Maharashtra agricultural districts and baseline coordinates. |
| [`constants/statusTranslations.ts`](apps/web/src/constants/statusTranslations.ts) | Localized status descriptors for soil moisture, vegetation vigor, and weather risk categories. |
| [`types/index.ts`](apps/web/src/types/index.ts) | Core TypeScript interfaces defining view routes, supported locales, and API response contracts. |

---

## 4. Data Assets Tier (`data/agri_baselines/`)

| File | One-Liner Description |
|---|---|
| [`maharashtra_district_agri_profiles.json`](data/agri_baselines/maharashtra_district_agri_profiles.json) | Comprehensive 32-district dataset containing 30-year IMD rainfall normals, soil orders, typical pH, SOC %, and staple crops. |
| [`soil_npk_standards.json`](data/agri_baselines/soil_npk_standards.json) | Official ICAR Soil Health rating thresholds for Low / Medium / High classification of Nitrogen, Phosphorus, Potassium, and micronutrients. |
| [`crop_agronomy_catalog.json`](data/agri_baselines/crop_agronomy_catalog.json) | ICAR agronomic guidelines detailing water requirements, sowing windows, seed rates, and critical irrigation stages per crop. |

---

## 5. Developer Quick Start Commands

```bash
# 1. Run Backend Locally (FastAPI)
cd services/api
PYTHONPATH=src uvicorn kisanai_c2c.main:app --host 127.0.0.1 --port 8080 --reload

# 2. Run Frontend Locally (Vite Dev Server with API Proxy)
cd apps/web
npm run dev

# 3. Execute Offline Backend Test Suite (25 Tests)
PYTHONPATH=services/api/src python3 -m pytest services/api/tests -v

# 4. Build Production Static Assets
npm --prefix apps/web run build
rm -rf static/* && cp -r apps/web/dist/* static/
```
