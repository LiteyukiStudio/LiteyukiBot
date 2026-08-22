"""v6 plugin metadata models."""

from __future__ import annotations

from enum import StrEnum
from types import ModuleType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PluginType(StrEnum):
    """Enumerate the supported plugin type values."""
    APPLICATION = "application"
    SERVICE = "service"
    MODULE = "module"
    UNCLASSIFIED = "unclassified"
    TEST = "test"


class PluginMetadata(BaseModel):
    """Represent the validated plugin metadata contract."""
    name: str
    description: str = ""
    usage: str = ""
    type: PluginType = PluginType.UNCLASSIFIED
    author: str = ""
    homepage: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class Plugin(BaseModel):
    """Represent the validated plugin contract."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    module: ModuleType
    module_name: str
    metadata: PluginMetadata

    def __hash__(self) -> int:
        """Implement the hash operation for the plugin.

        Returns:
            The `int` result produced by the operation.
        """
        return hash(self.module_name)


__all__ = ["Plugin", "PluginMetadata", "PluginType"]
