from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from liteyukibot_permissions.service import create_permission_service
from pydantic import ValidationError

from liteyukibot import AuthorizationContext, ExtensionDefinition, ExtensionManifest, PluginContext, ToolDeclaration
from liteyukibot.config import CordisSettings
from liteyukibot.exceptions import PluginError
from liteyukibot.testing import PluginTestHarness


def test_extension_api_v2_rejects_explicit_v1_and_foreign_tool_ids() -> None:
    manifest = ExtensionManifest(
        id="example.tools",
        name="Example Tools",
        version="1.0.0",
        capabilities=("example.read",),
        tools=(
            ToolDeclaration(
                id="example.tools.echo",
                description="Echo JSON input",
                input_schema={"type": "object", "additionalProperties": False},
                output_schema={"type": "object"},
                capabilities=("example.read",),
            ),
        ),
    )

    assert manifest.api_version == 2
    with pytest.raises(ValidationError, match="api_version"):
        ExtensionManifest(id="example.tools", name="Example Tools", version="1.0.0", api_version=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="prefixed"):
        ExtensionManifest(
            id="example.tools",
            name="Example Tools",
            version="1.0.0",
            tools=(
                ToolDeclaration(
                    id="other.echo",
                    description="Foreign tool",
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                ),
            ),
        )


def test_permission_v2_uses_minimal_context_and_extension_ceilings() -> None:
    service = create_permission_service(
        {
            "roles": {"operator": ["example.read"]},
            "grants": [
                {
                    "runtime_id": "bridge",
                    "bot_id": "bot",
                    "actor_id": "actor",
                    "roles": ["operator"],
                }
            ],
            "plugin_capabilities": {"example.tools": ["example.read"]},
        }
    )
    context = AuthorizationContext("event", "bridge", "bot", "actor")

    assert service.activation_allowed("example.tools", frozenset({"example.read"}))
    assert not service.activation_allowed("example.tools", frozenset({"example.write"}))
    assert not service.activation_allowed("missing.extension", frozenset())
    assert service.allows_extension(context, "example.tools", "example.read", full=False)
    assert not service.allows_extension(context, "example.tools", "example.write", full=False)
    assert service.allows_extension(context, "full.cordis", "ungranted", full=True)

    decisions = service.audit()
    assert [decision.reason for decision in decisions] == ["granted", "not_granted", "full_host"]
    assert all(
        set(decision.__dataclass_fields__) == {"capability", "principal", "component", "event_id", "allowed", "reason"}
        for decision in decisions
    )


def test_cordis_access_can_only_downscope_enabled_plugins() -> None:
    settings = CordisSettings(enabled=("example.cordis",), access={"example.cordis": "limited"})
    assert settings.access == {"example.cordis": "limited"}
    with pytest.raises(ValidationError):
        CordisSettings(enabled=("example.cordis",), access={"other.cordis": "limited"})
    with pytest.raises(ValidationError):
        CordisSettings(enabled=("example.cordis",), access={"example.cordis": "full"})  # type: ignore[dict-item]


@pytest.mark.asyncio
async def test_native_setup_must_register_each_declared_tool(tmp_path: Path) -> None:
    async def handler(_context: AuthorizationContext, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    async def setup(context: PluginContext) -> None:
        context.register_tool("example.tools.echo", handler)

    definition = ExtensionDefinition(
        ExtensionManifest(
            id="example.tools",
            name="Example Tools",
            version="1.0.0",
            tools=(
                ToolDeclaration(
                    id="example.tools.echo",
                    description="Echo",
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                ),
            ),
        ),
        setup,
    )
    async with PluginTestHarness(definition, root=tmp_path):
        pass


@pytest.mark.asyncio
async def test_native_setup_rejects_a_declared_tool_without_a_handler(tmp_path: Path) -> None:
    async def setup(_context: PluginContext) -> None:
        return None

    definition = ExtensionDefinition(
        ExtensionManifest(
            id="example.tools",
            name="Example Tools",
            version="1.0.0",
            tools=(
                ToolDeclaration(
                    id="example.tools.echo",
                    description="Echo",
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                ),
            ),
        ),
        setup,
    )
    with pytest.raises(PluginError, match="setup failed"):
        async with PluginTestHarness(definition, root=tmp_path):
            pass
