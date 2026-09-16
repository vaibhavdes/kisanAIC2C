# KISANAI C2C Backend API (`services/api`)

Production-ready FastAPI modular monolith powering the KISANAI C2C platform. Implemented with clean architecture: thin HTTP routes, decoupled domain policies, and dependency-injected providers.

## Architecture

- **Domain Policies (`domain.py`)**: Pure deterministic rules with zero HTTP or SDK calls. Evaluates crop suitability, agro-climatic boundaries (Kharif, Rabi, Summer), rotation rules, vernacular aliases, and operational forecast indicators.
- **Provider Adapters (`providers/`)**:
  - `satellite.py`: Google Earth Engine Sentinel-2 MSI Level-2A surface reflectance indices (NDVI, NDMI, NDWI), quantile zone stratification, biophysical narrative generation, and server-side PNG image streaming (`satellite_image_bytes()`).
  - `weather.py`: Primary India Meteorological Department (IMD) adapter (nowcast, warnings, rainfall forecast) with automatic fallback to Open-Meteo.
  - `gemini.py`: Dual-tier Google AI routing — attempts Google AI Studio free tier first to preserve credits, automatically failing over to Google Cloud Vertex AI on HTTP 429 quota exhaustion.
  - `voice.py`: Speech-to-text and text-to-speech audio synthesis.
- **Storage Layer (`store.py`, `service.py`)**: Pluggable `DocumentStore` supporting SQLite for development/testing and Cloud Firestore for production.
- **Static Mounting (`main.py`)**: Mounts built React frontend (`static/`) on root `/` with SPA catch-all routing for single-origin deployment.

## Test Suite

All unit and integration tests run 100% offline without external network dependencies:

```bash
# Run test suite
python3 -m pytest services/api/tests

# Run specific test file
python3 -m pytest services/api/tests/test_domain.py
```
