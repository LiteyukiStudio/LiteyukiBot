"""Bounded, deterministic Agent Tool catalog discovery and exposure."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib import metadata

from liteyukibot_agent_resolver import AgentToolDescriptor

CATALOG_SEARCH_ID = "agent.catalog.search"
SANDBOX_TOOL_ENTRY_POINT_GROUP = "liteyukibot.agent_sandbox_tools"
INITIAL_TOOL_LIMIT = 8
SEARCH_RESULT_LIMIT = 8
ACTIVE_TOOL_LIMIT = 32


@dataclass(frozen=True, slots=True)
class CatalogSearchResult:
    tools: tuple[AgentToolDescriptor, ...]


@dataclass(frozen=True, slots=True)
class SandboxToolDefinition:
    """Static Tool metadata plus an importable fresh-worker handler reference."""

    descriptor: AgentToolDescriptor
    worker_ref: str

    def __post_init__(self) -> None:
        if not self.worker_ref or self.worker_ref != self.worker_ref.strip() or ":" not in self.worker_ref:
            raise ValueError("sandbox worker reference must be a non-empty module:path value")


class AgentCatalog:
    """Own the static Tool universe visible to one Agent bridge process."""

    def __init__(self, tools: Iterable[AgentToolDescriptor] = ()) -> None:
        ordered = tuple(sorted(tools, key=lambda tool: tool.id))
        ids = tuple(tool.id for tool in ordered)
        if len(ids) != len(set(ids)):
            raise ValueError("Agent Tool IDs must be unique")
        if CATALOG_SEARCH_ID in ids:
            raise ValueError(f"{CATALOG_SEARCH_ID!r} is reserved for the local catalog search")
        self._tools = ordered
        self._by_id = {tool.id: tool for tool in ordered}

    @property
    def tools(self) -> tuple[AgentToolDescriptor, ...]:
        return self._tools

    def initial(self) -> tuple[AgentToolDescriptor, ...]:
        return self._tools[: INITIAL_TOOL_LIMIT - 1]

    def search(self, query: str) -> CatalogSearchResult:
        normalized = query.strip().casefold()
        if not normalized:
            return CatalogSearchResult(())
        return CatalogSearchResult(
            tuple(
                tool
                for tool in self._tools
                if normalized in tool.id.casefold()
                or normalized in tool.title.casefold()
                or normalized in tool.description.casefold()
            )[:SEARCH_RESULT_LIMIT]
        )

    def get(self, tool_id: str) -> AgentToolDescriptor | None:
        return self._by_id.get(tool_id)


def discover_sandbox_tool_definitions() -> tuple[SandboxToolDefinition, ...]:
    """Load static declarations and worker references without executing a Tool."""

    tools: list[SandboxToolDefinition] = []
    for entry in metadata.entry_points(group=SANDBOX_TOOL_ENTRY_POINT_GROUP):
        loaded = entry.load()
        if not callable(loaded):
            raise RuntimeError(f"sandbox Tool entry point {entry.name!r} is not callable")
        definition = loaded()
        if not isinstance(definition, SandboxToolDefinition):
            raise RuntimeError(
                f"sandbox Tool entry point {entry.name!r} did not return SandboxToolDefinition"
            )
        if definition.descriptor.id != entry.name:
            raise RuntimeError(
                f"sandbox Tool entry point {entry.name!r} returned mismatched ID {definition.descriptor.id!r}"
            )
        tools.append(definition)
    return tuple(tools)


def discover_sandbox_tool_descriptors() -> tuple[AgentToolDescriptor, ...]:
    """Return only static metadata for catalog construction."""

    return tuple(definition.descriptor for definition in discover_sandbox_tool_definitions())


def openai_tool_schema(tool: AgentToolDescriptor) -> Mapping[str, object]:
    """Convert one resolver declaration to the OpenAI-compatible function shape."""

    return {
        "type": "function",
        "function": {
            "name": tool.id,
            "description": tool.description,
            "parameters": dict(tool.input_schema),
        },
    }


def catalog_search_schema() -> Mapping[str, object]:
    return {
        "type": "function",
        "function": {
            "name": CATALOG_SEARCH_ID,
            "description": "Search the configured Tool catalog before selecting a Tool.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "minLength": 1}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


__all__ = [
    "ACTIVE_TOOL_LIMIT",
    "CATALOG_SEARCH_ID",
    "INITIAL_TOOL_LIMIT",
    "SEARCH_RESULT_LIMIT",
    "SANDBOX_TOOL_ENTRY_POINT_GROUP",
    "AgentCatalog",
    "CatalogSearchResult",
    "SandboxToolDefinition",
    "catalog_search_schema",
    "discover_sandbox_tool_definitions",
    "discover_sandbox_tool_descriptors",
    "openai_tool_schema",
]
