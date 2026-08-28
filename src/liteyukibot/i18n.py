"""Resource-pack backed message catalogs for user-facing clients."""

from __future__ import annotations

import locale
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from liteyukibot_kernel import ServiceKey

from .resource_packs import ResourceCatalog

DEFAULT_LOCALE = "en-US"
SUPPORTED_LOCALES = ("en-US", "zh-CN")
I18N_SERVICE = ServiceKey("liteyukibot.i18n", 1)


def normalize_locale(value: str) -> str:
    """Normalize locale.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.
    """
    normalized = value.strip().replace("_", "-")
    aliases = {"en": "en-US", "zh": "zh-CN", "zh-Hans": "zh-CN"}
    return aliases.get(normalized, normalized)


def system_locale() -> str:
    """Implement the system locale operation for the component.

    Returns:
        The `str` result produced by the operation.
    """
    detected = locale.getlocale()[0] or os.environ.get("LANG", "")
    normalized = normalize_locale(detected.split(".", maxsplit=1)[0])
    return normalized if normalized in SUPPORTED_LOCALES else DEFAULT_LOCALE


def terminal_supports_cjk() -> bool:
    """Implement the terminal supports cjk operation for the component.

    Returns:
        Whether the requested condition is satisfied.
    """
    if not sys.stdout.isatty() or not (sys.stdout.encoding or "").lower().startswith("utf"):
        return False
    if sys.platform != "win32":
        return True
    font_directory = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Fonts"
    if not font_directory.is_dir():
        return False
    candidates = ("msyh", "simhei", "simsun", "deng", "noto")
    return any(candidate in file.name.casefold() for file in font_directory.iterdir() for candidate in candidates)


def select_locale(value: str = "auto") -> tuple[str, str | None]:
    """Select locale.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `tuple[str, str | None]` result produced by the operation.
    """
    requested = value.strip() or "auto"
    automatic = requested == "auto"
    selected = system_locale() if automatic else normalize_locale(requested)
    if selected not in SUPPORTED_LOCALES:
        selected = DEFAULT_LOCALE
    if selected == "zh-CN" and not terminal_supports_cjk():
        warning = "Chinese terminal font support was not detected"
        return (DEFAULT_LOCALE if automatic else selected, warning)
    return selected, None


def _parse_lang(text: str, source: str) -> dict[str, str]:
    """Parse lang.

    Args:
        text: The text value used by the operation.
        source: Source value or location to process.

    Returns:
        The `dict[str, str]` result produced by the operation.

    Notes:
        Internal implementation detail for `_parse_lang`. It delegates to `enumerate`, `splitlines`,
        `strip`, `startswith` while keeping intermediate state local to the owning operation.
    """
    entries: dict[str, str] = {}
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid language entry at {source}:{line_number}")
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        if not key or key in entries:
            raise ValueError(f"invalid language key at {source}:{line_number}")
        entries[key] = value.strip()
    return entries


@dataclass(frozen=True, slots=True)
class Translator:
    """Represent the translator contract."""
    locale: str
    catalogs: Mapping[str, Mapping[str, str]]

    @classmethod
    def from_resources(cls, resources: ResourceCatalog, locale: str = "auto") -> tuple[Translator, str | None]:
        """Create the translator from resources.

        Args:
            resources: The resources value used by the operation.
            locale: The locale value used by the operation.

        Returns:
            The `tuple[Translator, str | None]` result produced by the operation.
        """
        selected, warning = select_locale(locale)
        catalogs: dict[str, dict[str, str]] = {}
        for resource in resources.files("lang"):
            if not resource.path.endswith(".lang"):
                continue
            language = normalize_locale(resource.path.rsplit("/", maxsplit=1)[-1][:-5])
            source = f"{resource.pack_id}:{resource.path}"
            catalogs.setdefault(language, {}).update(_parse_lang(resource.read_text(), source))
        return cls(selected, catalogs), warning

    def text(self, key: str, /, default: str | None = None, **values: object) -> str:
        """Implement the text operation for the translator.

        Args:
            key: Stable FIFO ordering key for the queued work.
            default: The default value used by the operation.
            **values: The values value used by the operation.

        Returns:
            The `str` result produced by the operation.
        """
        return self.text_for(self.locale, key, default, **values)

    def text_for(self, locale: str, key: str, /, default: str | None = None, **values: object) -> str:
        """Implement the text for operation for the translator.

        Args:
            locale: The locale value used by the operation.
            key: Stable FIFO ordering key for the queued work.
            default: The default value used by the operation.
            **values: The values value used by the operation.

        Returns:
            The `str` result produced by the operation.
        """
        selected = normalize_locale(locale)
        if selected not in SUPPORTED_LOCALES:
            selected = self.locale
        value = self.catalogs.get(selected, {}).get(key)
        if value is None:
            value = self.catalogs.get(DEFAULT_LOCALE, {}).get(key, default if default is not None else key)
        try:
            return value.format_map(_PlaceholderValues(values))
        except ValueError:
            return value


class _PlaceholderValues(dict[str, object]):
    """Represent the placeholder values contract."""
    def __missing__(self, key: str) -> str:
        """Implement the missing operation for the placeholder values.

        Args:
            key: Stable FIFO ordering key for the queued work.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `_PlaceholderValues.__missing__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        return "{" + key + "}"


__all__ = [
    "DEFAULT_LOCALE",
    "I18N_SERVICE",
    "SUPPORTED_LOCALES",
    "Translator",
    "normalize_locale",
    "select_locale",
    "system_locale",
]
