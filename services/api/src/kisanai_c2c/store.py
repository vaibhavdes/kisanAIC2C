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
        supported = {"node_id", "owner_subject"}
        sql = "SELECT body FROM documents WHERE collection=?"
        params: list[Any] = [collection]
        for key in supported:
            if key in filters:
                sql += f" AND {key}=?"
                params.append(filters[key])
        sql += " ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?"
        params.append(min(max(limit, 1), 500))
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        values = [json.loads(row["body"]) for row in rows]
        for key, expected in filters.items():
            if key not in supported:
                values = [value for value in values if value.get(key) == expected]
        return values

    def delete(self, collection: str, document_id: str) -> bool:
        with self.lock, self._connect() as connection:
            result = connection.execute(
                "DELETE FROM documents WHERE collection=? AND id=?", (collection, document_id)
            )
        return result.rowcount > 0


class FirestoreDocumentStore:
    def __init__(self, settings: Settings):
        from google.cloud import firestore

        self.client = firestore.Client(project=settings.google_cloud_project, database=settings.firestore_database)

    def put(self, collection: str, document_id: str, value: dict[str, Any]) -> dict[str, Any]:
        self.client.collection(collection).document(document_id).set(value)
        return value

    def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        snapshot = self.client.collection(collection).document(document_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list(self, collection: str, *, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self.client.collection(collection)
        for key, value in (filters or {}).items():
            query = query.where(filter=FieldFilter(key, "==", value))
        return [snapshot.to_dict() for snapshot in query.limit(min(max(limit, 1), 500)).stream()]

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
