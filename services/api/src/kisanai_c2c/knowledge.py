"""Static agronomic knowledge: global crop catalog, regenerative practices and regional packs.

Bundled packs live in data/packs/. Packs imported from peer nodes and approved by a local
expert are stored in the document store and take part in lookups through `active_packs`.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from .settings import PROJECT_ROOT

DATA_DIR = PROJECT_ROOT / "data"
UI_LOCALES = ("en", "hi", "mr", "te", "kn")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def crop_catalog() -> dict[str, dict[str, Any]]:
    data = _read(DATA_DIR / "crops" / "global_crop_catalog.json")
    return {crop["id"]: crop for crop in data["crops"]}


@lru_cache
def catalog_sources() -> list[dict[str, str]]:
    return _read(DATA_DIR / "crops" / "global_crop_catalog.json")["sources"]


@lru_cache
def practice_catalog() -> dict[str, dict[str, Any]]:
    data = _read(DATA_DIR / "practices" / "regenerative_practices.json")
    return {item["id"]: item for item in data["practices"]}


@lru_cache
def bundled_packs() -> dict[str, dict[str, Any]]:
    packs: dict[str, dict[str, Any]] = {}
    for path in sorted((DATA_DIR / "packs").glob("*.json")):
        pack = _read(path)
        packs[pack["region"]["subdivision_code"]] = pack
    return packs


@lru_cache
def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for crop_id, crop in crop_catalog().items():
        index[crop_id] = crop_id
        index[crop_id.replace("_", "")] = crop_id
        for alias in crop.get("aliases", []):
            index[_slug(alias)] = crop_id
        for name in crop["names"].values():
            index[_slug(name)] = crop_id
    return index


def _slug(value: str) -> str:
    return "_".join(value.strip().lower().replace("/", " ").replace("(", " ").replace(")", " ").split())


def normalize_crop(value: str | None) -> str:
    """Map a free-text crop name (English, Indian languages, local aliases) to a catalog id."""
    if not value:
        return ""
    slug = _slug(value)
    index = _alias_index()
    if slug in index:
        return index[slug]
    for token in slug.split("_"):
        if token in index:
            return index[token]
    return slug


def crop_name(crop_id: str, locale: str = "en-IN") -> str:
    crop = crop_catalog().get(crop_id)
    if not crop:
        return crop_id.replace("_", " ").title()
    lang = locale.split("-")[0]
    return crop["names"].get(lang) or crop["names"]["en"]


def practice_name(practice_id: str, locale: str = "en-IN") -> str:
    practice = practice_catalog().get(practice_id)
    if not practice:
        return practice_id.replace("-", " ").title()
    lang = locale.split("-")[0]
    return practice["names"].get(lang) or practice["names"]["en"]


def subdivision_code(country_code: str | None, state_code: str | None) -> str | None:
    if not country_code or not state_code:
        return None
    state = state_code.upper()
    if "-" in state:
        return state
    return f"{country_code.upper()}-{state}"


def find_district(pack: dict[str, Any] | None, district: str | None) -> dict[str, Any] | None:
    if not pack or not district:
        return None
    wanted = district.strip().lower().replace(" district", "")
    for item in pack.get("districts", []):
        names = [item["name"], *item.get("aliases", [])]
        if any(name.strip().lower() == wanted for name in names):
            return item
    return None


def _mmdd_to_date(mmdd: str, year: int) -> date:
    month, day = (int(part) for part in mmdd.split("-"))
    if month == 2 and day == 29:
        day = 28
    return date(year, month, day)


def window_dates(window: dict[str, Any], today: date) -> tuple[date, date]:
    """Resolve an MM-DD window to the occurrence that is current or next relative to `today`."""
    for year in (today.year - 1, today.year, today.year + 1):
        start = _mmdd_to_date(window["start"], year)
        end = _mmdd_to_date(window["end"], year)
        if end < start:
            end = _mmdd_to_date(window["end"], year + 1)
        if end >= today:
            return start, end
    start = _mmdd_to_date(window["start"], today.year + 1)
    end = _mmdd_to_date(window["end"], today.year + 1)
    return start, end if end >= start else _mmdd_to_date(window["end"], today.year + 2)


def season_for_month(pack: dict[str, Any] | None, month: int) -> str | None:
    if not pack:
        return None
    for season in pack.get("seasons", []):
        if month in season["months"]:
            return season["id"]
    return None
