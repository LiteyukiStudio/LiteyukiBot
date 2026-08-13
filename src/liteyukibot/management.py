"""Capability-aware management commands shared by terminal and extensions."""

from __future__ import annotations

import shlex
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from .plugin_install import PluginInstallationService
from .plugin_store import RuntimeGenerationStore
from .services import ServiceKey

MANAGEMENT_SERVICE = ServiceKey("liteyukibot.management", 1)
MANAGEMENT_ADMIN = "liteyukibot.management.admin"


class ManagementError(RuntimeError):
    pass


class ManagementDanger(StrEnum):
    NONE = "none"
    CONFIRM = "confirm"


@dataclass(frozen=True, slots=True)
class ManagementCaller:
    """A named command caller. The local terminal is the administrator caller."""

    id: str
    kind: str
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        if not self.id or self.id != self.id.strip() or not self.kind or self.kind != self.kind.strip():
            raise ValueError("management caller identity must be non-empty and trimmed")

    @classmethod
    def local_terminal(cls) -> ManagementCaller:
        return cls("local-terminal", "terminal", frozenset({MANAGEMENT_ADMIN}))


@dataclass(frozen=True, slots=True)
class ManagementCommand:
    name: tuple[str, ...]
    summary: str
    capability: str = MANAGEMENT_ADMIN
    danger: ManagementDanger = ManagementDanger.NONE
    owner: str = "liteyukibot.kernel"

    def __post_init__(self) -> None:
        if not self.name or any(not token or token != token.strip() for token in self.name):
            raise ValueError("management command name must contain non-empty tokens")
        if not self.summary.strip() or not self.capability.strip() or not self.owner.strip():
            raise ValueError("management command metadata must not be blank")


@dataclass(frozen=True, slots=True)
class ManagementResult:
    text: str
    data: Mapping[str, Any] | Sequence[Any] | str | int | float | bool | None = None


type ManagementHandler = Callable[[ManagementCaller, tuple[str, ...]], Awaitable[ManagementResult]]
type ManagementAuthorizer = Callable[[ManagementCaller, str], bool]


class ManagementRegistry:
    """Atomic, capability-gated command registry with no shell escape hatch."""

    def __init__(self) -> None:
        self._commands: dict[tuple[str, ...], tuple[ManagementCommand, ManagementHandler]] = {}
        self._authorizer: ManagementAuthorizer | None = None

    def set_authorizer(self, authorizer: ManagementAuthorizer | None) -> None:
        self._authorizer = authorizer

    def register(self, command: ManagementCommand, handler: ManagementHandler) -> None:
        if command.name in self._commands:
            raise ManagementError(f"management command already registered: {' '.join(command.name)}")
        self._commands[command.name] = (command, handler)

    def unregister_owner(self, owner: str) -> None:
        for name in [name for name, (command, _handler) in self._commands.items() if command.owner == owner]:
            del self._commands[name]

    def commands(self, caller: ManagementCaller) -> tuple[ManagementCommand, ...]:
        return tuple(
            command
            for command, _handler in sorted(self._commands.values(), key=lambda item: item[0].name)
            if self._allows(caller, command.capability)
        )

    def resolve(self, caller: ManagementCaller, line: str) -> tuple[ManagementCommand, tuple[str, ...]]:
        try:
            tokens = tuple(shlex.split(line))
        except ValueError as error:
            raise ManagementError(f"invalid command line: {error}") from error
        if not tokens:
            raise ManagementError("enter a command; use help to list available commands")
        selected: tuple[ManagementCommand, ManagementHandler] | None = None
        consumed = 0
        for name, candidate in self._commands.items():
            if len(name) <= len(tokens) and tokens[: len(name)] == name and len(name) > consumed:
                selected = candidate
                consumed = len(name)
        if selected is None:
            raise ManagementError(f"unknown management command: {' '.join(tokens)}")
        command, _handler = selected
        if not self._allows(caller, command.capability):
            raise ManagementError(f"management command is not authorized: {' '.join(command.name)}")
        return command, tokens[consumed:]

    def _allows(self, caller: ManagementCaller, capability: str) -> bool:
        if caller.kind == "terminal" and caller.id == "local-terminal":
            return capability in caller.capabilities
        return self._authorizer(caller, capability) if self._authorizer is not None else False

    async def execute(self, caller: ManagementCaller, line: str) -> tuple[ManagementCommand, ManagementResult]:
        command, arguments = self.resolve(caller, line)
        return command, await self._commands[command.name][1](caller, arguments)


class ManagementService(Protocol):
    registry: ManagementRegistry


