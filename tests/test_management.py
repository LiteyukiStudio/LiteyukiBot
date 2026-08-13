from __future__ import annotations

import pytest

from liteyukibot.management import (
    MANAGEMENT_ADMIN,
    ManagementCaller,
    ManagementCommand,
    ManagementDanger,
    ManagementError,
    ManagementRegistry,
    ManagementResult,
)


async def _result(_caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
    return ManagementResult(" ".join(arguments))


@pytest.mark.asyncio
async def test_management_registry_resolves_and_executes_quoted_arguments() -> None:
    registry = ManagementRegistry()
    command = ManagementCommand(("plugin", "install"), "Install a plugin")
    registry.register(command, _result)

    caller = ManagementCaller.local_terminal()
    selected, result = await registry.execute(caller, 'plugin install runtime "example plugin"')

    assert selected == command
    assert result.text == "runtime example plugin"


@pytest.mark.asyncio
async def test_management_registry_rejects_unauthorized_extension_callers() -> None:
    registry = ManagementRegistry()
    registry.register(ManagementCommand(("status",), "Show status"), _result)
    caller = ManagementCaller("plugin.example", "plugin", frozenset({MANAGEMENT_ADMIN}))

    with pytest.raises(ManagementError, match="not authorized"):
        await registry.execute(caller, "status")

    registry.set_authorizer(lambda actual, capability: actual.id == "plugin.example" and capability == MANAGEMENT_ADMIN)
    _command, result = await registry.execute(caller, "status")
    assert result.text == ""


def test_management_registry_lists_only_authorized_commands() -> None:
    registry = ManagementRegistry()
    registry.register(ManagementCommand(("status",), "Show status"), _result)
    registry.register(
        ManagementCommand(("stop",), "Stop", danger=ManagementDanger.CONFIRM),
        _result,
    )
    caller = ManagementCaller.local_terminal()

    assert tuple(command.name for command in registry.commands(caller)) == (("status",), ("stop",))
