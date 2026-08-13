"""v6 plugin metadata models."""

from __future__ import annotations

from enum import StrEnum
from types import ModuleType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PluginType(StrEnum):
    APPLICATION = "application"
    SERVICE = "service"
    MODULE = "module"
    UNCLASSIFIED = "unclassified"
    TEST = "test"


class PluginMetadata(BaseModel):
    name: str
    description: str = ""
    usage: str = ""
    type: PluginType = PluginType.UNCLASSIFIED
    author: str = ""
    homepage: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class Plugin(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    module: ModuleType
    module_name: str
    metadata: PluginMetadata

    def __hash__(self) -> int:
        return hash(self.module_name)


__all__ = ["Plugin", "PluginMetadata", "PluginType"]
