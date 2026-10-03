"""One way out for calls to public data services (AGMARKNET, CEDA, data.gov.in, OpenStreetMap):

- responses are cached in memory and, when a document store is given, in the store (collection
  `http_cache`), so every Cloud Run instance and restart reuses them instead of asking again;
- each host gets a minimum gap between requests (AGMARKNET and Nominatim ask for about one a second);
- after a 429/5xx the host is paused (Retry-After when sent, otherwise growing back-off) and the last
  cached answer is served, even if it is past its freshness, rather than failing the farmer's screen.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import requests

USER_AGENT = "KISANAI-C2C-Agricultural-Intelligence/1.0 (+https://kisanai-c2c-313370978552.asia-south1.run.app)"
MIN_GAP = {"api.agmarknet.gov.in": 1.0, "nominatim.openstreetmap.org": 1.1, "api.ceda.ashoka.edu.in": 0.5, "api.data.gov.in": 0.5}
MEMORY_LIMIT = 2000

_lock = threading.Lock()
_next_slot: dict[str, float] = {}
_paused_until: dict[str, float] = {}
_failures: dict[str, int] = {}
_memory: dict[str, tuple[float, Any]] = {}
stats = {"memory_hits": 0, "store_hits": 0, "network": 0, "stale_served": 0, "throttled": 0}


class Unavailable(RuntimeError):
    pass


def _key(method: str, url: str, params: dict | None, body: dict | None) -> str:
    raw = json.dumps([method, url, params or {}, body or {}], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def _wait_turn(host: str, max_wait: float) -> None:
    """Reserve the next request slot for this host; raise if the host is paused or the wait is too long."""
    with _lock:
        now = time.monotonic()
        if _paused_until.get(host, 0) > now:
            stats["throttled"] += 1
            raise Unavailable(f"{host} asked us to slow down; retry in {int(_paused_until[host] - now)} s")
        slot = max(now, _next_slot.get(host, 0))
        if slot - now > max_wait:
            stats["throttled"] += 1
            raise Unavailable(f"{host} request queue is full")
        _next_slot[host] = slot + MIN_GAP.get(host, 0.2)
    if slot > now:
        time.sleep(slot - now)


def _pause(host: str, retry_after: str | None) -> None:
    with _lock:
        _failures[host] = _failures.get(host, 0) + 1
        delay = float(retry_after) if retry_after and retry_after.isdigit() else min(600, 15 * 2 ** (_failures[host] - 1))
        _paused_until[host] = time.monotonic() + delay


def fetch_json(url: str, *, params: dict | None = None, body: dict | None = None, headers: dict | None = None,
               ttl: float = 86400, store: Any = None, timeout: float = 20, max_wait: float = 8) -> Any:
    """GET (or POST with `body`) returning parsed JSON, cached for `ttl` seconds."""
    method = "POST" if body is not None else "GET"
    key = _key(method, url, params, body)
    now = time.time()
    cached = _memory.get(key)
    if cached and now - cached[0] < ttl:
        stats["memory_hits"] += 1
        return cached[1]
    stored = None
    if store is not None:
        try:
            stored = store.get("http_cache", key)
        except Exception:
            stored = None
        if stored and now - stored["at"] < ttl:
            stats["store_hits"] += 1
            _remember(key, stored["at"], stored["value"])
            return stored["value"]
    stale = cached[1] if cached else (stored or {}).get("value")
    host = urlparse(url).netloc
    try:
        _wait_turn(host, max_wait)
        stats["network"] += 1
        response = requests.request(method, url, params=params, json=body, timeout=timeout,
                                    headers={"User-Agent": USER_AGENT, **(headers or {})})
        if response.status_code == 429 or response.status_code >= 500:
            _pause(host, response.headers.get("Retry-After"))
            raise Unavailable(f"{host} answered {response.status_code}")
        response.raise_for_status()
        value = response.json()
        _failures.pop(host, None)
    except Exception as exc:
        if stale is not None:
            stats["stale_served"] += 1
            return stale
        raise Unavailable(str(exc)) from exc
    _remember(key, now, value)
    if store is not None:
        try:
            store.put("http_cache", key, {"id": key, "at": now, "url": url, "value": value,
                                          "created_at": datetime.now(UTC).isoformat()})
        except Exception:
            pass  # a value too large or a store hiccup only costs a refetch later
    return value


def _remember(key: str, at: float, value: Any) -> None:
    with _lock:
        if len(_memory) >= MEMORY_LIMIT:
            for old in sorted(_memory, key=lambda k: _memory[k][0])[: MEMORY_LIMIT // 10]:
                _memory.pop(old, None)
        _memory[key] = (at, value)
