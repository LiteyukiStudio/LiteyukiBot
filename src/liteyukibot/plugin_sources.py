"""Workspace-owned plugin-index sources and cached metadata retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

from .plugin_store import PluginBundle, PluginIndex, PluginStoreError, _https_url, _identifier, _open_public_url

OFFICIAL_SOURCE_ID = "liteyukibot-v7-plugins"
OFFICIAL_SOURCE_URL = "https://raw.githubusercontent.com/LiteyukiStudio/liteyukibot-v7-plugins/main/index.json"
_MAX_INDEX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PluginSource:
    """Represent the plugin source contract."""
    id: str
    url: str
    priority: int = 100

    def __post_init__(self) -> None:
        """Validate and normalize the plugin source after initialization.

        Returns:
            None.
        """
        normalized_id = _identifier(self.id, "plugin source ID")
        object.__setattr__(self, "id", normalized_id)
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise PluginStoreError("plugin source priority must be an integer")
        _https_url(self.url, "plugin source URL")

    def document(self) -> dict[str, object]:
        """Return the serialized document for the plugin source operation.

        Returns:
            The `dict[str, object]` result produced by the operation.
        """
        return {"id": self.id, "url": self.url, "priority": self.priority}


@dataclass(frozen=True, slots=True)
class PluginSearchResult:
    """One discoverable bundle paired with the source that published it."""

    source: PluginSource
    bundle: PluginBundle


OFFICIAL_SOURCE = PluginSource(OFFICIAL_SOURCE_ID, OFFICIAL_SOURCE_URL, priority=0)


class PluginSourceStore:
    """Persist only custom source declarations; the official source is always present."""

    def __init__(self, workspace: str | Path) -> None:
        """Initialize the plugin source store.

        Args:
            workspace: The workspace value used by the operation.

        Returns:
            None.
        """
        management = Path(workspace).resolve() / ".liteyuki"
        self.path = management / "plugin-sources.json"
        self.cache_directory = management / "plugins" / "indexes"

    def list(self) -> tuple[PluginSource, ...]:
        """List the plugin source store operation.

        Returns:
            The `tuple[PluginSource, ...]` result produced by the operation.
        """
        custom = self._custom()
        return (OFFICIAL_SOURCE, *sorted(custom.values(), key=lambda item: (item.priority, item.id)))

    def add(self, source: PluginSource) -> None:
        """Add the plugin source store operation.

        Args:
            source: Source value or location to process.

        Returns:
            None.
        """
        if source.id == OFFICIAL_SOURCE_ID:
            raise PluginStoreError(f"plugin source {OFFICIAL_SOURCE_ID!r} is reserved")
        custom = self._custom()
        custom[source.id] = source
        self._write_sources(custom)

    def remove(self, source_id: str) -> None:
        """Remove the plugin source store operation.

        Args:
            source_id: Stable identifier for the source.

        Returns:
            None.
        """
        if source_id == OFFICIAL_SOURCE_ID:
            raise PluginStoreError(f"plugin source {OFFICIAL_SOURCE_ID!r} is reserved")
        custom = self._custom()
        if source_id not in custom:
            raise PluginStoreError(f"plugin source {source_id!r} is not configured")
        del custom[source_id]
        self._write_sources(custom)

    def fetch(self, source_id: str, *, refresh: bool = False) -> PluginIndex:
        """Fetch the plugin source store operation.

        Args:
            source_id: Stable identifier for the source.
            refresh: The refresh value used by the operation.

        Returns:
            The `PluginIndex` result produced by the operation.
        """
        source = next((item for item in self.list() if item.id == source_id), None)
        if source is None:
            raise PluginStoreError(f"plugin source {source_id!r} is not configured")
        cache = self.cache_directory / f"{source.id}.json"
        if cache.is_symlink() or (cache.exists() and not cache.is_file()):
            raise PluginStoreError(f"cached plugin index {source.id!r} is unsafe")
        if cache.is_file() and not refresh:
            if cache.stat().st_size > _MAX_INDEX_BYTES:
                raise PluginStoreError(f"cached plugin index {source.id!r} exceeded the 8 MiB limit")
            try:
                return PluginIndex.parse(json.loads(cache.read_text(encoding="utf-8")))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise PluginStoreError(f"cached plugin index {source.id!r} is invalid") from error
        try:
            request = Request(source.url, headers={"User-Agent": "liteyukibot-v7-plugin-index"})
            with _open_public_url(request, timeout=15, subject="plugin source redirect") as response:
                _https_url(response.geturl(), "plugin source redirect")
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

    def search(
        self,
        query: str = "",
        *,
        source_id: str | None = None,
        refresh: bool = False,
    ) -> tuple[PluginSearchResult, ...]:
        """Search cached or refreshed plugin indexes by human-facing metadata.

        Args:
            query: Case-insensitive text matched against identity, display name,
                summary, and publisher fields. Empty text returns every release.
            source_id: Optional single source to search.
            refresh: Whether to bypass existing source caches.

        Returns:
            Deterministically ordered matching source and bundle pairs.

        Raises:
            PluginStoreError: If the selected source is unavailable, or every
                configured source fails before any index can be searched.
        """
        needle = query.strip().casefold()
        selected = tuple(source for source in self.list() if source_id is None or source.id == source_id)
        if not selected:
            raise PluginStoreError(f"plugin source {source_id!r} is not configured")
        results: list[PluginSearchResult] = []
        failures: list[str] = []
        succeeded = 0
        for source in selected:
            try:
                index = self.fetch(source.id, refresh=refresh)
            except PluginStoreError as error:
                failures.append(f"{source.id}: {error}")
                continue
            succeeded += 1
            results.extend(PluginSearchResult(source, bundle) for bundle in index.search(needle))
        if succeeded == 0:
            raise PluginStoreError(f"cannot search plugin sources ({'; '.join(failures)})")
        return tuple(sorted(results, key=lambda item: (item.bundle.id, item.source.priority, item.source.id)))

    def cached_digest(self, source_id: str) -> str | None:
        """Implement the cached digest operation for the plugin source store.

        Args:
            source_id: Stable identifier for the source.

        Returns:
            The `str | None` result produced by the operation.
        """
        path = self.cache_directory / f"{source_id}.sha256"
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise PluginStoreError(f"cached plugin source digest for {source_id!r} is invalid")
        return value

    def _custom(self) -> dict[str, PluginSource]:
        """Implement the custom operation for the plugin source store.

        Returns:
            The `dict[str, PluginSource]` result produced by the operation.

        Notes:
            Internal implementation detail for `PluginSourceStore._custom`. It delegates to `is_file`,
            `loads`, `read_text`, `get` while keeping intermediate state local to the owning operation.
        """
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
        except (AttributeError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PluginStoreError("plugin source configuration is invalid") from error
        if len(sources) != len(value["sources"]) or OFFICIAL_SOURCE_ID in sources:
            raise PluginStoreError("plugin source configuration contains duplicate or reserved IDs")
        return sources

    @staticmethod
    def _source(value: object) -> PluginSource:
        """Implement the source operation for the plugin source store.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `PluginSource` result produced by the operation.

        Notes:
            Internal implementation detail for `PluginSourceStore._source`. It delegates to `get` while
            keeping intermediate state local to the owning operation.
        """
        if not isinstance(value, dict):
            raise PluginStoreError("plugin source configuration entry must be an object")
        return PluginSource(value["id"], value["url"], value.get("priority", 100))

    def _write_sources(self, sources: dict[str, PluginSource]) -> None:
        """Write sources.

        Args:
            sources: The sources value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `PluginSourceStore._write_sources`. It delegates to
            `document`, `sorted`, `values`, `_write_text` while keeping intermediate state local to the
            owning operation.
        """
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
        """Write text.

        Args:
            path: Filesystem or logical resource path.
            text: The text value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `PluginSourceStore._write_text`. It delegates to `mkdir`,
            `with_suffix`, `write_text`, `replace` while keeping intermediate state local to the owning
            operation.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)


__all__ = [
    "OFFICIAL_SOURCE",
    "OFFICIAL_SOURCE_ID",
    "OFFICIAL_SOURCE_URL",
    "PluginSource",
    "PluginSearchResult",
    "PluginSourceStore",
]
