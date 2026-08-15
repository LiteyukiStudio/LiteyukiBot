"""Capability-aware management commands shared by terminal and extensions."""

from __future__ import annotations

import os
import secrets
import shlex
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from .operations import (
    ManagementPrincipal,
    OperationConfirmation,
    OperationDefinition,
    OperationImpact,
    OperationLedger,
    OperationRecord,
    OperationRequest,
    PrincipalKind,
)
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


@dataclass(frozen=True, slots=True)
class ManagementOperationRoute:
    """Map a catalogued structured operation to one registered command."""

    definition: OperationDefinition
    command_name: tuple[str, ...]
    argument_fields: tuple[str, ...]
    target_field: str | None = None

    def target_for(self, input: Mapping[str, Any]) -> str:
        if self.target_field is None:
            return "kernel"
        target = input.get(self.target_field)
        return target if isinstance(target, str) else ""

    def arguments_from_input(self, input: Mapping[str, Any]) -> tuple[str, ...]:
        arguments: list[str] = []
        for field in self.argument_fields:
            value = input.get(field)
            if value is None:
                continue
            if not isinstance(value, str):
                raise ManagementError(f"invalid operation input field: {field}")
            arguments.append(value)
        return tuple(arguments)

    def input_from_arguments(self, arguments: tuple[str, ...]) -> dict[str, str]:
        if len(arguments) > len(self.argument_fields):
            raise ManagementError(f"too many arguments for operation: {self.definition.id}")
        return {field: arguments[index] for index, field in enumerate(self.argument_fields[: len(arguments)])}


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

    def command(self, name: tuple[str, ...]) -> ManagementCommand:
        try:
            return self._commands[name][0]
        except KeyError as error:
            raise ManagementError(f"management command is not registered: {' '.join(name)}") from error

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
        self.operations: OperationLedger | None = None
        self._owns_operations = False
        self._operation_routes: dict[str, ManagementOperationRoute] = {}
        self._register_kernel_commands()

    async def start_operations(self, data_dir: Path) -> None:
        """Start durable command execution after all command providers are registered."""

        if self.operations is not None:
            return
        ledger = OperationLedger(data_dir / "operations.sqlite3", audit_key=self._audit_key(data_dir))
        self.bind_operations(ledger)
        self._owns_operations = True
        await ledger.start()

    def bind_operations(self, ledger: OperationLedger) -> None:
        """Bind a daemon-owned ledger without starting or closing it."""

        if self.operations is not None and self.operations is not ledger:
            raise ManagementError("management operation service is already bound")
        if self.operations is ledger:
            return
        self.operations = ledger
        for route in self._operation_routes.values():
            ledger.register(route.definition, self.execute_structured_operation)

    async def close_operations(self) -> None:
        if self.operations is not None and self._owns_operations:
            await self.operations.close()
        self.operations = None
        self._owns_operations = False

    async def submit_operation(
        self,
        principal: ManagementPrincipal,
        command_name: tuple[str, ...],
        arguments: tuple[str, ...],
        *,
        confirmed: bool,
        idempotency_key: str,
    ) -> OperationRecord:
        """Queue an authorized management command without persisting its raw arguments."""

        if self.operations is None:
            raise ManagementError("management operation service is not running")
        caller = ManagementCaller(principal.subject, principal.kind.value, principal.capabilities)
        command = self.registry.resolve(caller, shlex.join((*command_name, *arguments)))[0]
        if command.danger is ManagementDanger.CONFIRM and not confirmed:
            raise ManagementError(f"management command requires confirmation: {' '.join(command.name)}")
        operation_name = self._operation_name(command.name)
        route = self._operation_routes.get(operation_name)
        if route is not None:
            input = route.input_from_arguments(arguments)
            target = route.target_for(input)
            return await self.submit_structured_operation(
                principal,
                operation_name,
                target,
                input,
                confirmed=confirmed,
                confirmation_target=target if confirmed else None,
                idempotency_key=idempotency_key,
            )
        if not self.operations.has_definition(operation_name):
            self.operations.register(
                OperationDefinition(
                    operation_name,
                    command.capability,
                    mutating=command.name not in {("help",), ("status",), ("runtime", "list"), ("plugin", "list")},
                    cancellable=False,
                ),
                self._execute_operation,
            )
        return await self.operations.submit(
            principal,
            OperationRequest(
                operation=operation_name,
                target=arguments[0] if arguments else "kernel",
                input={"command": list(command.name), "arguments": list(arguments)},
                idempotency_key=idempotency_key,
                confirmed=confirmed,
            ),
        )

    def operation_catalog(self, principal: ManagementPrincipal) -> tuple[dict[str, Any], ...]:
        """Return WebUI-safe operation metadata, without exposing command strings."""

        return tuple(
            route.definition.catalog_entry()
            for route in self._operation_routes.values()
            if self._route_is_authorized(principal, route)
        )

    async def submit_structured_operation(
        self,
        principal: ManagementPrincipal,
        operation_id: str,
        target: str,
        input: Mapping[str, Any],
        *,
        confirmed: bool,
        confirmation_target: str | None,
        idempotency_key: str,
    ) -> OperationRecord:
        """Submit a catalogued operation without accepting a raw command line."""

        if self.operations is None:
            raise ManagementError("management operation service is not running")
        route = self._operation_routes.get(operation_id)
        if route is None:
            raise ManagementError(f"unknown structured operation: {operation_id}")
        if target != route.target_for(input):
            raise ManagementError("operation target does not match structured input")
        return await self.operations.submit(
            principal,
            OperationRequest(
                operation=operation_id,
                target=target,
                input=input,
                idempotency_key=idempotency_key,
                confirmed=confirmed,
                confirmation_target=confirmation_target,
            ),
        )

    async def execute_structured_operation(self, principal: ManagementPrincipal, request: OperationRequest) -> str:
        """Execute one validated route for a daemon-owned ledger worker bridge."""

        route = self._operation_routes.get(request.operation)
        if route is None:
            raise ManagementError(f"unknown structured operation: {request.operation}")
        if request.target != route.target_for(request.input):
            raise ManagementError("operation target does not match structured input")
        validation_error = OperationLedger.validate_request(route.definition, request)
        if validation_error is not None:
            raise ManagementError(f"invalid structured operation: {validation_error}")
        return await self._execute_operation(principal, request)

    async def _execute_operation(self, principal: ManagementPrincipal, request: OperationRequest) -> str:
        command_name = self._command_name(request.operation)
        route = self._operation_routes.get(request.operation)
        if route is not None:
            arguments = route.arguments_from_input(request.input)
        else:
            raw_arguments = request.input.get("arguments")
            if not isinstance(raw_arguments, list) or not all(isinstance(argument, str) for argument in raw_arguments):
                raise ManagementError("invalid management operation payload")
            arguments = tuple(raw_arguments)
        caller = (
            ManagementCaller.local_terminal()
            if principal.kind is PrincipalKind.SYSTEM and principal.authentication_origin == "daemon-control"
            else ManagementCaller(principal.subject, principal.kind.value, principal.capabilities)
        )
        await self.registry.execute(caller, shlex.join((*command_name, *arguments)))
        return "ok"

    def _route_is_authorized(self, principal: ManagementPrincipal, route: ManagementOperationRoute) -> bool:
        if not principal.allows(route.definition.capability):
            return False
        caller = ManagementCaller(principal.subject, principal.kind.value, principal.capabilities)
        try:
            self.registry.resolve(caller, shlex.join(route.command_name))
        except ManagementError:
            return False
        return True

    @staticmethod
    def _operation_name(command_name: tuple[str, ...]) -> str:
        return f"management.{'.'.join(command_name)}"

    @staticmethod
    def _command_name(operation_name: str) -> tuple[str, ...]:
        if not operation_name.startswith("management."):
            raise ManagementError("invalid management operation")
        tokens = tuple(operation_name.removeprefix("management.").split("."))
        if not tokens or any(not token for token in tokens):
            raise ManagementError("invalid management operation")
        return tokens

    @staticmethod
    def _audit_key(data_dir: Path) -> bytes:
        path = data_dir / "operations.audit-key"
        try:
            key = path.read_bytes()
        except FileNotFoundError:
            key = secrets.token_bytes(32)
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                key = path.read_bytes()
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(key)
                path.chmod(0o600)
        if len(key) != 32:
            raise ManagementError("management audit key must contain exactly 32 bytes")
        return key

    def _register_kernel_commands(self) -> None:
        registrations = (
            (("help",), "List available management commands", self._help, ManagementDanger.NONE),
            (("status",), "Show kernel status", self._status, ManagementDanger.NONE),
            (("runtime", "list"), "List runtime health", self._runtime_list, ManagementDanger.NONE),
            (("runtime", "start"), "Start a runtime", self._runtime_start, ManagementDanger.NONE),
            (("runtime", "stop"), "Stop a runtime", self._runtime_stop, ManagementDanger.CONFIRM),
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
        self._register_operation_routes()

    def _register_operation_routes(self) -> None:
        object_schema = {"type": "object", "additionalProperties": False}

        def register(
            command_name: tuple[str, ...],
            fields: tuple[str, ...],
            schema: Mapping[str, Any],
            *,
            impact: OperationImpact = OperationImpact.STANDARD,
            confirmation: OperationConfirmation = OperationConfirmation.EXPLICIT,
            target_field: str | None = "runtime_id",
        ) -> None:
            operation_id = self._operation_name(command_name)
            command = self.registry.command(command_name)
            self._operation_routes[operation_id] = ManagementOperationRoute(
                OperationDefinition(
                    operation_id,
                    command.capability,
                    mutating=True,
                    input_schema={**object_schema, **schema},
                    impact=impact,
                    confirmation=confirmation,
                    target=target_field or "kernel",
                    target_input_field=target_field,
                ),
                command_name,
                fields,
                target_field,
            )

        runtime_id = {"runtime_id": {"type": "string", "minLength": 1}}
        bundle_id = {"bundle_id": {"type": "string", "minLength": 1}}
        source_id = {"source_id": {"type": "string", "minLength": 1}}
        register(("runtime", "start"), ("runtime_id",), {"properties": runtime_id, "required": ["runtime_id"]})
        register(
            ("runtime", "stop"),
            ("runtime_id",),
            {"properties": runtime_id, "required": ["runtime_id"]},
            impact=OperationImpact.HIGH,
            confirmation=OperationConfirmation.TARGET,
        )
        register(("runtime", "restart"), ("runtime_id",), {"properties": runtime_id, "required": ["runtime_id"]})
        register(
            ("plugin", "install"),
            ("runtime_id", "bundle_id", "source_id"),
            {"properties": {**runtime_id, **bundle_id, **source_id}, "required": ["runtime_id", "bundle_id"]},
        )
        register(
            ("plugin", "update"),
            ("runtime_id", "source_id"),
            {"properties": {**runtime_id, **source_id}, "required": ["runtime_id"]},
        )
        for operation in ("enable", "disable"):
            register(
                ("plugin", operation),
                ("runtime_id", "bundle_id"),
                {"properties": {**runtime_id, **bundle_id}, "required": ["runtime_id", "bundle_id"]},
            )
        register(
            ("plugin", "rollback"),
            ("runtime_id",),
            {"properties": runtime_id, "required": ["runtime_id"]},
            impact=OperationImpact.HIGH,
            confirmation=OperationConfirmation.TARGET,
        )

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

    async def _runtime_start(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if len(arguments) != 1:
            raise ManagementError("usage: runtime start <runtime-id>")
        await self._app.runtimes.start_runtime(arguments[0])
        return ManagementResult(f"started {arguments[0]}")

    async def _runtime_stop(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        if len(arguments) != 1:
            raise ManagementError("usage: runtime stop <runtime-id>")
        await self._app.runtimes.stop_runtime(arguments[0])
        return ManagementResult(f"stopped {arguments[0]}")

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
    "ManagementOperationRoute",
    "ManagementRegistry",
    "ManagementResult",
    "ManagementService",
]
