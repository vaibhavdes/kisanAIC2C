from __future__ import annotations

from typing import Any

import pytest

from kisanai_c2c.models import Actor, ClimateMonth, Farm, LandProfile, Location, Role, SoilEstimate
from kisanai_c2c.service import AppService
from kisanai_c2c.settings import Settings


class MemoryStore:
    def __init__(self):
        self.data: dict[str, dict[str, dict[str, Any]]] = {}

    def put(self, collection: str, document_id: str, value: dict[str, Any]) -> dict[str, Any]:
        self.data.setdefault(collection, {})[document_id] = value
        return value

    def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        return self.data.get(collection, {}).get(document_id)

    def list(self, collection: str, *, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        items = list(self.data.get(collection, {}).values())
        for key, value in (filters or {}).items():
            items = [item for item in items if item.get(key) == value]
        items.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or item.get("fetched_at") or ""), reverse=True)
        return items[:limit]

    def delete(self, collection: str, document_id: str) -> bool:
        return self.data.get(collection, {}).pop(document_id, None) is not None


class MemoryMediaStore:
    def __init__(self):
        self.media: dict[str, bytes] = {}

    def save(self, content: bytes, content_type: str) -> tuple[str, str]:
        uri = f"memory://{len(self.media)}"
        self.media[uri] = content
        return uri, uri

    def read(self, storage_uri: str) -> bytes:
        return self.media[storage_uri]


def make_settings(**overrides) -> Settings:
    base = dict(_env_file=None, node_id="node-mh", node_label="Test MH node", node_subdivisions="IN-MH,IN-UP",
                earth_engine_enabled=False, imd_enabled=False, open_meteo_enabled=False, ai_enabled=False,
                google_cloud_project=None, expert_access_token=None, peer_nodes="")
    base.update(overrides)
    return Settings(**base)


# Monthly normals resembling semi-arid central India (Vidarbha): hot pre-monsoon, monsoon Jun-Sep, mild dry winter.
VIDARBHA = [
    (1, 12.5, 29.5, 12, 110), (2, 15.0, 32.5, 8, 125), (3, 19.5, 37.0, 12, 170), (4, 23.5, 40.5, 8, 200),
    (5, 27.0, 42.0, 12, 220), (6, 25.5, 36.0, 170, 170), (7, 23.5, 30.5, 280, 125), (8, 23.0, 30.0, 250, 115),
    (9, 22.5, 31.5, 170, 120), (10, 19.5, 32.0, 55, 125), (11, 15.0, 30.5, 15, 105), (12, 12.0, 29.0, 8, 95),
]
# Southern Brazil (Parana plateau): mild winter, rain all year.
PARANA = [
    (1, 19.0, 29.0, 190, 140), (2, 19.0, 29.0, 170, 120), (3, 18.0, 28.0, 130, 115), (4, 15.0, 25.5, 120, 85),
    (5, 12.0, 22.0, 140, 65), (6, 10.0, 20.5, 110, 55), (7, 9.5, 20.5, 95, 60), (8, 10.5, 23.0, 80, 80),
    (9, 12.5, 24.0, 140, 95), (10, 15.0, 26.5, 190, 120), (11, 16.5, 27.5, 170, 130), (12, 18.0, 28.5, 190, 140),
]


def land_profile(farm: Farm, rows, soil: SoilEstimate | None = None) -> LandProfile:
    return LandProfile(
        farm_id=farm.id, node_id=farm.node_id, latitude=farm.location.latitude, longitude=farm.location.longitude,
        climate=[ClimateMonth(month=m, tmin_c=tmin, tmax_c=tmax, tmean_c=(tmin + tmax) / 2, precip_mm=pr, pet_mm=pet) for m, tmin, tmax, pr, pet in rows],
        climate_source="test", climate_period="test", soil=soil,
    )


def make_farm(**overrides) -> Farm:
    base = dict(name="Test farm", country_code="IN", state_code="MH", state_name="Maharashtra", district="Yavatmal", area_value=2,
                area_ha=0.81, location=Location(latitude=20.43, longitude=78.51), water_access="rainfed", soil_type="black",
                previous_crop="soybean", owner_subject="dev-farmer-000001", node_id="node-mh")
    base.update(overrides)
    return Farm(**base)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def service(settings) -> AppService:
    return AppService(store=MemoryStore(), media_store=MemoryMediaStore(), settings=settings)


@pytest.fixture
def farmer() -> Actor:
    return Actor(subject="dev-farmer-000001", node_id="node-mh", roles={Role.farmer})


@pytest.fixture
def other_farmer() -> Actor:
    return Actor(subject="dev-farmer-000002", node_id="node-mh", roles={Role.farmer})


@pytest.fixture
def expert() -> Actor:
    return Actor(subject="dev-expert-000001", node_id="node-mh", roles={Role.farmer, Role.expert})
