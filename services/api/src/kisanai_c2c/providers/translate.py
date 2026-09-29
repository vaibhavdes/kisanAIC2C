"""Google Cloud Translation (v3) for languages that have no hand-written translation.

A node that serves a new country lists its languages in NODE_LANGUAGES; the farmer UI strings,
crop names and practice names are machine-translated once from English and cached in the store,
so no code or file changes are needed to add a language. Placeholders such as {date} are
protected from translation.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from functools import lru_cache
from typing import Any

from ..settings import Settings, get_settings

PLACEHOLDER = re.compile(r"\{[a-z_]+\}%?")  # a trailing % belongs to the number
BATCH = 100
METHOD_VERSION = 2  # bump when placeholder handling changes so cached translations are rebuilt


class TranslationUnavailable(RuntimeError):
    pass


def language_of(locale: str) -> str:
    """BCP-47 tag understood by Cloud Translation: keep the region only for Chinese and Portuguese variants."""
    lang, _, region = locale.partition("-")
    if lang in {"zh", "pt"} and region:
        return f"{lang}-{region}"
    return lang


class TranslationProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _client(self):
        if not self.settings.google_cloud_project:
            raise TranslationUnavailable("GOOGLE_CLOUD_PROJECT is required for Cloud Translation")
        from google.cloud import translate_v3

        return translate_v3.TranslationServiceClient()

    def translate(self, texts: list[str], locale: str) -> list[str]:
        if not texts:
            return []
        client = self._client()
        parent = f"projects/{self.settings.google_cloud_project}/locations/global"
        out: list[str] = []
        for start in range(0, len(texts), BATCH):
            chunk = [PLACEHOLDER.sub(lambda m: f'<span translate="no">{m.group(0)}</span>', html.escape(text, quote=False))
                     for text in texts[start:start + BATCH]]
            try:
                response = client.translate_text(request={
                    "parent": parent, "contents": chunk, "mime_type": "text/html",
                    "source_language_code": "en", "target_language_code": language_of(locale),
                })
            except Exception as exc:  # noqa: BLE001
                raise TranslationUnavailable(f"Cloud Translation failed: {exc}") from exc
            for item in response.translations:
                text = re.sub(r'<span translate="no">\s*(\{[a-z_]+\}%?)\s*</span>', r"\1", item.translated_text)
                text = re.sub(r"(\{[a-z_]+\}%?)\s+([.,;:!?)])", r"\1\2", text)
                text = re.sub(r"\(\s+", "(", text)
                out.append(html.unescape(text).strip())
        return out

    def native_name(self, locale: str) -> str:
        """The language's name in itself (e.g. "Português"), for the language picker."""
        names = _language_names(self.settings.google_cloud_project, language_of(locale).split("-")[0])
        name = names.get(language_of(locale)) or names.get(locale.split("-")[0])
        return name[:1].upper() + name[1:] if name else locale

    def language_name(self, locale: str) -> str:
        names = _language_names(self.settings.google_cloud_project, "en")
        return names.get(language_of(locale)) or names.get(locale.split("-")[0]) or locale


@lru_cache
def _language_names(project: str | None, display: str) -> dict[str, str]:
    if not project:
        return {}
    try:
        from google.cloud import translate_v3

        client = translate_v3.TranslationServiceClient()
        response = client.get_supported_languages(parent=f"projects/{project}/locations/global", display_language_code=display)
        return {item.language_code: item.display_name for item in response.languages}
    except Exception:  # noqa: BLE001 - the tag itself is still understood by Gemini
        return {}


def placeholders_match(source: str, translated: str) -> bool:
    return sorted(re.findall(r"\{[a-z_]+\}", source)) == sorted(re.findall(r"\{[a-z_]+\}", translated))


def content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps([METHOD_VERSION, value], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
