# KISANAI 🌾
### Localized Weather Forecasts & Explainable Crop Recommendations for Farmers

> **Hackathon Problem Statement — AG-02:** Build a platform that provides farmers with localized weather forecasts and crop recommendations.

**KISANAI provides localized weather forecasts and explainable crop recommendations by combining farm location, weather, soil, water availability, crop history, agronomic data, and satellite observations in one farmer-friendly platform.**

[**Live Demo**](https://kisanai-c2c-313370978552.asia-south1.run.app) · **Google Cloud Run** (`asia-south1`)

---

## Problem & Solution

A weather forecast tells a farmer what may happen, but the real questions are:

- **Is this a good time to sow?**
- **Will rain or wind affect spraying?**
- **Does the crop need irrigation?**
- **Could heavy rain create waterlogging or drainage risk?**

Crop selection raises a different set of questions:

- **Which crops suit the current season?**
- **Which crops fit the available water source?**
- **Is the soil suitable for the crop?**
- **Does recent and forecast weather support it?**
- **Should the previous crop affect the next crop choice?**

**KISANAI brings these decisions together in one platform.**

### Weather Forecasting
KISANAI uses the farm location for a **7-day coordinate-based weather forecast**, combines it with official regional alerts, and converts the forecast into practical guidance for **sowing, spraying, irrigation, and drainage risk**.

### Crop Recommendation
KISANAI combines three levels of information:

- **Farmer-specific:** water availability, current crop, previous crop, uploaded Soil Health Card.
- **Location-specific:** farm coordinates, weather forecast, and parcel-level satellite observations when a boundary is available.
- **Regional & historical:** soil baselines, agro-climatic conditions, crop calendars, groundwater context, and agronomic reference data.

The result is an **explainable crop recommendation** showing why a crop is suitable, why an unsuitable crop was rejected, which condition limits suitability, and what can improve it.

Weather analysis and the selected crop recommendation are then combined into a **field action plan**, available visually and through voice.

---

## Core Capabilities

### 🌦️ Localized Weather & Farm Operations

KISANAI provides:

- 7-day rainfall forecast and rainfall probability
- maximum and minimum temperature
- relative humidity
- wind speed
- reference evapotranspiration (ET₀)
- IMD district warnings and nowcasts

The forecast is converted into four operational decisions:

| Decision | Purpose |
|---|---|
| **Sowing Readiness** | Checks whether upcoming rainfall and field conditions support sowing |
| **Spraying Window** | Uses wind and rainfall conditions to identify safer foliar-spraying periods |
| **Irrigation Guidance** | Compares rainfall with crop water-demand indicators |
| **Drainage Risk** | Highlights heavy-rain periods that may increase waterlogging or runoff risk |

Operational thresholds are configurable.

### 🌾 Explainable Crop Recommendation Engine

The engine evaluates **12 regional crops** across seven factors:

1. Season and sowing window
2. Water availability
3. Soil type and pH compatibility
4. Near-term rainfall forecast
5. Current and previous crop
6. Regional agro-climatic conditions
7. Suitable soil and water-management practices

For each crop, the farmer can see:

- suitability score
- supporting factors
- limiting factors
- rejection reasons for unsuitable crops
- conditions affecting suitability
- corrective guidance

### 📋 Farm Action Plan

AI converts the validated weather, soil, crop recommendation, and agronomic context into a simple action plan containing:

- **what to do**
- **when to do it**
- **why it is recommended**
- **important cautions**

---

## Supporting Capabilities

### 📍 Farm Location & Boundary
- Locate the farm using a **6-digit PIN code** or device GPS.
- Reverse-geocode coordinates to the local place name.
- Use farm coordinates for weather and regional-data lookup.
- Plot the farm boundary for **parcel-level satellite analysis**.

### 🛰️ Satellite Field Analysis
Copernicus Sentinel-2 imagery is processed through Google Earth Engine for:

- **NDVI** — crop vigor and vegetation condition
- **NDWI** — surface water / wetness signal
- **NDMI** — vegetation moisture condition
- **NDRE** — red-edge chlorophyll signal where available

The plotted field can be divided into relative management zones to highlight stronger and weaker areas. Satellite acquisition date and source are displayed with the analysis.

### 🧪 Soil Health Card Reader
Farmers can upload a Soil Health Card image or PDF. AI extracts available values such as:

`pH` · `EC` · `Organic Carbon` · `Nitrogen` · `Phosphorus` · `Potassium` · `Zinc` · `Iron`

Unclear values are flagged for review. If a Soil Health Card is unavailable, regional soil information can be used as a fallback reference and is kept distinct from measured farm data.

### 🔬 Visual Crop Doctor
A farmer can upload an affected leaf, stem, or visible-pest image. The system returns:

- visible symptom observations
- possible causes
- low-risk next steps
- an expert-review flag when the image or diagnosis is uncertain


### 🎙️ Krishi Mitra — Voice & Follow-Up Advisor
Krishi Mitra allows farmers to use **voice or text** to:

- listen to weather, crop, and field recommendations
- ask follow-up questions about the current farm plan
- receive answers using the active farm context

The interface, recommendations, voice input, and advisory playback support:

| Language | Locale |
|---|---|
| English | `en-IN` |
| Hindi | `hi-IN` |
| Marathi | `mr-IN` |
| Telugu | `te-IN` |
| Kannada | `kn-IN` |

Google Cloud Speech-to-Text handles spoken questions and Text-to-Speech handles advisory playback. Follow-up conversation context expires after **5 minutes of inactivity**.

---

## How KISANAI Works

```text
Farmer
  |
  v
PIN Code / GPS
  |
  v
Farm Location
  |
  +--> Optional Boundary --> Satellite Analysis
  |
  v
Farm Details
  |-- Season
  |-- Water availability
  |-- Soil / Soil Health Card
  |-- Current crop
  |-- Previous crop
  |
  v
Data Collection
  |-- IMD alerts
  |-- Coordinate-based weather forecast
  |-- Regional & historical agronomic data
  |-- Satellite observations when boundary is available
  |
  +-------------------------------+
  |                               |
  v                               v
Localized Weather            Crop Recommendation
Analysis                     7-factor evaluation
  |                               |
  +---------------+---------------+
                  |
                  v
       Recommended Crops + Reasons
                  |
                  v
          AI Field Action Plan
                  |
        +---------+----------+
        |         |          |
     Visual     Voice    Krishi Mitra
    Advisory   Playback    Follow-Up
```

---

## System Architecture

```text
+------------------------------------------------------------------+
|                       FARMER APPLICATION                         |
| React + Vite + TypeScript                                       |
| Weather | Crop Recommendations | Farm Map | Soil | Voice | Image |
+-------------------------------+----------------------------------+
                                |
                           HTTPS / JSON
                                |
                                v
+------------------------------------------------------------------+
|                         FASTAPI BACKEND                          |
| API routes | validation | farm data | media | session handling  |
+----------------------+----------------------+--------------------+
                       |                      |
                       v                      v
+--------------------------------+   +-----------------------------+
| AGRONOMIC DECISION ENGINE      |   | AI SERVICES                 |
| weather-operation rules        |   | field action plan           |
| crop-suitability scoring       |   | Soil Health Card extraction |
| soil / rotation checks         |   | crop-image analysis         |
|                                |   | multilingual follow-up      |
+----------------+---------------+   +-----------------------------+
                 |
                 v
+------------------------------------------------------------------+
|                         DATA SOURCES                             |
| IMD | Open-Meteo | Sentinel-2 | OSM | Postal | ICAR | CGWB     |
+-------------------------------+----------------------------------+
                                |
                                v
+------------------------------------------------------------------+
|                    CLOUD & APPLICATION DATA                     |
| Farm data | Advisories | Cloud Storage | BigQuery | TTL cache  |
+------------------------------------------------------------------+
```

---

## Data Sources

KISANAI combines **farm-specific, location-specific, regional, and historical/reference data**, with each source used at its appropriate spatial and temporal level.

| Source | Used For | Data Scope |
|---|---|---|
| **India Meteorological Department (IMD)** | District warnings, nowcasts, severe-weather information | Regional / current |
| **Open-Meteo** | Rainfall, temperature, humidity, wind, ET₀ forecast | Coordinate-based / forecast |
| **Copernicus Sentinel-2 via Google Earth Engine** | Vegetation and moisture analysis | Parcel-level when boundary is available |
| **India Post / postal data** | PIN-code based location information | Postal / regional |
| **pincodeapi.in** | PIN-code lookup in the current implementation | Postal / regional |
| **OpenStreetMap + Nominatim** | Reverse geocoding from latitude and longitude | Location-specific |
| **ICAR / NBSS&LUP references** | Crop and soil agronomic reference information | Reference / regional |
| **Maharashtra agriculture datasets** | Crop, season, agro-climatic information | Regional / historical |
| **Central Ground Water Board (CGWB)** | Groundwater assessment information | Regional / historical |
| **Google Maps Static imagery** | Satellite-style map preview | Visual context |

Fetched evidence can retain its **source and timestamp** so the application can show which information was used for a recommendation.

---


## Regional Data Pipeline & BigQuery

KISANAI uses an automated ETL pipeline to prepare and validate regional and historical agricultural datasets before loading them into **Google BigQuery**.

```text
Open / Regional Data Sources
  |-- IMD 30-year rainfall normals (1991-2020)
  |-- ICAR-NBSS&LUP soil N-P-K & organic-carbon baselines
  |-- ICAR crop water-demand & sowing calendars
  |-- Maharashtra DES crop-yield statistics
  |
  v
services/api/scripts/ingest_regional_data.py
  |-- composite-key deduplication
  |-- SHA-256 checksum validation
  |
  v
services/api/scripts/ingest_to_bigquery.py
  |-- schema validation & mapping
  |-- batch JSON transformation
  |
  v
Google BigQuery - asia-south1
Dataset: kisanai_intelligence
  |-- district_agri_profiles
  |-- soil_npk_standards
  `-- crop_agronomy_catalog
```

### BigQuery Dataset

The pipeline targets:

- **Dataset:** `kisanai_intelligence`
- **Region:** `asia-south1`
- **Primary tables:**
  - `district_agri_profiles` — district rainfall normals, agro-climatic context, soil baselines, groundwater status, primary crops, and dry-spell risk
  - `soil_npk_standards` — ICAR nutrient-rating and soil-reference thresholds
  - `crop_agronomy_catalog` — crop requirements, water demand, sowing windows, and agronomic reference data

The `district_agri_profiles` table contains typed fields such as:

`district` · `subdivision` · `agro_climatic_zone` · `normal_rainfall_mm` · `monsoon_normal_mm` · `predominant_soil` · `available_nitrogen_kg_ha` · `available_phosphorus_kg_ha` · `available_potassium_kg_ha` · `organic_carbon_percent` · `ph_typical` · `groundwater_status` · `primary_crops` · `dryspell_risk_category` · `agronomic_notes`

### ETL Commands

```bash
# Validate local data and schemas without writing to GCP
python3 services/api/scripts/ingest_to_bigquery.py --dry-run

# Generate BigQuery dataset/table DDL
python3 services/api/scripts/ingest_to_bigquery.py \
  --generate-sql \
  --project YOUR_PROJECT_ID

# Upload validated data to BigQuery
python3 services/api/scripts/ingest_to_bigquery.py \
  --upload-bq \
  --project YOUR_PROJECT_ID
```

Live ingestion uses the official `google-cloud-bigquery` SDK and batch JSON loading.

### Runtime Use

BigQuery acts as the warehouse for **historical and regional intelligence** such as long-term rainfall normals, soil baselines, crop-yield statistics, and agronomic catalogs.

For farmer-facing requests, the validated regional context is loaded by the application through `maharashtra_agri_context.py` and served by FastAPI on Cloud Run. This avoids querying BigQuery for every interaction while keeping the operational recommendation flow fast and independent of repeated warehouse calls.

---

## Google Cloud & Deployment

| Service | Usage |
|---|---|
| **Cloud Run** | Hosts the FastAPI backend and web application |
| **Vertex AI / Gemini** | Field action plan, Soil Health Card extraction, crop-image analysis |
| **Google Earth Engine** | Sentinel-2 processing and vegetation/moisture indices |
| **Cloud Speech-to-Text** | Converts farmer voice questions into text |
| **Cloud Text-to-Speech** | Generates multilingual audio advisories |
| **Cloud Storage** | Stores uploaded Soil Health Cards and crop images |
| **BigQuery** | Warehouses validated regional and historical agricultural datasets used by the application |
| **Cloud Build** | Builds application container images |
| **Artifact Registry** | Stores deployment container images |

```text
                    +----------------------+
                    |   Farmer Web / PWA   |
                    +----------+-----------+
                               |
                             HTTPS
                               |
                               v
                    +----------------------+
                    |   Google Cloud Run   |
                    |   React + FastAPI    |
                    +----+---------+-------+
                         |         |
              +----------+         +-----------+
              |                                |
              v                                v
+---------------------------+       +-----------------------+
| Vertex AI / Gemini        |       | Cloud Storage         |
| Action plan               |       | Soil Health Cards     |
| Vision extraction         |       | Crop Images           |
| Crop-image analysis       |       +-----------------------+
+-------------+-------------+
              |
      +-------+----------------------+
      |                              |
      v                              v
+---------------------------+  +-----------------------------+
| Speech-to-Text / TTS      |  | Google Earth Engine         |
| Voice interaction         |  | Sentinel-2 field analysis   |
+---------------------------+  +-----------------------------+

Cloud Run also connects to external weather, geocoding,
postal, and agronomic data sources.
```

---

## Main API Endpoints

Detailed request and response schemas are available through FastAPI OpenAPI / Swagger.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/farms` | Create a farm profile |
| `GET /api/v1/farms/{id}/evidence` | Get weather and supporting farm evidence |
| `GET /api/v1/farms/{id}/satellite/map` | Generate a satellite index map |
| `POST /api/v1/farms/{id}/soil/extract` | Extract Soil Health Card information |
| `GET /api/v1/farms/{id}/crops/recommendations` | Generate crop recommendations |
| `POST /api/v1/farms/{id}/advisories` | Generate the field action plan |
| `POST /api/v1/farms/{id}/diagnoses` | Analyze a crop image |
| `POST /api/v1/farms/{id}/chat` | Krishi Mitra follow-up conversation |

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React, Vite, TypeScript, responsive web UI, interactive map/SVG boundary plotting, browser voice recording/playback |
| **Backend** | Python, FastAPI, Pydantic, REST APIs, agronomic decision rules, in-memory TTL session handling |
| **AI & Geospatial** | Vertex AI / Gemini, Google Earth Engine, Copernicus Sentinel-2, Google Cloud Speech-to-Text, Google Cloud Text-to-Speech |
| **Cloud** | Cloud Run, Cloud Storage, BigQuery, Cloud Build, Artifact Registry |
