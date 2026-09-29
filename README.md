# KISANAI

**Farm advice from satellite, soil and weather, in the farmer's language, on an open network where Indian states, and BRICS partner countries, share agricultural knowledge.**

Built for *Build with AI: Code for Communities, Second Edition*, Track 04 AgriN & Regenerative Agricultural Intelligence (BRICS theme: Cooperation).

Three nodes run on Google Cloud: two Indian state nodes that cooperate with each other, and a Brazilian node that shows the same network working across borders. Each keeps its data in its own region.

| Node | Region | Languages |
|---|---|---|
| [India, Maharashtra](https://kisanai-in-mh-313370978552.asia-south1.run.app) | `asia-south1` (Mumbai) | Marathi, Hindi, English |
| [India, Punjab and Uttar Pradesh](https://kisanai-in-north-313370978552.asia-south2.run.app) | `asia-south2` (Delhi) | Hindi, Punjabi (machine-translated), English |
| [Brazil, Paraná](https://kisanai-br-pr-313370978552.southamerica-east1.run.app) | `southamerica-east1` (São Paulo) | Portuguese, English |

Licence: Apache-2.0.

---

## The problem

A smallholder deciding what to sow next week needs answers to concrete questions:
- Is it time to sow?
- Can I spray tomorrow?
- Which crop fits my water, my soil and my last season?
- What is wrong with this leaf?

Agricultural institutions publish good crop calendars, and satellites and forecasts are free. But the calendar sits in a PDF, the forecast isn't tied to field operations, and nothing combines them for one field. Each country and state also keeps its own knowledge, with no shared digital infrastructure for another to reuse it.

## What KISANAI does

| Farmer need | How it is answered | Evidence behind it |
|---|---|---|
| **What to sow now** | A deterministic engine ranks ~36 crops for the field on today's date. It checks the regional sowing window and legal dates, a seasonal water balance (FAO-56 style: PET × Kc against effective rain, stored soil moisture and irrigation), temperature fit (FAO EcoCrop), measured soil pH, groundwater status and rotation. Every crop comes with its reasons. | Regional agronomy pack, Open-Meteo ERA5 normals, ISRIC SoilGrids, soil test, farmer inputs |
| **Regenerative choice** | Each option also gets a *soil-friendly* score (N-fixing, water use, residue, diversity), plus practices that fit the region, such as no-till, inoculation, residue mulching, BBF or AWD. | Practice catalog; regional priority practices |
| **This week's operations** | Sowing readiness from soil moisture. Spray windows are computed hour by hour (wind, rain probability, 6 h dry after). Also irrigation need from ET₀, drainage risk, heat and cold extremes, and disease-risk weather (leaf wetness, late-blight Smith periods, blast). | Open-Meteo hourly forecast; IMD warnings in India |
| **Field condition** | Sentinel-2 NDVI, NDMI and NDWI zones over the plotted boundary, with the area in each class. The field median is compared with nearby cropland from ESA WorldCover. | Google Earth Engine |
| **A plan in plain words** | Gemini writes a short plan in the farmer's language using the engine's crops, the field's satellite readings and the week's windows. It may only use practices the engine allowed. The farmer marks each step *will do* or *not for me*, and later *worked / partly / didn't work*. | Engine output + evidence IDs |
| **Plant Doctor** | Gemini reads a leaf photo and returns structured screening: findings, likely causes, safe next steps and prevention. Poor photos, low confidence and fast-spreading diseases go to an expert queue, and the expert's reply shows up in the farmer's app. | Photo + local weather risk |
| **Soil test** | Upload a photo or PDF of the lab report (India's Soil Health Card or any lab report) and Gemini extracts the values and explains them. pH and salinity are rated everywhere; nutrient ratings use the country's official limits where they are encoded (India). | Farmer's report |
| **Voice** | Ask by voice and hear answers read aloud. Google Speech-to-Text, plus the best available Text-to-Speech voice for the language, found automatically. | |

### Why the AI does not pick crops

Gemini explains, reads photos and writes in the farmer's language. Crop ranking, sowing windows and spray windows come from transparent rules over measured data. That keeps them reproducible, auditable by regional experts and identical in every language. When evidence is missing, the app says so; it never fills the gap with made-up numbers.

## BRICS AgriN network

Each deployment is a **node** run by an agriculture department for one or more states or provinces (ISO 3166-2 codes such as `IN-MH`, `IN-PB`, `BR-PR`). Indian states cooperate node to node, and the same protocol reaches BRICS partners.

- **Agronomy packs** are regional crop calendars: sowing windows by season, irrigation needs, groundwater category, legal sowing dates and priority practices. They follow [`contracts/agronomy-pack.schema.json`](contracts/agronomy-pack.schema.json) (JSON Schema 2020-12, ISO codes, crop IDs plus scientific names), so any BRICS country can publish one.
  - The **Maharashtra**, **Punjab** and **Uttar Pradesh** packs come from the state agricultural universities' packages of practice, with the CGWB groundwater category and legal dates such as Punjab's paddy-transplanting date (Preservation of Subsoil Water Act 2009).
  - The **Paraná** pack comes from the CONAB planting calendar. Each of Paraná's 399 municipalities (IBGE register) carries its legal soybean window from the MAPA/ADAPAR sanitary-break regions.
- Each node publishes a manifest at `/.well-known/agrin-node`. An officer on another node imports a pack **only from an allowlisted peer**; it is schema-validated, deduplicated by digest and **used only after local expert approval**. A Punjab farm registered on the Maharashtra node switches from the global baseline to Punjab's calendar once the Maharashtra expert approves the pack; the same works for Paraná across borders.
- **Practice bundles** ([`contracts/practice-bundle.schema.json`](contracts/practice-bundle.schema.json)) travel the same way.
  - Each node's write-ups ([`data/practices/practice_library.json`](data/practices/practice_library.json)) start as drafts and are published only after its expert reviews them.
  - A bundle outside its declared countries is flagged and can't be approved blindly; for example, Maharashtra's black-soil BBF is flagged in Brazil.
  - Field evidence is attached once at least 5 farmer outcomes exist.
- **Signals** are district-level crop-health counts, published only for groups of 5 or more reports. Officers see their peers' signals in the expert workspace, which gives early warning across borders.
- **Shared data on BigQuery:** every day, Cloud Scheduler asks each node to publish its k-anonymous calendars, signals and practice outcomes to a BigQuery dataset in its own region. The datasets are listed in **BigQuery Analytics Hub** exchanges (one per region: `brics_agrin_in`, `brics_agrin_in_north`, `brics_agrin_br`) that other countries' agencies can subscribe to.

A farm outside any pack region, anywhere in the world, gets the **global baseline**: FAO EcoCrop climate and soil fit plus the water balance, with sowing dates found by temperature.

### Languages without hand-written files

A node lists its farmer languages in `NODE_LANGUAGES`.
- **Hand-written dictionaries:** English, Hindi, Marathi, Telugu and Kannada ship with the app.
- **Any other language** (for example `pt-BR` on the Brazil node) is machine-translated once from [`data/i18n/en.json`](data/i18n/en.json) with **Google Cloud Translation** and cached in the node's database. This covers the UI strings and any missing crop or practice names; `{placeholders}` are protected, and a string that fails the check stays in English.
- **What adapts automatically:** Gemini's output language and the Text-to-Speech voice follow the node's languages. A new country's node needs configuration, not code.

## Google Cloud services

| Service | Use |
|---|---|
| Cloud Run | One service per country node, in that country's region; dedicated least-privilege service account |
| Vertex AI Gemini 3.5 Flash | Plans, leaf diagnosis, soil report reading, chat, district brief (asia-south1; global endpoint for the Brazil node) |
| Google Earth Engine | Sentinel-2 indices, SoilGrids, WorldCover, WRI Aqueduct water risk, WorldClim fallback |
| Cloud Firestore | One database per node in its region (`kisanai-in-mh`, `kisanai-in-north`, `kisanai-br-pr`) |
| Cloud Storage | Private buckets per node for leaf photos and soil reports |
| Cloud Translation | Node languages without a hand-written dictionary |
| Speech-to-Text / Text-to-Speech | Voice questions and read-aloud answers |
| BigQuery + Analytics Hub | Cross-country sharing of k-anonymous agricultural data |
| Cloud Scheduler | Daily publish job, authenticated with a Google-signed OIDC token |
| Secret Manager | Per-node expert access codes |
| Cloud Build / Artifact Registry | Source deployments |

## Privacy

- No login and no phone number. Each device gets an anonymous ID, and farms are private to that device.
- Chat is not stored; it is wiped after 5 minutes.
- Officers see aggregated dashboards and the cases farmers chose to send. Exchanges between nodes and BigQuery listings carry no personal data and nothing below district level.
- Each country's farm data, photos and shared dataset stay in that country's cloud region.

## Architecture

```
React + Vite (apps/web) ── same origin ──> FastAPI (services/api) on Cloud Run, one service per country node
                                             ├─ engine.py      crop ranking, windows, water balance
                                             ├─ operations.py  sowing / spray / irrigation / disease-risk windows
                                             ├─ providers/     Open-Meteo, IMD, Earth Engine, Gemini, Speech, Translation, BigQuery
                                             ├─ knowledge.py   crop catalog, practices, regional packs, UI strings (data/)
                                             └─ store.py       Firestore (production) or SQLite (development); media in GCS
```

## Data sources and attribution

| Source | Use | Licence / terms |
|---|---|---|
| FAO EcoCrop (via the OpenCLIM EcoCrop database) | Crop temperature, rainfall, pH and soil ranges | Open Government Licence v3 |
| WRI Aqueduct 4.0 (Earth Engine) | Sub-basin water stress and groundwater-table decline for every field, in every country | CC-BY 4.0 |
| ISRIC SoilGrids 2.0 (Earth Engine) | Estimated pH, organic carbon, clay and sand when no soil test exists (averaged within 300 m of the field, or 1.5 km where nearer cells are masked) | CC-BY 4.0 |
| ESA WorldCover v200 (Earth Engine) | Land cover; nearby cropland for comparison | CC-BY 4.0 |
| Copernicus Sentinel-2 SR (Earth Engine) | NDVI / NDMI / NDWI | Copernicus open licence |
| Open-Meteo forecast and ERA5 archive | Hourly and daily forecast, 2015-2024 climate normals | CC-BY 4.0 |
| India Meteorological Department | District warnings in India (when credentials are configured) | IMD terms |
| State agricultural universities' packages of practice (Maharashtra, Punjab, Uttar Pradesh); CGWB Dynamic Ground Water Resources assessment; Punjab Preservation of Subsoil Water Act 2009 | Sowing windows, state groundwater category, legal sowing dates | Cited in each pack |
| India Soil Health Card (ICAR rating limits) | Soil test ratings in India | Cited in `data/soil/interpretation.json` |
| CONAB planting calendar; MAPA Portaria 1.579/2026 and ADAPAR soybean sanitary break; IBGE municipality register; Embrapa Soja P and K table (Sfredo et al. 1999); EMBRAPA practices | Paraná planting windows, per-municipality legal soybean dates, soil ratings with soybean doses, no-till and inoculation | Cited in the pack, soil schemes and practices |
| Esri World Imagery; OpenStreetMap / CARTO labels; Nominatim | Field-plotting map and place search | Esri, ODbL |
| pincodeapi.in | Indian PIN code lookup | Service terms |

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

[`infra/cloud-run/deploy-nodes.sh`](infra/cloud-run/deploy-nodes.sh) deploys the three nodes and their daily publish jobs. [`infra/cloud-run/README.md`](infra/cloud-run/README.md) lists the one-time resources and how to add a state or a country. For a single node, start from [`config/cloud-run.example.yaml`](config/cloud-run.example.yaml).

## Main API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/node` | Node country, regions and farmer languages |
| GET | `/api/v1/i18n/{locale}` | Machine-translated UI strings for a node language |
| POST/GET/PUT/DELETE | `/api/v1/farms[/{id}]` | Farms (private per device, `X-Actor-Id`) |
| GET | `/api/v1/farms/{id}/weather/operational` | Sowing, spray, irrigation, drainage and disease-risk windows |
| GET | `/api/v1/farms/{id}/crop-recommendations` | Ranked crops with reasons, windows and water balance |
| GET | `/api/v1/farms/{id}/satellite/map` | Index zones and neighbour comparison |
| POST | `/api/v1/farms/{id}/soil/extract`, `/soil` | Soil report extraction and saving |
| POST | `/api/v1/farms/{id}/advisories` | AI-written plan grounded in the engine |
| POST | `/api/v1/farms/{id}/diagnoses` | Plant Doctor |
| GET | `/.well-known/agrin-node` | Node manifest |
| GET | `/api/v1/network/packs/{id}`, `/practices/{id}`, `/signals` | Public exchange endpoints |
| POST | `/api/v1/internal/publish` | Daily BigQuery publish (Cloud Scheduler OIDC only) |
| * | `/api/v1/expert/...` | Cases, practices, imports, packs, peer signals, dashboard (`X-Expert-Token`) |

## Honest limitations

- The bundled packs are curated by the team from official sources and still need sign-off by regional experts (the state agricultural universities, IDR-Paraná / EMBRAPA). The app labels them that way.
- Paraná municipalities are assigned to the three ADAPAR soybean regions through their IBGE mesoregion, following ADAPAR's geographic description; the portaria's own municipality annex should be checked for border municipalities.
- Paraná soil ratings use Embrapa's table for clay above 40%; lighter soils are shown unrated because Embrapa's Cerrado tables are not encoded.
- WRI Aqueduct has no sub-basin value in some places; the state category (India) or "unknown" is then shown.
- Punjabi and Portuguese UI text is machine-translated and marked as such; a native speaker should review it.
- The global baseline is coarse. It can suggest crops that are climatically possible but not locally grown, and a regional pack fixes that.
- IMD warnings need IMD API credentials. Without them the app uses Open-Meteo only.
- Plant Doctor is screening, not a lab diagnosis. It never names pesticide products or doses.
- The officer access code is a per-node shared secret (kept in Secret Manager). A production rollout should put the expert workspace behind the agency's identity provider.

## Digital Public Good checklist

- Open licence (Apache-2.0 code; packs and practices CC-BY-4.0).
- Open standards: JSON Schema contracts, ISO 3166-2, BCP-47 language tags, scientific crop names.
- Privacy by design: no PII collected, anonymous devices, k ≥ 5 aggregation, data kept in each country's region.
- Documented data sources with licences (above).
- Any BRICS country or state can run its own node, in its own language, and publish its own pack; no central owner.
- Do-no-harm safeguards: expert review for risky diagnoses and imported knowledge, no chemical doses, and honest *unavailable* states instead of invented data.
