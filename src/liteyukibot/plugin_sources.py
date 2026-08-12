"""Workspace-owned plugin-index sources and cached metadata retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .plugin_store import PluginIndex, PluginStoreError

OFFICIAL_SOURCE_ID = "liteyukibot-v7-plugins"
OFFICIAL_SOURCE_URL = "https://raw.githubusercontent.com/LiteyukiStudio/liteyukibot-v7-plugins/main/index.json"
_MAX_INDEX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PluginSource:
    id: str
    url: str
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.id or self.id != self.id.strip() or any(character.isspace() for character in self.id):
            raise PluginStoreError("plugin source ID must be a non-empty whitespace-free string")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise PluginStoreError("plugin source priority must be an integer")
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise PluginStoreError("plugin source URL must be credential-free HTTPS")

    def document(self) -> dict[str, object]:
        return {"id": self.id, "url": self.url, "priority": self.priority}


OFFICIAL_SOURCE = PluginSource(OFFICIAL_SOURCE_ID, OFFICIAL_SOURCE_URL, priority=0)


class PluginSourceStore:
    """Persist only custom source declarations; the official source is always present."""

    def __init__(self, workspace: str | Path) -> None:
        management = Path(workspace).resolve() / ".liteyuki"
        self.path = management / "plugin-sources.json"
        self.cache_directory = management / "plugins" / "indexes"

    def list(self) -> tuple[PluginSource, ...]:
        custom = self._custom()
        return (OFFICIAL_SOURCE, *sorted(custom.values(), key=lambda item: (item.priority, item.id)))

    def add(self, source: PluginSource) -> None:
        if source.id == OFFICIAL_SOURCE_ID:
            raise PluginStoreError(f"plugin source {OFFICIAL_SOURCE_ID!r} is reserved")
        custom = self._custom()
        custom[source.id] = source
        self._write_sources(custom)

    def remove(self, source_id: str) -> None:
        if source_id == OFFICIAL_SOURCE_ID:
            raise PluginStoreError(f"plugin source {OFFICIAL_SOURCE_ID!r} is reserved")
        custom = self._custom()
        if source_id not in custom:
            raise PluginStoreError(f"plugin source {source_id!r} is not configured")
        del custom[source_id]
        self._write_sources(custom)

    def fetch(self, source_id: str, *, refresh: bool = False) -> PluginIndex:
        source = next((item for item in self.list() if item.id == source_id), None)
        if source is None:
            raise PluginStoreError(f"plugin source {source_id!r} is not configured")
        cache = self.cache_directory / f"{source.id}.json"
        if cache.is_file() and not refresh:
            try:
                return PluginIndex.parse(json.loads(cache.read_text(encoding="utf-8")))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise PluginStoreError(f"cached plugin index {source.id!r} is invalid") from error
        try:
            request = Request(source.url, headers={"User-Agent": "liteyukibot-v7-plugin-index"})
            with urlopen(request, timeout=15) as response:  # noqa: S310 - source URL is validated HTTPS configuration.
                payload = response.read(_MAX_INDEX_BYTES + 1)
        except (OSError, URLError) as error:
            raise PluginStoreError(f"cannot fetch plugin source {source.id!r}: {error}") from error
        if len(payload) > _MAX_INDEX_BYTES:
            size_mib = _MAX_INDEX_BYTES // 1024 // 1024
            raise PluginStoreError(f"plugin source {source.id!r} exceeded the {size_mib} MiB limit")
        try:
            text = payload.decode("utf-8")
            index = PluginIndex.parse(json.loads(text))
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            raise PluginStoreError(f"plugin source {source.id!r} returned an invalid index") from error
        self._write_text(cache, text)
        self._write_text(cache.with_suffix(".sha256"), index.digest + "\n")
        return index

    def cached_digest(self, source_id: str) -> str | None:
        path = self.cache_directory / f"{source_id}.sha256"
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise PluginStoreError(f"cached plugin source digest for {source_id!r} is invalid")
        return value

    def _custom(self) -> dict[str, PluginSource]:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("schema") != 1 or not isinstance(value.get("sources"), list):
                raise ValueError("unexpected source schema")
            sources = {
                source.id: source
                for raw in value["sources"]
                for source in [self._source(raw)]
            }
        except (AttributeError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PluginStoreError("plugin source configuration is invalid") from error
        if len(sources) != len(value["sources"]) or OFFICIAL_SOURCE_ID in sources:
            raise PluginStoreError("plugin source configuration contains duplicate or reserved IDs")
        return sources

    @staticmethod
    def _source(value: object) -> PluginSource:
        if not isinstance(value, dict):
            raise PluginStoreError("plugin source configuration entry must be an object")
        return PluginSource(str(value["id"]), str(value["url"]), value.get("priority", 100))

    def _write_sources(self, sources: dict[str, PluginSource]) -> None:
        document = {
            "schema": 1,
            "sources": [source.document() for source in sorted(sources.values(), key=lambda item: item.id)],
        }
        self._write_text(
            self.path,
            json.dumps(document, indent=2, sort_keys=True) + "\n",
        )

    @staticmethod
    def _write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)


__all__ = [
    "OFFICIAL_SOURCE",
    "OFFICIAL_SOURCE_ID",
    "OFFICIAL_SOURCE_URL",
    "PluginSource",
    "PluginSourceStore",
]
