# KISANAI backend (`services/api`)

FastAPI service behind the KISANAI app. Routes stay thin; the decisions live in plain Python modules that are easy to test:

- `weather_ops.py` — field-work advice from the forecast (thresholds in `THRESHOLDS`)
- `domain.py` — crop scoring and reasons
- `fertilizer.py` — fertilizer plan from a soil test
- `satellite_explain.py` — plain-language satellite summary

External services sit in `providers/` (Open-Meteo and IMD weather, Earth Engine, Gemini on Vertex AI, Google Speech).

## Tests

```bash
PYTHONPATH=src python3 -m pytest tests
```

Most tests run offline. The PIN-code lookup test calls the public postal API.
