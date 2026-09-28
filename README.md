# KISANAI

**Farm advice from satellite, soil and weather, in the farmer's language, on an open network that states can join.**

Built for *Build with AI: Code for Communities, Second Edition*, Track 04 Agricultural Intelligence (AgriN and regenerative agricultural intelligence).

[Live demo](https://kisanai-c2c-313370978552.asia-south1.run.app) · Google Cloud Run (`asia-south1`) · Apache-2.0

---

## The problem

A smallholder deciding what to sow next week needs answers to concrete questions:
- Is it time to sow?
- Can I spray tomorrow?
- Which crop fits my water, my soil and my last season?
- What is wrong with this leaf?

State universities publish good crop calendars, and satellites and forecasts are free. But the calendar sits in a PDF, the forecast is not tied to field operations, and nothing combines them for one field. Each state also keeps its own knowledge, with no standard way for another state to reuse it.

## What KISANAI does

| Farmer need | How it is answered | Evidence behind it |
|---|---|---|
| **What to sow now** | A deterministic engine ranks ~36 crops for the field on today's date. It checks the state sowing window, a seasonal water balance (FAO-56 style: PET × Kc against effective rain, stored soil moisture and irrigation), temperature fit (FAO EcoCrop), measured soil pH, groundwater status and rotation. Every crop comes with its reasons. | State agronomy pack, Open-Meteo ERA5 normals, ISRIC SoilGrids, Soil Health Card, farmer inputs |
| **Regenerative choice** | Each option also gets a *soil-friendly* score (N-fixing, water use, residue, diversity), plus practices that fit it, such as rhizobium, BBF, residue mulching or AWD. | Curated practice catalog; state priority practices |
| **This week's operations** | Sowing readiness from soil moisture. Spray windows are computed hour by hour (wind, rain probability, 6 h dry after). Also irrigation need from ET₀, drainage risk, heat and cold extremes, and disease-risk weather (leaf wetness, late-blight Smith periods, blast). | Open-Meteo hourly forecast; IMD warnings where available |
| **Field condition** | Sentinel-2 NDVI, NDMI and NDWI zones over the plotted boundary, with the acreage in each class. The field median is compared with nearby cropland from ESA WorldCover. | Google Earth Engine |
| **A plan in plain words** | Gemini writes a short plan in the farmer's language. It may only use crops and practices the engine allowed, and must cite the numbers. The farmer marks each step *will do* or *not for me*, and later *worked / partly / didn't work*. | Engine output + evidence IDs |
| **Plant Doctor** | Gemini reads a leaf photo and returns structured screening: findings, likely causes, safe next steps and prevention. Poor photos, low confidence and fast-spreading diseases go to an expert queue, and the expert's reply shows up in the farmer's app. | Photo + local weather risk |
| **Soil Health Card** | Upload a photo or PDF and Gemini extracts 12 parameters. Values are rated against Soil Health Card limits and explained. Measured values always override estimates. | Farmer's card |
| **Voice** | Ask by voice and hear answers read aloud (Google Speech-to-Text and Text-to-Speech, with a browser fallback). A short-lived chat is grounded in the same computed windows. | |

Languages: English, हिन्दी, मराठी, తెలుగు, ಕನ್ನಡ. The expert workspace is in English.

### Why the AI does not pick crops

Gemini explains, reads photos and writes in the farmer's language. Crop ranking, sowing windows and spray windows come from transparent rules over measured data. That keeps them reproducible, auditable by state experts and identical in every language. When evidence is missing, the app says so; it never fills the gap with made-up numbers.

## Interoperable state network (AgriN)

Each deployment is a **node** serving one or more states (ISO 3166-2 codes such as `IN-MH`).

- **Agronomy packs** are the state crop calendars: sowing windows by season, irrigation needs, groundwater category, legal sowing dates and priority practices. They follow [`contracts/agronomy-pack.schema.json`](contracts/agronomy-pack.schema.json) (JSON Schema 2020-12, ISO codes, crop IDs plus scientific names), so any country or state can publish one.
- A node publishes a manifest at `/.well-known/agrin-node` listing its packs, practices and signal endpoint.
- An officer on another node can import a pack **only from an allowlisted peer**. It is schema-validated, deduplicated by digest and **used only after expert approval**. Farms in that state immediately switch from the global baseline to the regional calendar.
- **Practice bundles** ([`contracts/practice-bundle.schema.json`](contracts/practice-bundle.schema.json)) travel the same way, with field evidence attached once at least 5 farmer outcomes exist.
- **Signals** are district-level crop-health counts. They are published only for groups of 5 or more reports; no farm, farmer or location is ever shared.

Bundled packs: **Maharashtra, Punjab, Uttar Pradesh**. They are curated from the published state university packages of practice and are marked *pending state expert review*. Farms outside those states, including other BRICS countries, get the **global baseline**: FAO EcoCrop climate and soil fit plus the water balance, with sowing dates found by temperature. The crop catalog includes crops such as teff, cassava, canola and oats, with names in English, Hindi, Marathi, Telugu, Kannada, Portuguese, Russian and Chinese.

## Privacy

- No login and no phone number. Each device gets an anonymous ID, and farms are private to that device.
- Chat is not stored; it is wiped after 5 minutes.
- Officers see aggregated dashboards and the cases farmers chose to send. Exchanges between nodes carry no personal data.

## Architecture

```
React + Vite (apps/web) ── same origin ──> FastAPI (services/api) on Cloud Run
                                             ├─ engine.py      crop ranking, windows, water balance
                                             ├─ operations.py  sowing / spray / irrigation / disease-risk windows
                                             ├─ providers/     Open-Meteo, IMD, Earth Engine, SoilGrids, Gemini, Speech
                                             ├─ knowledge.py   crop catalog, practices, state packs (data/)
                                             └─ store.py       SQLite (dev/demo) or Firestore; media local or GCS
```

## Data sources and attribution

| Source | Use | Licence / terms |
|---|---|---|
| FAO EcoCrop (via the OpenCLIM EcoCrop database) | Crop temperature, rainfall, pH and soil ranges | Open Government Licence v3 |
| ISRIC SoilGrids 2.0 (Earth Engine) | Estimated pH, organic carbon, clay and sand when no soil test exists | CC-BY 4.0 |
| ESA WorldCover v200 (Earth Engine) | Land cover; nearby cropland for comparison | CC-BY 4.0 |
| Copernicus Sentinel-2 SR (Earth Engine) | NDVI / NDMI / NDWI | Copernicus open licence |
| Open-Meteo forecast and ERA5 archive | Hourly and daily forecast, 2015-2024 climate normals | CC-BY 4.0 |
| India Meteorological Department | District warnings (when credentials are configured) | IMD terms |
| State university packages of practice; CGWB; Punjab Preservation of Subsoil Water Act 2009 | Sowing windows, groundwater category, legal sowing dates | Cited per pack |
| Esri World Imagery; OpenStreetMap / CARTO labels; Nominatim | Field-plotting map and place search | Esri, ODbL |
| pincodeapi.in | PIN code lookup | Service terms |

## Run locally

```bash
cp .env.example .env.local        # set GOOGLE_CLOUD_PROJECT; run `gcloud auth application-default login`
pip install -e "services/api[dev]"
PYTHONPATH=services/api/src uvicorn kisanai_c2c.main:app --port 8080
```

```bash
cd apps/web && npm ci && npm run dev          # http://localhost:5173, proxies /api to :8080
npm run build:static                          # refresh static/ served by the API
```

```bash
PYTHONPATH=services/api/src python -m pytest services/api/tests -q
```

To rebuild the data from sources, run `python services/api/scripts/build_crop_catalog.py` (it needs the EcoCrop CSV) and `python services/api/scripts/build_agronomy_packs.py`.

## Deploy

- **One node:** `gcloud run deploy <service> --source . --env-vars-file config/cloud-run.local.yaml`. Start from [`config/cloud-run.example.yaml`](config/cloud-run.example.yaml).
- **Two peer test nodes:** [`infra/cloud-run/deploy-test-nodes.sh`](infra/cloud-run/deploy-test-nodes.sh) deploys `kisanai-c2c-test` (MH+UP) and `kisanai-node-pb` (PB).

For durable data, use `STORE_PROVIDER=firestore` and `MEDIA_PROVIDER=gcs`. SQLite in `/tmp` is only for demos.

## Main API

| Method | Path | Purpose |
|---|---|---|
| POST/GET/PUT/DELETE | `/api/v1/farms[/{id}]` | Farms (private per device, `X-Actor-Id`) |
| GET | `/api/v1/farms/{id}/weather/operational` | Sowing, spray, irrigation, drainage and disease-risk windows |
| GET | `/api/v1/farms/{id}/crop-recommendations` | Ranked crops with reasons, windows and water balance |
| GET | `/api/v1/farms/{id}/satellite/map` | Index zones and neighbour comparison |
| POST | `/api/v1/farms/{id}/soil/extract`, `/soil` | Soil Health Card extraction and saving |
| POST | `/api/v1/farms/{id}/advisories` | AI-written plan grounded in the engine |
| POST | `/api/v1/farms/{id}/diagnoses` | Plant Doctor |
| GET | `/.well-known/agrin-node` | Node manifest |
| GET | `/api/v1/network/packs/{id}`, `/practices/{id}`, `/signals` | Public exchange endpoints |
| * | `/api/v1/expert/...` | Cases, practices, imports, packs, dashboard (`X-Expert-Token`) |

## Honest limitations

- Bundled state packs are curated by the team from published sources and still need sign-off by state experts. The app labels them that way.
- The global baseline is coarse. It can suggest crops that are climatically possible but not locally grown, and a regional pack fixes that.
- IMD warnings need IMD API credentials. Without them the app says IMD is unavailable and uses Open-Meteo only.
- Plant Doctor is screening, not a lab diagnosis. It never names pesticide products or doses.
- The officer access code is a shared secret. A production rollout should use the state's identity provider.

## Digital Public Good checklist

- Open licence (Apache-2.0 code; packs CC-BY-4.0).
- Open standards: JSON Schema contracts, ISO 3166-2, scientific crop names.
- Privacy by design: no PII collected, anonymous devices, k ≥ 5 aggregation.
- Documented data sources with licences (above).
- Any state or country can run its own node and publish its own pack; no central owner.
- Do-no-harm safeguards: expert review for risky diagnoses, no chemical doses, and honest *unavailable* states instead of invented data.
