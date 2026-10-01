from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from .settings import Settings, get_settings


class DocumentStore(Protocol):
    def put(self, collection: str, document_id: str, value: dict[str, Any]) -> dict[str, Any]: ...
    def get(self, collection: str, document_id: str) -> dict[str, Any] | None: ...
    def list(self, collection: str, *, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]: ...
    def delete(self, collection: str, document_id: str) -> bool: ...


class SQLiteDocumentStore:
    def __init__(self, path: str):
        self.path = path
        self.lock = RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    collection TEXT NOT NULL,
                    id TEXT NOT NULL,
                    node_id TEXT,
                    owner_subject TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    body TEXT NOT NULL,
                    PRIMARY KEY (collection, id)
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_scope ON documents(collection, node_id, owner_subject)")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def put(self, collection: str, document_id: str, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        with self.lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents(collection,id,node_id,owner_subject,created_at,updated_at,body)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(collection,id) DO UPDATE SET
                  node_id=excluded.node_id, owner_subject=excluded.owner_subject,
                  updated_at=excluded.updated_at, body=excluded.body
                """,
                (
                    collection,
                    document_id,
                    value.get("node_id"),
                    value.get("owner_subject"),
                    value.get("created_at"),
                    value.get("updated_at") or value.get("created_at"),
                    encoded,
                ),
            )
        return value

    def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT body FROM documents WHERE collection=? AND id=?", (collection, document_id)
            ).fetchone()
        return json.loads(row["body"]) if row else None

    def list(self, collection: str, *, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        filters = filters or {}
        columns = {"node_id", "owner_subject"}
        sql = "SELECT body FROM documents WHERE collection=?"
        params: list[Any] = [collection]
        # Every filter is applied in SQL, before LIMIT; filtering afterwards drops matching rows.
        for key, expected in filters.items():
            if key in columns:
                sql += f" AND {key}=?"
            elif key.isidentifier():
                sql += f" AND json_extract(body, '$.{key}')=?"
            else:
                raise ValueError(f"Unsupported filter key: {key}")
            params.append(expected)
        sql += " ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?"
        params.append(min(max(limit, 1), 500))
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def delete(self, collection: str, document_id: str) -> bool:
        with self.lock, self._connect() as connection:
            result = connection.execute(
                "DELETE FROM documents WHERE collection=? AND id=?", (collection, document_id)
            )
        return result.rowcount > 0


_NESTED = "nested_list"  # Firestore reserves names wrapped in double underscores


def _to_firestore(value: Any) -> Any:
    """Firestore rejects arrays inside arrays (e.g. boundary [[lat, lon], ...]); wrap inner lists."""
    if isinstance(value, dict):
        return {key: _to_firestore(item) for key, item in value.items()}
    if isinstance(value, list):
        return [{_NESTED: _to_firestore(item)} if isinstance(item, list) else _to_firestore(item) for item in value]
    return value


def _from_firestore(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {_NESTED}:
            return _from_firestore(value[_NESTED])
        return {key: _from_firestore(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_firestore(item) for item in value]
    return value


class FirestoreDocumentStore:
    def __init__(self, settings: Settings):
        from google.cloud import firestore

        self.client = firestore.Client(project=settings.google_cloud_project, database=settings.firestore_database)

    def put(self, collection: str, document_id: str, value: dict[str, Any]) -> dict[str, Any]:
        self.client.collection(collection).document(document_id).set(_to_firestore(value))
        return value

    def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        snapshot = self.client.collection(collection).document(document_id).get()
        return _from_firestore(snapshot.to_dict()) if snapshot.exists else None

    def list(self, collection: str, *, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self.client.collection(collection)
        for key, value in (filters or {}).items():
            query = query.where(filter=FieldFilter(key, "==", value))
        # Equality filters only, so no composite index is needed; newest-first ordering (as in
        # SQLite) is applied here. Collections per farm are small, so 500 rows is a safe ceiling.
        rows = [_from_firestore(snapshot.to_dict()) for snapshot in query.limit(500).stream()]
        rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or row.get("fetched_at") or ""), reverse=True)
        return rows[: min(max(limit, 1), 500)]

    def delete(self, collection: str, document_id: str) -> bool:
        reference = self.client.collection(collection).document(document_id)
        existed = reference.get().exists
        if existed:
            reference.delete()
        return existed


@lru_cache
def get_store() -> DocumentStore:
    settings = get_settings()
    if settings.store_provider == "firestore":
        return FirestoreDocumentStore(settings)
    return SQLiteDocumentStore(settings.sqlite_path)
