# KISANAI developer map

## Repository

| Path | What it holds |
|---|---|
| `apps/web/` | React 18 + Vite + TypeScript farmer app and expert workspace |
| `services/api/` | FastAPI service, recommendation engine, providers and tests |
| `contracts/` | JSON Schemas exchanged between nodes (agronomy pack, practice bundle) |
| `data/crops/global_crop_catalog.json` | ~36 crops: EcoCrop ranges, cycle, water class, N-fixing, names in 8 languages |
| `data/practices/regenerative_practices.json` | Regenerative practice catalog with localized names (used by the engine) |
| `data/practices/practice_library.json` | Detailed practice write-ups loaded into a node's library as drafts for expert review |
| `data/packs/*.json` | Bundled regional agronomy packs (`IN-MH`, `IN-PB`, `IN-UP`, `BR-PR` with per-municipality soybean windows) |
| `data/soil/interpretation.json` | Official soil-test interpretation schemes by region (Soil Health Card, Embrapa Paraná) |
| `data/i18n/en.json` | English farmer UI strings, shared by the web app and the API translator |
| `static/` | Built web app served by the API (`npm run build:static`) |
| `infra/cloud-run/` | `deploy-nodes.sh` deploys the Maharashtra, North India (Punjab + UP) and Paraná nodes with their Scheduler jobs |
| `config/cloud-run.example.yaml` | Env-vars file template for one node |

## Backend (`services/api/src/kisanai_c2c/`)

| Module | Responsibility |
|---|---|
| `main.py` | HTTP routes, error mapping, geo lookups (PIN, reverse, search), chat sessions, SPA serving |
| `service.py` | Application service: farms, evidence refresh, recommendations, plans, diagnoses, cases, practices, packs, node exchange, dashboard |
| `engine.py` | `RecommendationEngine`: sowing windows (pack or temperature search), water balance, EcoCrop temperature fit, soil pH/texture, groundwater, rotation, regenerative score, rejection reasons |
| `operations.py` | Weekly operational indicators from the forecast: sowing readiness, spray window, irrigation, drainage, temperature extremes, disease-risk weather, IMD warnings |
| `knowledge.py` | Loads the crop catalog, practices and packs; crop aliases in local scripts; ISO subdivision codes; season helpers |
| `soil.py` | Soil ratings from the regional scheme and the effective soil (measured > farmer > estimate) |
| `models.py` | Pydantic models shared by API and store |
| `store.py` | Document store: SQLite (filters in SQL) or Firestore |
| `media.py` | Upload storage: local directory or GCS |
| `auth.py` | Anonymous device actors (`X-Actor-Id`) and expert access code (`X-Expert-Token`) |
| `settings.py` | Environment configuration (see `.env.example`) |
| `providers/weather.py` | Open-Meteo daily + hourly forecast, IMD district warnings (India only) |
| `providers/land.py` | Climate normals (Open-Meteo ERA5, fallback WorldClim + Hargreaves PET), SoilGrids soil, WorldCover land cover, WRI Aqueduct water risk |
| `providers/satellite.py` | Sentinel-2 indices, zone areas, neighbour comparison, server-rendered thumbnails |
| `providers/gemini.py` | Vertex AI Gemini: plan writing, photo diagnosis, Soil Health Card extraction, chat, district brief |
| `providers/voice.py` | Google Speech-to-Text and Text-to-Speech (best voice per language discovered automatically) |
| `providers/translate.py` | Cloud Translation for node languages without a dictionary; language names |
| `providers/bigquery.py` | Daily publish of k-anonymous shared data to the node's BigQuery dataset |

Scripts in `services/api/scripts/`:
- `build_crop_catalog.py` builds the crop catalog from the EcoCrop CSV;
- `build_agronomy_packs.py` builds the state packs and validates them against the contract.

Tests (`services/api/tests/`) run offline with in-memory stores:
- `test_engine.py` covers ranking, windows, water balance and rejections;
- `test_service.py` covers privacy, plans, outcomes, exchange, k-anonymity and seeding.

## Frontend (`apps/web/src/`)

| Path | Responsibility |
|---|---|
| `App.tsx` | Farm loading and selection, language, view routing (map form and expert views are lazy-loaded) |
| `api.ts` | Fetch wrapper with device ID and expert code headers, uploads, text-to-speech |
| `hooks.ts` | `useResource` (shared 10-minute cache), `invalidate`, `useCropName` |
| `constants/i18n.ts`, `constants/locales/` | Hand-written translations (en, hi, mr, te, kn); other node languages are fetched from `/api/v1/i18n/{locale}`; expert strings are English only |
| `utils/text.ts` | Turns engine codes and parameters into localized sentences |
| `components/` | Header, language modal, step bar, mobile nav, Leaflet field map, shared UI pieces |
| `views/` | Home, FarmForm, Weather, Soil, CropRec, Advisory (plan, satellite, chat), Diagnose, Expert |

## Common commands

```bash
PYTHONPATH=services/api/src uvicorn kisanai_c2c.main:app --port 8080   # API
cd apps/web && npm run dev                                               # web dev server
cd apps/web && npm run build:static                                      # refresh static/
PYTHONPATH=services/api/src python -m pytest services/api/tests -q       # tests
```
