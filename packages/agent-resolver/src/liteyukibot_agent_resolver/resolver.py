"""Pure dependency closure and tree search for agent-provided tools."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


class ResolutionError(ValueError):
    """Raised when a declarative agent module set is invalid or unsatisfiable."""


def _identifier(value: str, *, field: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty trimmed identifier")
    return value


def _identifiers(values: Iterable[str], *, field: str) -> tuple[str, ...]:
    normalized = tuple(_identifier(value, field=field) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class AgentModule:
    """A label-only module used to determine an activation closure."""

    id: str
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    provides_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _identifier(self.id, field="module id"))
        object.__setattr__(self, "requires", _identifiers(self.requires, field="module requirements"))
        object.__setattr__(self, "conflicts", _identifiers(self.conflicts, field="module conflicts"))
        object.__setattr__(
            self,
            "provides_capabilities",
            _identifiers(self.provides_capabilities, field="module capabilities"),
        )
        if self.id in self.requires or self.id in self.conflicts:
            raise ValueError("a module cannot require or conflict with itself")


@dataclass(frozen=True, slots=True)
class AgentToolDescriptor:
    """JSON-safe metadata for a tool whose executable remains outside this package."""

    id: str
    module_id: str
    title: str
    description: str
    input_schema: Mapping[str, object]
    required_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _identifier(self.id, field="tool id"))
        object.__setattr__(self, "module_id", _identifier(self.module_id, field="tool module id"))
        if not self.title.strip() or not self.description.strip():
            raise ValueError("tool title and description must be non-empty")
        if self.input_schema.get("type") != "object":
            raise ValueError("tool input schema must describe a JSON object")
        object.__setattr__(
            self,
            "required_capabilities",
            _identifiers(self.required_capabilities, field="tool required capabilities"),
        )


@dataclass(frozen=True, slots=True)
class ToolTreeNode:
    """One visible path node; only leaves may carry an executable descriptor."""

    id: str
    children: tuple[ToolTreeNode, ...] = ()
    tool: AgentToolDescriptor | None = None


@dataclass(frozen=True, slots=True)
class AgentToolTree:
    """Bounded direct exposure plus deterministic search over resolved tools."""

    roots: tuple[ToolTreeNode, ...]
    tools: tuple[AgentToolDescriptor, ...]

    def direct(self, limit: int) -> tuple[ToolTreeNode, ...]:
        if limit < 1:
            raise ValueError("direct tool limit must be at least 1")
        return self.roots[:limit]

    def search(self, query: str, limit: int) -> tuple[AgentToolDescriptor, ...]:
        if limit < 1:
            raise ValueError("search result limit must be at least 1")
        normalized = query.strip().casefold()
        if not normalized:
            return ()
        return tuple(
            tool
            for tool in sorted(self.tools, key=lambda descriptor: descriptor.id)
            if normalized in tool.id.casefold()
            or normalized in tool.title.casefold()
            or normalized in tool.description.casefold()
        )[:limit]


@dataclass(frozen=True, slots=True)
class Resolution:
    """The deterministic activation result passed to a kernel broker or harness."""

    modules: tuple[AgentModule, ...]
    capabilities: frozenset[str]
    tools: tuple[AgentToolDescriptor, ...]
    tool_tree: AgentToolTree


class Resolver:
    """Resolve labels without process, environment, or package side effects."""

    def __init__(
        self,
        modules: Iterable[AgentModule],
        tools: Iterable[AgentToolDescriptor] = (),
    ) -> None:
        module_items = tuple(modules)
        self._modules = {module.id: module for module in module_items}
        if not self._modules:
            raise ValueError("at least one agent module is required")
        if len(self._modules) != len(module_items):
            raise ValueError("agent module ids must be unique")
        self._tools = tuple(tools)
        tool_ids = tuple(tool.id for tool in self._tools)
        if len(set(tool_ids)) != len(tool_ids):
            raise ValueError("agent tool ids must be unique")
        unknown_modules = sorted({tool.module_id for tool in self._tools} - self._modules.keys())
        if unknown_modules:
            raise ValueError(f"tools reference unknown module(s): {', '.join(unknown_modules)}")

    def resolve(
        self,
        requested: Iterable[str],
        *,
        granted_capabilities: Iterable[str] = (),
    ) -> Resolution:
        requested_ids = _identifiers(requested, field="requested modules")
        if not requested_ids:
            raise ValueError("at least one agent module must be requested")
        granted = frozenset(_identifiers(granted_capabilities, field="granted capabilities"))
        ordered: list[AgentModule] = []
        visiting: set[str] = set()
        selected: set[str] = set()

        def visit(module_id: str) -> None:
            if module_id in selected:
                return
            if module_id in visiting:
                raise ResolutionError(f"agent module dependency cycle includes {module_id!r}")
            module = self._modules.get(module_id)
            if module is None:
                raise ResolutionError(f"agent module {module_id!r} is not installed")
            visiting.add(module_id)
            for requirement in module.requires:
                visit(requirement)
            visiting.remove(module_id)
            selected.add(module_id)
            ordered.append(module)

        for module_id in requested_ids:
            visit(module_id)

        selected_ids = frozenset(selected)
        conflicts = sorted(
            f"{module.id} conflicts with {conflict}"
            for module in ordered
            for conflict in module.conflicts
            if conflict in selected_ids
        )
        if conflicts:
            raise ResolutionError("; ".join(conflicts))

        capabilities = frozenset(
            capability
            for module in ordered
            for capability in module.provides_capabilities
        )
        available_capabilities = capabilities | granted
        enabled_tools = tuple(
            tool
            for tool in self._tools
            if tool.module_id in selected_ids
            and set(tool.required_capabilities).issubset(available_capabilities)
        )
        return Resolution(
            modules=tuple(ordered),
            capabilities=available_capabilities,
            tools=enabled_tools,
            tool_tree=_tool_tree(enabled_tools),
        )


def _tool_tree(tools: tuple[AgentToolDescriptor, ...]) -> AgentToolTree:
    nodes: dict[str, dict[str, object]] = {}
    roots: dict[str, dict[str, object]] = {}
    for tool in tools:
        parent = roots
        parts = tool.id.split(".")
        path: list[str] = []
        for index, part in enumerate(parts):
            path.append(part)
            node_id = ".".join(path)
            node = nodes.setdefault(node_id, {"children": {}, "tool": None})
            parent.setdefault(part, node)
            if index == len(parts) - 1:
                node["tool"] = tool
            parent = node["children"]  # type: ignore[assignment]

    def freeze(branch: Mapping[str, dict[str, object]], prefix: str = "") -> tuple[ToolTreeNode, ...]:
        return tuple(
            ToolTreeNode(
                id=f"{prefix}.{name}" if prefix else name,
                children=freeze(node["children"], f"{prefix}.{name}" if prefix else name),  # type: ignore[arg-type]
                tool=node["tool"],  # type: ignore[arg-type]
            )
            for name, node in sorted(branch.items())
        )

    return AgentToolTree(roots=freeze(roots), tools=tools)
