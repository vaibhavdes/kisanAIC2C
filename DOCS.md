# KISANAI — Developer Guide

One container: a FastAPI backend (Python 3.12) that also serves the React + Vite frontend.

## Layout

| Path | What it is |
|---|---|
| `apps/web/` | React + TypeScript frontend |
| `services/api/` | FastAPI backend, tests and data-loading scripts |
| `data/agri_baselines/` | District profiles, soil rating thresholds, crop catalogue |
| `static/` | Built frontend, served by FastAPI in the container |
| `infra/cloud-run/` | Cloud Run deploy script |
| `Dockerfile` | Builds the frontend, then the Python runtime |

## Backend (`services/api/src/kisanai_c2c/`)

| File | What it does |
|---|---|
| `main.py` | HTTP routes, PIN / GPS / IP location lookup, serves the frontend |
| `service.py` | Ties farms, soil tests, weather, satellite, Gemini and expert cases together; refetches stale weather |
| `weather_ops.py` | Turns the forecast into sowing, spraying (incl. hourly windows), irrigation, drainage, heat and disease advice in 5 languages |
| `domain.py` | Crop scoring: season, water, soil/pH, rain and temperature, last crop, district; reasons in 5 languages |
| `fertilizer.py` | Soil-test-based dose of N, P, K converted to DAP, urea and MOP bags |
| `satellite_explain.py` | Plain-language explanation of a satellite map from its measured zone areas |
| `models.py` | Pydantic models |
| `store.py` | Document store: SQLite (local) or Firestore |
| `media.py` | Uploaded photos: local folder or Cloud Storage |
| `auth.py` | Local headers in development, Firebase tokens in production |
| `settings.py` | Environment settings (see `.env.example`) |
| `providers/weather.py` | Open-Meteo (7 past + 7 forecast days, 72 hours, soil moisture); IMD warnings when configured |
| `providers/satellite.py` | Earth Engine Sentinel-2: latest clear scene, indices, measured zone areas, cached thumbnails |
| `providers/gemini.py` | Gemini on Vertex AI: action plan, soil card reading, plant photo check, chat |
| `providers/voice.py` | Google Cloud Speech-to-Text and Text-to-Speech |
| `data/maharashtra_agri_context.py` | Loads the district profiles |

Scripts in `services/api/scripts/` validate the baseline data and load it into BigQuery.

## Frontend (`apps/web/src/`)

| Path | What it is |
|---|---|
| `App.tsx` | Farm selection, data loading, screen switching |
| `views/HomeView.tsx` | Today on the farm, quick links, "How KISANAI helps" panel |
| `views/FarmFormView.tsx` | Add a farm by PIN code or GPS and mark the field on a map |
| `views/WeatherView.tsx` | Forecast, field-work advice cards, day-by-day table |
| `views/SoilView.tsx` | Soil values (test or district average), card upload, fertilizer plan |
| `views/CropRecView.tsx` | Ranked crops with reasons, by season |
| `views/AdvisoryView.tsx` | Satellite crop health, Gemini field plan, Krishi Mitra chat |
| `views/DiagnoseView.tsx` | Plant doctor and expert replies |
| `views/ExpertView.tsx` | Expert queue for uncertain plant doctor cases |
| `components/InfoTip.tsx` | (i) explanations and Listen buttons |
| `components/PlatformInfo.tsx` | Homepage "How KISANAI helps" panel |
| `constants/localization.ts` | Interface text in English, Hindi, Marathi, Telugu, Kannada |
| `constants/glossary.ts` | Plain-language explanations of technical terms |
| `constants/platformInfo.ts` | Homepage panel text |
| `utils/voice.ts`, `utils/weather.ts`, `utils/season.ts`, `utils/geo.ts` | Read-aloud, evidence parsing, current season, area calculation |

## Running locally

```bash
# Backend + built frontend on http://127.0.0.1:8080
PYTHONPATH=services/api/src python3 -m uvicorn kisanai_c2c.main:app --port 8080

# Frontend with hot reload (proxies /api to the backend)
npm --prefix apps/web run dev

# Tests
PYTHONPATH=services/api/src python3 -m pytest services/api/tests

# Rebuild the frontend that the container serves
npm --prefix apps/web run build && rm -rf static/assets && cp -R apps/web/dist/index.html apps/web/dist/assets static/
```
