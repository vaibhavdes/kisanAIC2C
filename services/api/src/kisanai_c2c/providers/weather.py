from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from ..models import EvidenceSnapshot, EvidenceValue, Farm
from ..settings import Settings, get_settings


class WeatherUnavailable(RuntimeError):
    pass


class WeatherProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def fetch(self, farm: Farm) -> list[EvidenceSnapshot]:
        snapshots: list[EvidenceSnapshot] = []
        imd_error: str | None = None

        if self.settings.imd_enabled:
            attempts = self.settings.imd_retry_attempts + 1
            for attempt in range(attempts):
                try:
                    snapshots.extend(self._fetch_imd(farm))
                    break
                except Exception as exc:
                    if attempt < attempts - 1:
                        time.sleep(1)
                    else:
                        imd_error = str(exc)

        # Ensure numerical 7-day precipitation, wind, humidity, and temperature are available via Open-Meteo
        has_numerical_forecast = any(
            item.kind == "weather_forecast" and any(str(v.name).startswith("rainfall_") for v in item.values)
            for item in snapshots
        )
        if not has_numerical_forecast and self.settings.open_meteo_enabled:
            try:
                snapshots.append(self._fetch_open_meteo(farm, fallback_from=imd_error))
            except Exception as om_exc:
                if not snapshots:
                    raise WeatherUnavailable(f"Open-Meteo failed: {om_exc}")

        if imd_error and not any(item.provider == "imd" for item in snapshots):
            snapshots.append(
                EvidenceSnapshot(
                    farm_id=farm.id,
                    node_id=farm.node_id,
                    provider="imd",
                    kind="official_warning_coverage",
                    mode="missing",
                    spatial_scope=f"{farm.state_code}/{farm.district}",
                    quality_flags=["provider_unavailable", imd_error[:200]],
                    source_reference="https://api.imd.gov.in/public/api_reference.html",
                )
            )

        if not snapshots:
            raise WeatherUnavailable("No weather provider is enabled or available")
        return snapshots

    _jwt_cache: dict[str, tuple[str, float]] = {}

    def _get_jwt_token(self) -> str:
        """Fetch or retrieve cached JWT token according to IMD documentation."""
        if self.settings.imd_jwt_token:
            return self.settings.imd_jwt_token

        email = self.settings.imd_email
        password = self.settings.imd_password
        if not email or not password:
            raise WeatherUnavailable("IMD JWT authentication requires IMD_JWT_TOKEN or (IMD_EMAIL and IMD_PASSWORD)")

        now = time.time()
        cached = self._jwt_cache.get(email)
        if cached and cached[1] > now + 60:
            return cached[0]

        token_url = f"{self.settings.imd_base_url.rstrip('/')}/api/oauth/token.php"
        try:
            resp = requests.post(token_url, json={"email": email, "password": password}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            if not token:
                raise WeatherUnavailable(f"IMD token endpoint did not return access_token: {resp.text[:100]}")
            expires_in = float(data.get("expires_in", 3600))
            self._jwt_cache[email] = (token, now + expires_in)
            return token
        except Exception as exc:
            raise WeatherUnavailable(f"Failed to generate IMD JWT token: {exc}")

    def _auth(self, params: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
        headers: dict[str, str] = {"Accept": "application/json"}
        auth_mode = self.settings.imd_auth_mode

        if auth_mode == "jwt":
            if not self.settings.imd_api_key:
                raise WeatherUnavailable("IMD_API_KEY is required for X-API-KEY header")
            headers["X-API-KEY"] = self.settings.imd_api_key
            token = self._get_jwt_token()
            headers["Authorization"] = f"Bearer {token}"
            return headers, params

        if auth_mode == "header":
            if not self.settings.imd_api_key or not self.settings.imd_auth_header_name:
                raise WeatherUnavailable("IMD header authentication is incomplete")
            prefix = f"{self.settings.imd_auth_scheme} " if self.settings.imd_auth_scheme else ""
            headers[self.settings.imd_auth_header_name] = f"{prefix}{self.settings.imd_api_key}"
        elif auth_mode == "query":
            if not self.settings.imd_api_key or not self.settings.imd_auth_query_name:
                raise WeatherUnavailable("IMD query authentication is incomplete")
            params[self.settings.imd_auth_query_name] = self.settings.imd_api_key

        return headers, params

    def _imd_json(self, path: str) -> Any:
        headers, params = self._auth({})
        response = requests.get(f"{self.settings.imd_base_url.rstrip('/')}{path}", params=params, headers=headers, timeout=12)
        response.raise_for_status()

        text = response.text.lstrip()
        if text.lower().startswith("<!doctype") or text.lower().startswith("<html"):
            raise WeatherUnavailable("IMD returned an HTML page (possibly login required) instead of JSON")

        if "json" not in response.headers.get("content-type", "").lower():
            raise WeatherUnavailable("IMD returned a non-JSON response")
        return response.json()

    def _fetch_imd(self, farm: Farm) -> list[EvidenceSnapshot]:
        result = []
        try:
            result.extend(self._fetch_imd_forecast(farm))
        except Exception:
            pass

        try:
            result.extend(self._fetch_imd_warning(farm))
        except Exception:
            pass
            
        try:
            result.extend(self._fetch_imd_nowcast(farm))
        except Exception:
            pass

        if not result:
            raise WeatherUnavailable("Failed to fetch any data from IMD endpoints")
        return result

    def _fetch_imd_forecast(self, farm: Farm) -> list[EvidenceSnapshot]:
        state = farm.state_name.strip().upper()
        district = farm.district.strip().upper()
        forecast_rows = self._unwrap(self._imd_json("/api/v1/state_district_rainfall_forecast"))
        matches = [row for row in forecast_rows if str(row.get("District", "")).strip().upper() == district]
        state_matches = [row for row in matches if state in str(row.get("State", "")).strip().upper() or str(row.get("State", "")).strip().upper() in state]
        row = (state_matches or matches or [None])[0]
        if row is None:
            raise WeatherUnavailable("IMD district mapping was not found")

        values: list[EvidenceValue] = []
        for day in range(1, 6):
            values.append(EvidenceValue(name=f"day_{day}_distribution", value=row.get(f"day{day}_distribution")))
            values.append(EvidenceValue(name=f"day_{day}_coverage", value=row.get(f"day{day}_distribution_percentage")))
        issued = self._parse_date(row.get("date_obs"))
        
        return [
            EvidenceSnapshot(
                farm_id=farm.id,
                node_id=farm.node_id,
                provider="imd",
                kind="weather_forecast",
                mode="live",
                issued_at=issued,
                valid_until=issued + timedelta(days=5) if issued else None,
                spatial_scope=f"district:{row.get('Obj_id') or district}",
                values=values,
                source_reference="https://api.imd.gov.in/api/v1/state_district_rainfall_forecast",
            )
        ]

    def _fetch_imd_warning(self, farm: Farm) -> list[EvidenceSnapshot]:
        district = farm.district.strip().upper()
        warning_rows = self._unwrap(self._imd_json("/api/v1/districtwarning"))
        warning = next((item for item in warning_rows if str(item.get("District", "")).strip().upper() == district), None)
        if warning:
            warning_issued = self._parse_date(warning.get("Date"))
            warning_values = []
            for day in range(1, 6):
                warning_values.append(EvidenceValue(name=f"day_{day}_warning_code", value=warning.get(f"Day_{day}")))
                warning_values.append(EvidenceValue(name=f"day_{day}_warning_color_code", value=warning.get(f"Day{day}_Color")))
            return [
                EvidenceSnapshot(
                    farm_id=farm.id,
                    node_id=farm.node_id,
                    provider="imd",
                    kind="official_warning",
                    mode="live",
                    issued_at=warning_issued,
                    valid_until=warning_issued + timedelta(days=5) if warning_issued else None,
                    spatial_scope=f"district:{warning.get('Obj_id') or district}",
                    values=warning_values,
                    source_reference="https://api.imd.gov.in/api/v1/districtwarning",
                )
            ]
        return []

    def _fetch_imd_nowcast(self, farm: Farm) -> list[EvidenceSnapshot]:
        district = farm.district.strip().upper()
        nowcast_rows = self._unwrap(self._imd_json("/api/v1/districtnowcast"))
        nowcast = next((item for item in nowcast_rows if str(item.get("District", "")).strip().upper() == district), None)
        if nowcast:
            issued = self._parse_date(nowcast.get("date_obs"))
            values = [
                EvidenceValue(name="nowcast_warning", value=nowcast.get("Warning")),
                EvidenceValue(name="nowcast_color_code", value=nowcast.get("Color")),
            ]
            return [
                EvidenceSnapshot(
                    farm_id=farm.id,
                    node_id=farm.node_id,
                    provider="imd",
                    kind="weather_nowcast",
                    mode="live",
                    issued_at=issued,
                    valid_until=issued + timedelta(hours=3) if issued else None,
                    spatial_scope=f"district:{nowcast.get('Obj_id') or district}",
                    values=values,
                    source_reference="https://api.imd.gov.in/api/v1/districtnowcast",
                )
            ]
        return []

    def _fetch_open_meteo(self, farm: Farm, fallback_from: str | None = None) -> EvidenceSnapshot:
        params = {
            "latitude": farm.location.latitude,
            "longitude": farm.location.longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
            "daily": "precipitation_sum,precipitation_probability_max,temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration",
            "forecast_days": 7,
            "timezone": "auto",
        }
        response = requests.get(self.settings.open_meteo_base_url, params=params, timeout=12)
        response.raise_for_status()
        data = response.json()
        daily = data.get("daily") or {}
        dates = daily.get("time") or []
        if not dates:
            raise WeatherUnavailable("Open-Meteo returned no daily forecast")
        
        values: list[EvidenceValue] = []
        for index, value in enumerate(daily.get("precipitation_sum") or []):
            values.append(EvidenceValue(name=f"rainfall_{dates[index]}", value=value, unit="mm/day"))
        for index, value in enumerate(daily.get("precipitation_probability_max") or []):
            values.append(EvidenceValue(name=f"rain_probability_{dates[index]}", value=value, unit="percent"))
        current = data.get("current") or {}
        values.extend(
            [
                EvidenceValue(name="current_temperature", value=current.get("temperature_2m"), unit="C"),
                EvidenceValue(name="current_humidity", value=current.get("relative_humidity_2m"), unit="percent"),
                EvidenceValue(name="current_rainfall", value=current.get("precipitation"), unit="mm"),
                EvidenceValue(name="current_wind_speed", value=current.get("wind_speed_10m"), unit="km/h"),
            ]
        )
        now = datetime.now(UTC)
        flags = ["forecast_fallback_not_official_warning"]
        if fallback_from:
            flags.append(f"imd_unavailable:{fallback_from[:120]}")
            
        return EvidenceSnapshot(
            farm_id=farm.id,
            node_id=farm.node_id,
            provider="open_meteo",
            kind="weather_forecast",
            mode="live",
            issued_at=now,
            valid_until=now + timedelta(hours=3),
            spatial_scope=f"point:{farm.location.latitude:.4f},{farm.location.longitude:.4f}",
            values=values,
            quality_flags=flags,
            source_reference="https://open-meteo.com/",
        )

    def _unwrap(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return [item for item in data["data"] if isinstance(item, dict)]
        raise WeatherUnavailable("Provider response is not a row list")

    def _parse_date(self, value: Any) -> datetime | None:
        if not value:
            return None
        for pattern in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(str(value).strip(), pattern).replace(tzinfo=UTC)
            except ValueError:
                continue
        return None
