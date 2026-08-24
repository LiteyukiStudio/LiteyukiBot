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
    """Raised when the management contract cannot be satisfied."""
    pass


class ManagementDanger(StrEnum):
    """Enumerate the supported management danger values."""
    NONE = "none"
    CONFIRM = "confirm"


@dataclass(frozen=True, slots=True)
class ManagementCaller:
    """A named command caller. The local terminal is the administrator caller."""

    id: str
    kind: str
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        """Validate and normalize the management caller after initialization.

        Returns:
            None.
        """
        if not self.id or self.id != self.id.strip() or not self.kind or self.kind != self.kind.strip():
            raise ValueError("management caller identity must be non-empty and trimmed")

    @classmethod
    def local_terminal(cls) -> ManagementCaller:
        """Implement the local terminal operation for the management caller.

        Returns:
            The `ManagementCaller` result produced by the operation.
        """
        return cls("local-terminal", "terminal", frozenset({MANAGEMENT_ADMIN}))


@dataclass(frozen=True, slots=True)
class ManagementCommand:
    """Represent the management command contract."""
    name: tuple[str, ...]
    summary: str
    capability: str = MANAGEMENT_ADMIN
    danger: ManagementDanger = ManagementDanger.NONE
    owner: str = "liteyukibot.kernel"

    def __post_init__(self) -> None:
        """Validate and normalize the management command after initialization.

        Returns:
            None.
        """
        if not self.name or any(not token or token != token.strip() for token in self.name):
            raise ValueError("management command name must contain non-empty tokens")
        if not self.summary.strip() or not self.capability.strip() or not self.owner.strip():
            raise ValueError("management command metadata must not be blank")


