from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from .settings import get_settings


ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}


class MediaStore:
    def __init__(self):
        self.settings = get_settings()

    def save(self, content: bytes, content_type: str) -> tuple[str, str]:
        extension = ALLOWED_CONTENT_TYPES.get(content_type)
        if not extension:
            raise ValueError("Unsupported media type")
        object_name = f"uploads/{uuid4().hex}{extension}"
        if self.settings.media_provider == "gcs":
            from google.cloud import storage

            bucket = storage.Client(project=self.settings.google_cloud_project).bucket(self.settings.media_bucket)
            bucket.blob(object_name).upload_from_string(content, content_type=content_type)
            return f"gs://{self.settings.media_bucket}/{object_name}", object_name
        path = Path(self.settings.media_directory) / object_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path), object_name

    def read(self, storage_uri: str) -> bytes:
        if storage_uri.startswith("gs://"):
            from google.cloud import storage

            bucket_name, object_name = storage_uri.removeprefix("gs://").split("/", 1)
            return storage.Client(project=self.settings.google_cloud_project).bucket(bucket_name).blob(object_name).download_as_bytes()
        path = Path(storage_uri).resolve()
        root = Path(self.settings.media_directory).resolve()
        if root not in path.parents:
            raise ValueError("Invalid local media path")
        return path.read_bytes()


@lru_cache
def get_media_store() -> MediaStore:
    return MediaStore()