class KernelManagement:
    def __init__(self, app: Any, workspace: str, stop: Callable[[], None]) -> None:
        self.registry = ManagementRegistry()
        self._app = app
        self._workspace = workspace
        self._stop = stop
        self._register_kernel_commands()

    def _register_kernel_commands(self) -> None:
        registrations = (
            (("help",), "List available management commands", self._help, ManagementDanger.NONE),
            (("status",), "Show kernel status", self._status, ManagementDanger.NONE),
            (("runtime", "list"), "List runtime health", self._runtime_list, ManagementDanger.NONE),
            (("runtime", "restart"), "Restart a runtime", self._runtime_restart, ManagementDanger.NONE),
            (("plugin", "list"), "List runtime plugin generations", self._plugin_list, ManagementDanger.NONE),
            (("plugin", "install"), "Install a runtime plugin bundle", self._plugin_install, ManagementDanger.NONE),
            (("plugin", "update"), "Update a runtime plugin generation", self._plugin_update, ManagementDanger.NONE),
            (("plugin", "enable"), "Enable a runtime plugin bundle", self._plugin_enable, ManagementDanger.NONE),
            (("plugin", "disable"), "Disable a runtime plugin bundle", self._plugin_disable, ManagementDanger.NONE),
            (
                ("plugin", "uninstall"),
                "Uninstall a runtime plugin bundle",
                self._plugin_uninstall,
                ManagementDanger.CONFIRM,
            ),
            (
                ("plugin", "rollback"),
                "Restore the previous runtime plugin generation",
                self._plugin_rollback,
                ManagementDanger.NONE,
            ),
            (("plugin", "gc"), "Remove unreferenced plugin generations", self._plugin_gc, ManagementDanger.CONFIRM),
            (("stop",), "Stop LiteyukiBot", self._stop_command, ManagementDanger.CONFIRM),
        )
        for name, summary, handler, danger in registrations:
            self.registry.register(ManagementCommand(name, summary, danger=danger), handler)

    async def _help(self, caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if arguments:
            raise ManagementError("usage: help")
        text = "\n".join(
            f"{' '.join(command.name)} - {command.summary}" for command in self.registry.commands(caller)
        )
        return ManagementResult(text)

    async def _status(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if arguments:
            raise ManagementError("usage: status")
        return ManagementResult(str(self._app.status()), self._app.status())

    async def _runtime_list(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if arguments:
            raise ManagementError("usage: runtime list")
        health = self._app.runtimes.health()
        text = "\n".join(f"{key}\t{value['state']}\t{value['kind']}" for key, value in health.items())
        return ManagementResult(text, health)

    async def _runtime_restart(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if len(arguments) != 1:
            raise ManagementError("usage: runtime restart <runtime-id>")
        await self._app.runtimes.restart(arguments[0])
        return ManagementResult(f"restarted {arguments[0]}")

    def _runtime(self, runtime_id: str) -> Any:
        try:
            runtime = self._app.settings.runtimes[runtime_id]
        except KeyError as error:
            raise ManagementError(f"runtime is not configured: {runtime_id}") from error
        if not runtime.enabled:
            raise ManagementError(f"runtime is disabled: {runtime_id}")
        return runtime

    async def _plugin_list(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if len(arguments) > 1:
            raise ManagementError("usage: plugin list [runtime-id]")
        store = RuntimeGenerationStore(self._workspace)
        records = store.list_generations(arguments[0] if arguments else None)
        text = "\n".join(f"{item.runtime_id}\t{item.id}\t{','.join(item.roots)}" for item in records)
        return ManagementResult(text or "no runtime plugin generations")

    async def _plugin_install(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if len(arguments) not in (2, 3):
            raise ManagementError("usage: plugin install <runtime-id> <bundle-id> [source-id]")
        runtime = self._runtime(arguments[0])
        result = PluginInstallationService(self._workspace).install(
            arguments[1],
            runtime_id=arguments[0],
            runtime_kind=runtime.kind,
            source_id=arguments[2] if len(arguments) == 3 else None,
        )
        return ManagementResult(f"installed {arguments[1]} as {result.generation.id}")

    async def _plugin_update(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if len(arguments) not in (1, 2):
            raise ManagementError("usage: plugin update <runtime-id> [source-id]")
        runtime = self._runtime(arguments[0])
        result = PluginInstallationService(self._workspace).update(
            runtime_id=arguments[0],
            runtime_kind=runtime.kind,
            source_id=arguments[1] if len(arguments) == 2 else None,
        )
        return ManagementResult(f"updated {arguments[0]} as {result.generation.id}")

    async def _plugin_enable(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        return await self._change_plugin("enable", arguments)

    async def _plugin_disable(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        return await self._change_plugin("disable", arguments)

    async def _change_plugin(self, operation: str, arguments: tuple[str, ...]) -> ManagementResult:
        if len(arguments) != 2:
            raise ManagementError(f"usage: plugin {operation} <runtime-id> <bundle-id>")
        runtime = self._runtime(arguments[0])
        service = PluginInstallationService(self._workspace)
        result = getattr(service, operation)(arguments[1], runtime_id=arguments[0], runtime_kind=runtime.kind)
        return ManagementResult(f"{operation}d {arguments[1]} as {result.generation.id}")

    async def _plugin_uninstall(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if len(arguments) != 2:
            raise ManagementError("usage: plugin uninstall <runtime-id> <bundle-id>")
        runtime = self._runtime(arguments[0])
        result = PluginInstallationService(self._workspace).uninstall(
            arguments[1], runtime_id=arguments[0], runtime_kind=runtime.kind
        )
        generation = result.generation.id if result.generation else "deactivated"
        return ManagementResult(f"uninstalled {arguments[1]}; {generation}")

    async def _plugin_rollback(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if len(arguments) != 1:
            raise ManagementError("usage: plugin rollback <runtime-id>")
        deployment = RuntimeGenerationStore(self._workspace).rollback(arguments[0])
        return ManagementResult(f"activated {deployment.runtime_generations[arguments[0]]}")

    async def _plugin_gc(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if len(arguments) > 1:
            raise ManagementError("usage: plugin gc [runtime-id]")
        collected = RuntimeGenerationStore(self._workspace).collect(arguments[0] if arguments else None)
        return ManagementResult(f"collected {len(collected)} runtime plugin generation(s)")

    async def _stop_command(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if arguments:
            raise ManagementError("usage: stop")
        self._stop()
        return ManagementResult("stopping LiteyukiBot")


__all__ = [
    "KernelManagement",
    "MANAGEMENT_ADMIN",
    "MANAGEMENT_SERVICE",
    "ManagementCaller",
    "ManagementCommand",
    "ManagementDanger",
    "ManagementError",
    "ManagementRegistry",
    "ManagementResult",
    "ManagementService",
]