@dataclass(frozen=True, slots=True)
class ManagementResult:
    """Represent the validated management result contract."""
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
        """Implement the target for operation for the management operation route.

        Args:
            input: The input value used by the operation.

        Returns:
            The `str` result produced by the operation.
        """
        if self.target_field is None:
            return "kernel"
        target = input.get(self.target_field)
        return target if isinstance(target, str) else ""

    def arguments_from_input(self, input: Mapping[str, Any]) -> tuple[str, ...]:
        """Implement the arguments from input operation for the management operation route.

        Args:
            input: The input value used by the operation.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
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
        """Implement the input from arguments operation for the management operation route.

        Args:
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `dict[str, str]` result produced by the operation.
        """
        if len(arguments) > len(self.argument_fields):
            raise ManagementError(f"too many arguments for operation: {self.definition.id}")
        return {field: arguments[index] for index, field in enumerate(self.argument_fields[: len(arguments)])}


type ManagementHandler = Callable[[ManagementCaller, tuple[str, ...]], Awaitable[ManagementResult]]
type ManagementAuthorizer = Callable[[ManagementCaller, str], bool]


class ManagementRegistry:
    """Atomic, capability-gated command registry with no shell escape hatch."""

    def __init__(self) -> None:
        """Initialize the management registry.

        Returns:
            None.
        """
        self._commands: dict[tuple[str, ...], tuple[ManagementCommand, ManagementHandler]] = {}
        self._authorizer: ManagementAuthorizer | None = None

    def set_authorizer(self, authorizer: ManagementAuthorizer | None) -> None:
        """Set authorizer.

        Args:
            authorizer: The authorizer value used by the operation.

        Returns:
            None.
        """
        self._authorizer = authorizer

    def register(self, command: ManagementCommand, handler: ManagementHandler) -> None:
        """Register the management registry operation.

        Args:
            command: Command or operation name to execute.
            handler: Callable that handles the dispatched value.

        Returns:
            None.
        """
        if command.name in self._commands:
            raise ManagementError(f"management command already registered: {' '.join(command.name)}")
        self._commands[command.name] = (command, handler)

    def command(self, name: tuple[str, ...]) -> ManagementCommand:
        """Implement the command operation for the management registry.

        Args:
            name: Stable name used to identify the value.

        Returns:
            The `ManagementCommand` result produced by the operation.
        """
        try:
            return self._commands[name][0]
        except KeyError as error:
            raise ManagementError(f"management command is not registered: {' '.join(name)}") from error

    def unregister_owner(self, owner: str) -> None:
        """Unregister owner.

        Args:
            owner: Stable owner identity for the registration.

        Returns:
            None.
        """
        for name in [name for name, (command, _handler) in self._commands.items() if command.owner == owner]:
            del self._commands[name]

    def commands(self, caller: ManagementCaller) -> tuple[ManagementCommand, ...]:
        """Implement the commands operation for the management registry.

        Args:
            caller: The caller value used by the operation.

        Returns:
            The `tuple[ManagementCommand, ...]` result produced by the operation.
        """
        return tuple(
            command
            for command, _handler in sorted(self._commands.values(), key=lambda item: item[0].name)
            if self._allows(caller, command.capability)
        )

    def resolve(self, caller: ManagementCaller, line: str) -> tuple[ManagementCommand, tuple[str, ...]]:
        """Resolve the management registry operation.

        Args:
            caller: The caller value used by the operation.
            line: The line value used by the operation.

        Returns:
            The requested `tuple[ManagementCommand, tuple[str, ...]]` value.
        """
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
        """Determine whether the management registry operation is allowed.

        Args:
            caller: The caller value used by the operation.
            capability: The capability value used by the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `ManagementRegistry._allows`. It delegates to `_authorizer`
            while keeping intermediate state local to the owning operation.
        """
        if caller.kind == "terminal" and caller.id == "local-terminal":
            return capability in caller.capabilities
        return self._authorizer(caller, capability) if self._authorizer is not None else False

    async def execute(self, caller: ManagementCaller, line: str) -> tuple[ManagementCommand, ManagementResult]:
        """Execute one request through the management registry.

        Args:
            caller: The caller value used by the operation.
            line: The line value used by the operation.

        Returns:
            The `tuple[ManagementCommand, ManagementResult]` result produced by the operation.
        """
        command, arguments = self.resolve(caller, line)
        return command, await self._commands[command.name][1](caller, arguments)


class ManagementService(Protocol):
    """Define the structural interface required from a management service."""
    registry: ManagementRegistry


class KernelManagement:
    """Represent the kernel management contract."""
    def __init__(self, app: Any, workspace: str, stop: Callable[[], None]) -> None:
        """Initialize the kernel management.

        Args:
            app: The app value used by the operation.
            workspace: The workspace value used by the operation.
            stop: The stop value used by the operation.

        Returns:
            None.
        """
        self.registry = ManagementRegistry()
        self._app = app
        self._workspace = workspace
        self._stop = stop
        self.operations: OperationLedger | None = None
        self._owns_operations = False
        self._operation_routes: dict[str, ManagementOperationRoute] = {}
        self._register_kernel_commands()

    async def start_operations(self, data_dir: Path) -> None:
        """Start durable command execution after all command providers are registered.

        Args:
            data_dir: Filesystem path for the data.

        Returns:
            None.
        """

        if self.operations is not None:
            return
        ledger = OperationLedger(data_dir / "operations.sqlite3", audit_key=self._audit_key(data_dir))
        self.bind_operations(ledger)
        self._owns_operations = True
        await ledger.start()

    def bind_operations(self, ledger: OperationLedger) -> None:
        """Bind a daemon-owned ledger without starting or closing it.

        Args:
            ledger: The ledger value used by the operation.

        Returns:
            None.
        """

        if self.operations is not None and self.operations is not ledger:
            raise ManagementError("management operation service is already bound")
        if self.operations is ledger:
            return
        self.operations = ledger
        for route in self._operation_routes.values():
            ledger.register(route.definition, self.execute_structured_operation)

    async def close_operations(self) -> None:
        """Close operations.

        Returns:
            None.
        """
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
        """Queue an authorized management command without persisting its raw arguments.

        Args:
            principal: Authenticated principal requesting the operation.
            command_name: The command name value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.
            confirmed: The confirmed value used by the operation.
            idempotency_key: The idempotency key value used by the operation.

        Returns:
            The `OperationRecord` result produced by the operation.
        """

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
                    mutating=command.name not in {("help",), ("status",), ("plugin", "list")},
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
        """Return WebUI-safe operation metadata, without exposing command strings.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `tuple[dict[str, Any], ...]` result produced by the operation.
        """

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
        """Submit a catalogued operation without accepting a raw command line.

        Args:
            principal: Authenticated principal requesting the operation.
            operation_id: Stable identifier for the operation.
            target: Target value or location for the operation.
            input: The input value used by the operation.
            confirmed: The confirmed value used by the operation.
            confirmation_target: The confirmation target value used by the operation.
            idempotency_key: The idempotency key value used by the operation.

        Returns:
            The `OperationRecord` result produced by the operation.
        """

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
        """Execute one validated route for a daemon-owned ledger worker bridge.

        Args:
            principal: Authenticated principal requesting the operation.
            request: Validated request object to process.

        Returns:
            The `str` result produced by the operation.
        """

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
        """Execute operation.

        Args:
            principal: Authenticated principal requesting the operation.
            request: Validated request object to process.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._execute_operation`. It delegates to
            `_command_name`, `get`, `arguments_from_input`, `all` while keeping intermediate state local to
            the owning operation.
        """
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
        """Route is authorized.

        Args:
            principal: Authenticated principal requesting the operation.
            route: The route value used by the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `KernelManagement._route_is_authorized`. It delegates to
            `allows`, `resolve`, `join` while keeping intermediate state local to the owning operation.
        """
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
        """Implement the operation name operation for the kernel management.

        Args:
            command_name: The command name value used by the operation.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._operation_name`. It delegates to `join`
            while keeping intermediate state local to the owning operation.
        """
        return f"management.{'.'.join(command_name)}"

    @staticmethod
    def _command_name(operation_name: str) -> tuple[str, ...]:
        """Implement the command name operation for the kernel management.

        Args:
            operation_name: The operation name value used by the operation.

        Returns:
            The `tuple[str, ...]` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._command_name`. It delegates to
            `startswith`, `split`, `removeprefix`, `any` while keeping intermediate state local to the
            owning operation.
        """
        if not operation_name.startswith("management."):
            raise ManagementError("invalid management operation")
        tokens = tuple(operation_name.removeprefix("management.").split("."))
        if not tokens or any(not token for token in tokens):
            raise ManagementError("invalid management operation")
        return tokens

    @staticmethod
    def _audit_key(data_dir: Path) -> bytes:
        """Implement the audit key operation for the kernel management.

        Args:
            data_dir: Filesystem path for the data.

        Returns:
            The `bytes` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._audit_key`. It delegates to `read_bytes`,
            `token_bytes`, `open`, `fdopen` while keeping intermediate state local to the owning operation.
        """
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
        """Register kernel commands.

        Returns:
            None.

        Notes:
            Internal implementation detail for `KernelManagement._register_kernel_commands`. It delegates to
            `register`, `_register_operation_routes` while keeping intermediate state local to the owning
            operation.
        """
        registrations = (
            (("help",), "List available management commands", self._help, ManagementDanger.NONE),
            (("status",), "Show kernel status", self._status, ManagementDanger.NONE),
            (("plugin", "list"), "List managed plugin generations", self._plugin_list, ManagementDanger.NONE),
            (("plugin", "install"), "Install a managed plugin bundle", self._plugin_install, ManagementDanger.NONE),
            (("plugin", "update"), "Update a managed plugin generation", self._plugin_update, ManagementDanger.NONE),
            (("plugin", "enable"), "Enable a managed plugin bundle", self._plugin_enable, ManagementDanger.NONE),
            (("plugin", "disable"), "Disable a managed plugin bundle", self._plugin_disable, ManagementDanger.NONE),
            (
                ("plugin", "uninstall"),
                "Uninstall a managed plugin bundle",
                self._plugin_uninstall,
                ManagementDanger.CONFIRM,
            ),
            (
                ("plugin", "rollback"),
                "Restore the previous managed plugin generation",
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
        """Register operation routes.

        Returns:
            None.

        Notes:
            Internal implementation detail for `KernelManagement._register_operation_routes`. It delegates
            to `register` while keeping intermediate state local to the owning operation.
        """
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
            """Register the register operation routes operation.

            Args:
                command_name: The command name value used by the operation.
                fields: Structured fields attached to the operation.
                schema: The schema value used by the operation.
                impact: The impact value used by the operation.
                confirmation: The confirmation value used by the operation.
                target_field: The target field value used by the operation.

            Returns:
                None.

            Notes:
                Internal implementation detail for `KernelManagement._register_operation_routes.register`. It
                delegates to `_operation_name`, `command` while keeping intermediate state local to the owning
                operation.
            """
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
        register(
            ("plugin", "install"),
            ("runtime_id", "bundle_id", "source_id", "expected_index_digest"),
            {
                "properties": {
                    **runtime_id,
                    **bundle_id,
                    **source_id,
                    "expected_index_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                },
                "required": ["runtime_id", "bundle_id"],
                "allOf": [
                    {
                        "if": {"required": ["expected_index_digest"]},
                        "then": {"required": ["source_id"]},
                    }
                ],
            },
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
        register(
            ("plugin", "uninstall"),
            ("runtime_id", "bundle_id"),
            {"properties": {**runtime_id, **bundle_id}, "required": ["runtime_id", "bundle_id"]},
            impact=OperationImpact.HIGH,
            confirmation=OperationConfirmation.TARGET,
        )
        register(
            ("plugin", "gc"),
            ("runtime_id",),
            {"properties": runtime_id, "required": []},
            impact=OperationImpact.HIGH,
            confirmation=OperationConfirmation.EXPLICIT,
            target_field=None,
        )

    async def _help(self, caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Implement the help operation for the kernel management.

        Args:
            caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._help`. It delegates to `join`, `commands`
            while keeping intermediate state local to the owning operation.
        """
        if arguments:
            raise ManagementError("usage: help")
        text = "\n".join(
            f"{' '.join(command.name)} - {command.summary}" for command in self.registry.commands(caller)
        )
        return ManagementResult(text)

    async def _status(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Return the status of the kernel management operation.

        Args:
            _caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._status`. It delegates to `status` while
            keeping intermediate state local to the owning operation.
        """
        if arguments:
            raise ManagementError("usage: status")
        return ManagementResult(str(self._app.status()), self._app.status())

    def _target(self, target_id: str) -> Any:
        """Resolve one configured managed-plugin target.

        Args:
            target_id: Stable broker bridge identifier.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._target`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        try:
            return self._app.settings.broker.bridges[target_id]
        except KeyError as error:
            raise ManagementError(f"managed plugin target is not configured: {target_id}") from error

    async def _plugin_list(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Implement the plugin list operation for the kernel management.

        Args:
            _caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._plugin_list`. It delegates to
            `list_generations`, `join` while keeping intermediate state local to the owning operation.
        """
        if len(arguments) > 1:
            raise ManagementError("usage: plugin list [runtime-id]")
        store = RuntimeGenerationStore(self._workspace)
        records = store.list_generations(arguments[0] if arguments else None)
        text = "\n".join(f"{item.runtime_id}\t{item.id}\t{','.join(item.roots)}" for item in records)
        return ManagementResult(text or "no runtime plugin generations")

    async def _plugin_install(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Implement the plugin install operation for the kernel management.

        Args:
            _caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._plugin_install`. It delegates to
            `_target`, `install` while keeping intermediate state local to the owning operation.
        """
        if len(arguments) not in (2, 3, 4):
            raise ManagementError("usage: plugin install <runtime-id> <bundle-id> [source-id] [index-digest]")
        runtime = self._target(arguments[0])
        result = PluginInstallationService(self._workspace).install(
            arguments[1],
            runtime_id=arguments[0],
            runtime_kind=runtime.kind,
            source_id=arguments[2] if len(arguments) == 3 else None,
            expected_index_digest=arguments[3] if len(arguments) == 4 else None,
        )
        return ManagementResult(f"installed {arguments[1]} as {result.generation.id}")

    async def _plugin_update(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Implement the plugin update operation for the kernel management.

        Args:
            _caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._plugin_update`. It delegates to
            `_target`, `update` while keeping intermediate state local to the owning operation.
        """
        if len(arguments) not in (1, 2):
            raise ManagementError("usage: plugin update <runtime-id> [source-id]")
        runtime = self._target(arguments[0])
        result = PluginInstallationService(self._workspace).update(
            runtime_id=arguments[0],
            runtime_kind=runtime.kind,
            source_id=arguments[1] if len(arguments) == 2 else None,
        )
        return ManagementResult(f"updated {arguments[0]} as {result.generation.id}")

    async def _plugin_enable(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Implement the plugin enable operation for the kernel management.

        Args:
            _caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._plugin_enable`. It delegates to
            `_change_plugin` while keeping intermediate state local to the owning operation.
        """
        return await self._change_plugin("enable", arguments)

    async def _plugin_disable(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Implement the plugin disable operation for the kernel management.

        Args:
            _caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._plugin_disable`. It delegates to
            `_change_plugin` while keeping intermediate state local to the owning operation.
        """
        return await self._change_plugin("disable", arguments)

    async def _change_plugin(self, operation: str, arguments: tuple[str, ...]) -> ManagementResult:
        """Implement the change plugin operation for the kernel management.

        Args:
            operation: The operation value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._change_plugin`. It delegates to
            `_target`, `getattr` while keeping intermediate state local to the owning operation.
        """
        if len(arguments) != 2:
            raise ManagementError(f"usage: plugin {operation} <runtime-id> <bundle-id>")
        runtime = self._target(arguments[0])
        service = PluginInstallationService(self._workspace)
        result = getattr(service, operation)(arguments[1], runtime_id=arguments[0], runtime_kind=runtime.kind)
        return ManagementResult(f"{operation}d {arguments[1]} as {result.generation.id}")

    async def _plugin_uninstall(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Implement the plugin uninstall operation for the kernel management.

        Args:
            _caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._plugin_uninstall`. It delegates to
            `_target`, `uninstall` while keeping intermediate state local to the owning operation.
        """
        if len(arguments) != 2:
            raise ManagementError("usage: plugin uninstall <runtime-id> <bundle-id>")
        runtime = self._target(arguments[0])
        result = PluginInstallationService(self._workspace).uninstall(
            arguments[1], runtime_id=arguments[0], runtime_kind=runtime.kind
        )
        generation = result.generation.id if result.generation else "deactivated"
        return ManagementResult(f"uninstalled {arguments[1]}; {generation}")

    async def _plugin_rollback(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Implement the plugin rollback operation for the kernel management.

        Args:
            _caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._plugin_rollback`. It delegates to
            `rollback` while keeping intermediate state local to the owning operation.
        """
        if len(arguments) != 1:
            raise ManagementError("usage: plugin rollback <runtime-id>")
        deployment = RuntimeGenerationStore(self._workspace).rollback(arguments[0])
        return ManagementResult(f"activated {deployment.runtime_generations[arguments[0]]}")

    async def _plugin_gc(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Implement the plugin gc operation for the kernel management.

        Args:
            _caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._plugin_gc`. It delegates to `collect`
            while keeping intermediate state local to the owning operation.
        """
        if len(arguments) > 1:
            raise ManagementError("usage: plugin gc [runtime-id]")
        collected = RuntimeGenerationStore(self._workspace).collect(arguments[0] if arguments else None)
        return ManagementResult(f"collected {len(collected)} runtime plugin generation(s)")

    async def _stop_command(self, _caller: ManagementCaller, arguments: tuple[str, ...]) -> ManagementResult:
        """Stop command.

        Args:
            _caller: The caller value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `ManagementResult` result produced by the operation.

        Notes:
            Internal implementation detail for `KernelManagement._stop_command`. It delegates to `_stop`
            while keeping intermediate state local to the owning operation.
        """
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
