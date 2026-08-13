from __future__ import annotations

import pytest
from liteyukibot_agent_resolver import (
    AgentModule,
    AgentToolDescriptor,
    ResolutionError,
    Resolver,
)


def _tool(
    tool_id: str,
    module_id: str = "tools",
    *,
    required_capabilities: tuple[str, ...] = (),
) -> AgentToolDescriptor:
    return AgentToolDescriptor(
        id=tool_id,
        module_id=module_id,
        title=tool_id.rsplit(".", maxsplit=1)[-1],
        description=f"Use {tool_id}.",
        input_schema={"type": "object", "properties": {}},
        required_capabilities=required_capabilities,
    )


def test_resolver_returns_dependency_order_and_only_permitted_tools() -> None:
    resolver = Resolver(
        (
            AgentModule("base", provides_capabilities=("tool.public",)),
            AgentModule("tools", requires=("base",)),
        ),
        (
            _tool("docs.search"),
            _tool("admin.reset", required_capabilities=("admin.reset",)),
        ),
    )

    resolution = resolver.resolve(("tools",))

    assert tuple(module.id for module in resolution.modules) == ("base", "tools")
    assert resolution.capabilities == frozenset({"tool.public"})
    assert tuple(tool.id for tool in resolution.tools) == ("docs.search",)
    assert tuple(node.id for node in resolution.tool_tree.direct(2)) == ("docs",)
    assert tuple(tool.id for tool in resolution.tool_tree.search("search", 2)) == ("docs.search",)


def test_resolver_allows_explicitly_granted_tool_capabilities() -> None:
    resolver = Resolver((AgentModule("tools"),), (_tool("admin.reset", required_capabilities=("admin.reset",)),))

    resolution = resolver.resolve(("tools",), granted_capabilities=("admin.reset",))

    assert tuple(tool.id for tool in resolution.tools) == ("admin.reset",)


@pytest.mark.parametrize(
    ("modules", "requested", "message"),
    (
        ((AgentModule("a", requires=("missing",)),), ("a",), "not installed"),
        ((AgentModule("a", conflicts=("b",)), AgentModule("b")), ("a", "b"), "conflicts"),
        ((AgentModule("a", requires=("b",)), AgentModule("b", requires=("a",))), ("a",), "cycle"),
    ),
)
def test_resolver_rejects_invalid_closures(
    modules: tuple[AgentModule, ...], requested: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ResolutionError, match=message):
        Resolver(modules).resolve(requested)


def test_tool_tree_search_and_limits_are_bounded() -> None:
    resolver = Resolver(
        (AgentModule("tools"),),
        (_tool("docs.search"), _tool("docs.read"), _tool("issues.list")),
    )
    tree = resolver.resolve(("tools",)).tool_tree

    assert tuple(node.id for node in tree.direct(1)) == ("docs",)
    assert tuple(tool.id for tool in tree.search("docs", 1)) == ("docs.read",)
    assert tree.search("unknown", 1) == ()
    with pytest.raises(ValueError, match="limit"):
        tree.direct(0)
