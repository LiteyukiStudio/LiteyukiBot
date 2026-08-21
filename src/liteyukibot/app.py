"""LiteyukiBot v7 application lifecycle."""

from __future__ import annotations

import asyncio
import math
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from time import monotonic
from types import MappingProxyType
from typing import Any, cast
from uuid import uuid4

from jsonschema import Draft202012Validator, ValidationError

from ._version import __version__
from .agents import AGENT_HISTORY_SERVICE
from .authorization import AuthorizationContext
from .broker import (
    AuthorizationContextWire,
    BridgeControlInvoke,
    BrokerToolDeclaration,
    ControlOutcome,
    KernelBrokerPeer,
    ToolInvoke,
    ToolOutcome,
    configured_kernel_bridge,
)
from .capabilities import ADAPTER_CALL_API, AGENT_HISTORY_CLEAR, PERMISSION_SERVICE_MAJOR, PERMISSION_SERVICE_NAME
from .config import AppSettings, RuntimeEventRoute
from .control import ControlServer
from .cordis_host import CordisHost, discover_cordis_host, validate_extension_topology
from .events import ActionEnvelope, ActionResult, CallApi, EventBus, EventEnvelope, HandlerResult, Subscription
from .events.models import JsonValue as EventJsonValue
from .functions import (
    AGENT_FUNCTION_CATALOG,
    AGENT_PROMPT_CATALOG,
    AGENT_PROMPT_SELECT,
    FUNCTION_DISPATCH_SERVICE,
    FunctionDispatcher,
    FunctionEventContribution,
    FunctionHost,
    FunctionHostBindings,
    FunctionHostProvider,
    FunctionPackSource,
    FunctionPreflight,
    FunctionPromptPreset,
    discover_function_host_provider,
)
from .http import HttpServer
from .i18n import I18N_SERVICE, SUPPORTED_LOCALES, Translator, normalize_locale
from .instance_daemon import INSTANCE_DAEMON_SERVICE, InstanceDaemonService
from .logging import Logger, configure_logging, get_logger, log_payload, shutdown_logging
from .management import (
    MANAGEMENT_ADMIN,
    MANAGEMENT_SERVICE,
    KernelManagement,
    ManagementCaller,
    ManagementDanger,
    ManagementError,
)
from .operations import ManagementPrincipal, OperationRequest, PrincipalKind
from .plugin_store import RuntimeGenerationStore
from .plugins import ExtensionManifest, PluginDefinition, PluginManager, ToolCallback, ToolDeclaration
from .resource_packs import RESOURCE_CATALOG_SERVICE, ResourceCatalog, ResourcePackDeclaration
from .runtime import (
    ActionProvenance,
    ActionSinkResult,
    JsonValue,
    RuntimeCatalog,
    RuntimeSpec,
    RuntimeSupervisor,
    json_value,
)
from .runtime_api import (
    RuntimeApiError,
    RuntimeBinding,
    RuntimeCallContext,
    RuntimeContextFactory,
    RuntimeNamespaceProxy,
    RuntimeRequirement,
    RuntimeUnavailable,
    create_runtime_proxy,
)
from .services import ServiceKey, ServiceRegistry
from .status import KERNEL_STATUS_SERVICE, KernelStatusSnapshot
from .tasks import ManagedTasks


class AppState(StrEnum):
    CREATED = "created"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class ActionService:
    """Route protocol-neutral actions to the runtime that owns the bot."""

    def __init__(
        self,
        supervisor: RuntimeSupervisor,
        action_guard: Callable[[EventEnvelope | None, ActionEnvelope], ActionResult | None],
    ) -> None:
        self._supervisor = supervisor
        self._action_guard = action_guard

    async def execute(self, action: ActionEnvelope, *, event: EventEnvelope | None = None) -> ActionResult:
        guarded = self._action_guard(event, action)
        if guarded is not None:
            return guarded
        try:
            response = await self._supervisor.execute_action(
                action.runtime_id,
                action.action_id,
                action.model_dump(mode="json"),
            )
        except (KeyError, ConnectionError, RuntimeError, TimeoutError) as error:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="RUNTIME_UNAVAILABLE",
                error_message=str(error),
            )
        if response.ok:
            return ActionResult.model_validate(
                {
                    "action_id": action.action_id,
                    "success": True,
                    "data": response.data,
                }
            )
        return ActionResult(
            action_id=action.action_id,
            success=False,
            error_code="RUNTIME_ACTION_FAILED",
            error_message=response.error or "runtime rejected the action",
        )


_PERMISSION_SERVICE = ServiceKey(PERMISSION_SERVICE_NAME, PERMISSION_SERVICE_MAJOR)
_LEGACY_PERMISSION_SERVICE = ServiceKey(PERMISSION_SERVICE_NAME, 1)


def _permission_service(services: ServiceRegistry) -> object | None:
    """Use v2 for new hosts; retain v1 only for legacy runtime action paths."""

    return cast(object | None, services.get(_PERMISSION_SERVICE) or services.get(_LEGACY_PERMISSION_SERVICE))


class _AppStatusProvider:
    def __init__(self, app: LiteyukiApp) -> None:
        self._app = app

    def snapshot(self) -> KernelStatusSnapshot:
        return self._app.status_snapshot()


class _AgentHistoryProvider:
    def __init__(self, app: LiteyukiApp) -> None:
        self._app = app

    async def clear(self, event: EventEnvelope) -> int:
        return await self._app._clear_agent_history(event)


class _ApplicationRuntimeApiBackend:
    """Authorize and route one plugin runtime call through the active broker lease."""

    def __init__(self, app: LiteyukiApp) -> None:
        self._app = app

    async def invoke(
        self,
        binding: RuntimeBinding,
        operation: str,
        arguments: Mapping[str, EventJsonValue],
        context: RuntimeCallContext,
    ) -> EventJsonValue:
        requirement = self._app._find_runtime_requirement(context.extension_id, binding)
        if requirement is None:
            raise RuntimeApiError(
                binding.runtime,
                binding.api,
                operation,
                "RUNTIME_API_NOT_DECLARED",
            )
        if operation not in requirement.operations:
            raise RuntimeApiError(
                binding.runtime,
                binding.api,
                operation,
                "RUNTIME_API_OPERATION_NOT_DECLARED",
            )
        permissions = _permission_service(self._app.services)
        allows_extension = getattr(permissions, "allows_extension", None)
        capability = f"runtime.{binding.runtime}.{binding.api}.{operation}"
        if not callable(allows_extension) or not allows_extension(
            context.authorization,
            context.extension_id,
            capability,
            full=False,
        ):
            raise RuntimeApiError(binding.runtime, binding.api, operation, "RUNTIME_API_PERMISSION_DENIED")
        peer = self._app._kernel_broker_peer
        if peer is None:
            raise RuntimeUnavailable(binding.runtime, binding.api, "kernel broker is unavailable")
        response = await peer.request_runtime_api(
            context.event,
            correlation_id=str(uuid4()),
            runtime_kind=binding.runtime,
            version=binding.version,
            api_id=f"{binding.api}.{operation}",
            caller_extension_id=context.extension_id,
            authorization=AuthorizationContextWire(
                event_id=context.authorization.event_id,
                runtime_id=context.authorization.runtime_id,
                bot_id=context.authorization.bot_id,
                actor_id=context.authorization.actor_id,
            ),
            arguments=arguments,
            bridge_id=binding.bridge_id,
            timeout_seconds=self._app.settings.broker.delivery_timeout_seconds,
        )
        if response is None:
            raise RuntimeUnavailable(binding.runtime, binding.api, "no active broker delivery")
        if not response.success:
            raise RuntimeApiError(
                binding.runtime,
                binding.api,
                operation,
                response.error_code or "RUNTIME_API_FAILED",
                response.error_details,
            )
        return response.result


class LiteyukiApp:
    """Own all v7 services and enforce deterministic startup and shutdown."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        logger: Logger | None = None,
        runtime_secrets: Mapping[str, str] | None = None,
        resource_workspace: str | None = None,
    ) -> None:
        self.settings = settings
        self.resource_workspace = resource_workspace or "."
        self.logger = logger or get_logger(component="core")
        self.state = AppState.CREATED
        self.services = ServiceRegistry()
        self.runtimes = RuntimeSupervisor(
            logger=self.logger,
            event_sink=self._ingest_runtime_event,
            action_sink=self._execute_runtime_action,
            secret_values=runtime_secrets,
            lyip_settings=settings.lyip,
        )
        self.runtimes.set_logging_settings(settings.logging)
        self.runtimes.set_management_sink(self._execute_runtime_management)
        self.actions = ActionService(self.runtimes, self._authorize_action)
        core = settings.core
        self.events = EventBus(
            queue_capacity=core.queue_capacity,
            enqueue_timeout=core.enqueue_timeout_seconds,
            handler_timeout=core.handler_timeout_seconds,
            max_concurrent_events=core.max_concurrent_events,
            action_executor=self._execute_event_action,
            logger=self.logger,
        )
        self._kernel_broker_peer: KernelBrokerPeer | None = None
        self._cordis_host: CordisHost | None = None
        self._configured_kernel_bridge = configured_kernel_bridge(settings)
        self._runtime_targets = {
            bridge_id: bridge.kind
            for bridge_id, bridge in settings.broker.bridges.items()
            if bridge.kind != "kernel"
        }
        self._runtime_manifests: dict[str, ExtensionManifest] = {}
        self._runtime_backend = _ApplicationRuntimeApiBackend(self)
        self._runtime_secrets = dict(runtime_secrets or {})
        self.plugins = PluginManager(
            services=self.services,
            events=self.events,
            actions=self.actions,
            logger=self.logger,
            data_dir=core.data_dir,
            cache_dir=core.cache_dir,
            runtime_context_factory=self._runtime_context_factory,
            runtime_resolver=self._resolve_runtime_proxy,
            runtime_targets=self._runtime_targets,
        )
        self.management = KernelManagement(self, self.resource_workspace, self._request_stop)
        self.control = ControlServer(
            core.data_dir / "control.json",
            status_provider=self.status,
            runtime_restarter=self.runtimes.restart,
            handlers={
                "event.inject": self._inject_event,
                "management.execute": self._execute_local_management,
                "topology": self._control_topology,
                "daemon.webui.snapshot": self._daemon_webui_snapshot,
                "daemon.webui.presentation": self._daemon_webui_presentation,
                "daemon.webui.operation_catalog": self._daemon_webui_operation_catalog,
                "daemon.webui.operation.execute": self._daemon_webui_execute_operation,
                "daemon.webui.plugin_surfaces": self._daemon_webui_plugin_surfaces,
            },
        )
        self.http = (
            HttpServer(settings.http.host, settings.http.port, status_provider=self.status)
            if settings.http.enabled
            else None
        )
        self._accepting_events = False
        self._stop_callback: Callable[[], None] | None = None
        self._logging_owned = logger is None
        self._logging_started = False
        self._plugins_setup = False
        self._runtimes_started = False
        self._kernel_broker_started = False
        self._management_started = False
        self._control_started = False
        self._http_started = False
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        self._runtime_state_directories: dict[str, Any] = {}
        self.resources: ResourceCatalog | None = None
        self.translator: Translator | None = None
        self.functions: FunctionDispatcher | None = None
        self._function_host_provider: FunctionHostProvider | None = None
        self._function_preflights: dict[str, FunctionPreflight] = {}
        self._function_hosts: dict[str, FunctionHost] = {}
        self._function_host_tasks: dict[str, ManagedTasks] = {}
        self._function_tool_callbacks: dict[str, ToolCallback] = {}
        self._function_event_callbacks: dict[
            tuple[str, str], Callable[[EventEnvelope], Awaitable[HandlerResult | None]]
        ] = {}
        self._function_subscriptions: list[Subscription] = []
        self._function_prompts: dict[str, FunctionPromptPreset] = {}
        self._function_tasks = ManagedTasks("functions", on_failure=self._function_task_failed)
        runtime_plugins = RuntimeCatalog().discover()
        generation_store = RuntimeGenerationStore(self.resource_workspace)
        deployment = generation_store.active()
        for runtime_id, runtime in settings.runtimes.items():
            if not runtime.enabled:
                continue
            state_directory = (core.data_dir / "runtimes" / runtime_id).resolve()
            self._runtime_state_directories[runtime_id] = state_directory
            generation_path: Path | None = None
            command = runtime.command or None
            generation_id = deployment.runtime_generations.get(runtime_id)
            if generation_id is not None:
                generation = generation_store.read(runtime_id, generation_id)
                if generation.runtime_kind != runtime.kind:
                    raise RuntimeError(
                        f"runtime {runtime_id!r} generation kind {generation.runtime_kind!r} "
                        f"does not match {runtime.kind!r}"
                    )
                runtime_plugin = runtime_plugins.get(runtime.kind)
                if runtime_plugin is None:
                    raise RuntimeError(f"runtime {runtime.kind!r} has a managed generation but is not installed")
                if runtime.command:
                    raise RuntimeError(
                        f"runtime {runtime_id!r} cannot combine a managed generation with command override"
                    )
                generation_path = generation_store.path_for(runtime_id, generation_id)
                python = generation_store.python_path(generation_path)
                if not python.is_file():
                    raise RuntimeError(f"runtime {runtime_id!r} generation has no Python executable")
                command = (str(python), *runtime_plugin.command[1:])
            self.runtimes.add(
                RuntimeSpec(
                    id=runtime_id,
                    kind=runtime.kind,
                    options=runtime.options,
                    command=command,
                    working_directory=runtime.working_directory,
                    env={
                        **runtime.env,
                        "LITEYUKI_RUNTIME_STATE_DIR": str(state_directory),
                        **({"LITEYUKI_RUNTIME_GENERATION_DIR": str(generation_path)} if generation_path else {}),
                    },
                    secret_env=runtime.secret_env,
                    handshake_timeout=runtime.handshake_timeout_seconds,
                    restart_limit=runtime.max_failures,
                    restart_window=runtime.failure_window_seconds,
                    ready_timeout=runtime.ready_timeout_seconds,
                    heartbeat_interval=runtime.heartbeat_interval_seconds,
                    stale_after=runtime.stale_after_seconds,
                    max_inbound_events=runtime.max_inbound_events,
                )
            )
        self._runtime_event_routes = self._event_routes(settings)
        if self._runtime_event_routes:
            self.events.subscribe(
                self._forward_runtime_event,
                name="runtime.routes",
            )
        self.services.provide(
            KERNEL_STATUS_SERVICE,
            _AppStatusProvider(self),
            provider="liteyukibot.kernel",
        )
        if any(bridge.kind == "agent" for bridge in settings.broker.bridges.values()):
            self.services.provide(
                AGENT_HISTORY_SERVICE,
                _AgentHistoryProvider(self),
                provider="liteyukibot.kernel",
            )
        self.services.provide(MANAGEMENT_SERVICE, self.management, provider="liteyukibot.kernel")
        if (instance_daemon := InstanceDaemonService.from_environment()) is not None:
            self.services.provide(
                INSTANCE_DAEMON_SERVICE,
                instance_daemon,
                provider="liteyukibot.kernel",
            )

    def set_stop_callback(self, callback: Callable[[], None]) -> None:
        """Bind the host-owned shutdown signal used by the management console."""

        self._stop_callback = callback

    def _find_runtime_requirement(
        self, extension_id: str, binding: RuntimeBinding
    ) -> RuntimeRequirement | None:
        manifest = self._runtime_manifests.get(extension_id)
        if manifest is None:
            loaded = self.plugins.loaded.get(extension_id)
            manifest = None if loaded is None else loaded.definition.manifest
        if manifest is None:
            return None
        candidates = [
            requirement
            for requirement in manifest.runtime_requirements
            if requirement.runtime == binding.runtime
            and requirement.api == binding.api
            and requirement.version == binding.version
            and requirement.optional == binding.optional
            and (requirement.bridge_id is None or binding.bridge_id in (None, requirement.bridge_id))
        ]
        if binding.bridge_id is not None:
            exact = [item for item in candidates if item.bridge_id == binding.bridge_id]
            candidates = exact or [item for item in candidates if item.bridge_id is None]
        if len(candidates) != 1:
            return None
        return candidates[0]

    def _resolve_runtime_proxy(self, binding: RuntimeBinding, context: RuntimeCallContext) -> RuntimeNamespaceProxy:
        requirement = self._find_runtime_requirement(context.extension_id, binding)
        if requirement is None:
            return create_runtime_proxy(binding, None, context, reason="runtime API is not declared")
        effective_binding = binding
        if binding.bridge_id is None and requirement.bridge_id is not None:
            effective_binding = replace(binding, bridge_id=requirement.bridge_id)
        targets = tuple(
            bridge_id
            for bridge_id, kind in self._runtime_targets.items()
            if kind == effective_binding.runtime
            and (effective_binding.bridge_id is None or bridge_id == effective_binding.bridge_id)
        )
        if len(targets) != 1:
            reason = "runtime bridge is not configured" if not targets else "runtime bridge is ambiguous"
            return create_runtime_proxy(effective_binding, None, context, reason=reason)
        return create_runtime_proxy(effective_binding, self._runtime_backend, context)

    def _runtime_context_factory(self, extension_id: str) -> RuntimeContextFactory:
        def create(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> RuntimeCallContext:
            values = (*args, *kwargs.values())
            event: EventEnvelope | None = None
            authorization: AuthorizationContext | None = None
            for value in values:
                if isinstance(value, EventEnvelope):
                    event = value
                elif isinstance(value, AuthorizationContext):
                    authorization = value
                else:
                    envelope = getattr(value, "envelope", None)
                    if isinstance(envelope, EventEnvelope):
                        event = envelope
                    wrapped_event = getattr(value, "event", None)
                    envelope = getattr(wrapped_event, "envelope", None)
                    if isinstance(envelope, EventEnvelope):
                        event = envelope
            if event is None and authorization is not None and self._kernel_broker_peer is not None:
                event = self._kernel_broker_peer.active_event(authorization.event_id)
            if event is None:
                raise RuntimeError("runtime API calls require an active broker event")
            if authorization is None:
                authorization = AuthorizationContext(
                    event_id=event.id,
                    runtime_id=event.runtime_id,
                    bot_id=event.bot_id,
                    actor_id=None if event.actor is None else event.actor.id,
                )
            elif (
                authorization.event_id != event.id
                or authorization.runtime_id != event.runtime_id
                or authorization.bot_id != event.bot_id
            ):
                raise RuntimeError("runtime API authorization does not match the active event")
            return RuntimeCallContext(extension_id=extension_id, event=event, authorization=authorization)

        return create

    def _request_stop(self) -> None:
        if self._stop_callback is None:
            raise RuntimeError("application host does not support management shutdown")
        self._stop_callback()

    async def _inject_event(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not self.settings.development.enabled:
            raise PermissionError("development controls are disabled")
        raw_event = request.get("event")
        if not isinstance(raw_event, Mapping):
            raise ValueError("event.inject requires an event object")
        event = EventEnvelope.model_validate(raw_event)
        result = await self.events.publish(event)
        return result.model_dump(mode="json")

    async def _execute_local_management(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not self.settings.development.enabled:
            raise PermissionError("development controls are disabled")
        line = request.get("line")
        if not isinstance(line, str) or not line.strip():
            raise ValueError("management.execute requires a non-empty command line")
        caller = ManagementCaller.local_terminal()
        command, _arguments = self.management.registry.resolve(caller, line)
        if command.danger is ManagementDanger.CONFIRM and request.get("confirmed") is not True:
            raise PermissionError(f"management command requires confirmation: {' '.join(command.name)}")
        _command, result = await self.management.registry.execute(caller, line)
        return {"text": result.text, "data": result.data}

    async def _control_topology(self, _request: Mapping[str, Any]) -> dict[str, object]:
        if not self.settings.development.enabled:
            raise PermissionError("development controls are disabled")
        return self.topology()

    @staticmethod
    def _daemon_webui_principal() -> ManagementPrincipal:
        """The daemon control descriptor is the sole authority for this worker bridge."""

        return ManagementPrincipal(
            PrincipalKind.SYSTEM,
            "daemon-webui",
            "daemon-control",
            None,
            frozenset({MANAGEMENT_ADMIN}),
        )

    async def _daemon_webui_snapshot(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": self.status(),
            "topology": self.topology(),
            "webui_generation": self.plugins.webui_generation,
        }

    async def _daemon_webui_presentation(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self.translator is None:
            raise RuntimeError("WebUI presentation is unavailable before resource initialization")
        requested = request.get("locale")
        locale = normalize_locale(requested) if isinstance(requested, str) else self.translator.locale
        if locale not in SUPPORTED_LOCALES:
            locale = self.translator.locale
        keys = sorted(
            {key for catalog in self.translator.catalogs.values() for key in catalog if key.startswith("webui.")}
        )
        return {
            "locale": locale,
            "locales": list(SUPPORTED_LOCALES),
            "messages": {key: self.translator.text_for(locale, key) for key in keys},
        }

    async def _daemon_webui_operation_catalog(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        return {"operations": list(self.management.operation_catalog(self._daemon_webui_principal()))}

    async def _daemon_webui_execute_operation(self, request: Mapping[str, Any]) -> dict[str, str]:
        operation_id = request.get("operation_id")
        target = request.get("target")
        input_value = request.get("input")
        idempotency_key = request.get("idempotency_key")
        confirmation_target = request.get("confirmation_target")
        if (
            not isinstance(operation_id, str)
            or not isinstance(target, str)
            or not isinstance(input_value, Mapping)
            or not isinstance(idempotency_key, str)
            or confirmation_target is not None
            and not isinstance(confirmation_target, str)
        ):
            raise ValueError("invalid daemon WebUI operation request")
        result = await self.management.execute_structured_operation(
            self._daemon_webui_principal(),
            OperationRequest(
                operation=operation_id,
                target=target,
                input=input_value,
                idempotency_key=idempotency_key,
                confirmed=request.get("confirmed") is True,
                confirmation_target=confirmation_target,
            ),
        )
        return {"result_code": result}

    async def _daemon_webui_plugin_surfaces(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        surfaces = [
            {"plugin_id": plugin_id, "surface": surface.model_dump(mode="json")}
            for plugin_id, surface in self.plugins.webui_surfaces()
        ]
        diagnostics = [{"plugin_id": item.plugin_id, "code": item.code} for item in self.plugins.webui_diagnostics]
        return {"generation": self.plugins.webui_generation, "surfaces": surfaces, "diagnostics": diagnostics}

    def _function_sources(
        self,
        extension_id: str,
        declarations: tuple[ResourcePackDeclaration, ...],
    ) -> tuple[FunctionPackSource, ...]:
        if self.resources is None:
            raise RuntimeError("Function resources are unavailable before ResourceCatalog startup")
        sources: list[FunctionPackSource] = []
        for declaration in declarations:
            pack = self.resources.pack_for_declaration(declaration)
            files = {
                resource.path.removeprefix("functions/"): resource.read_bytes()
                for resource in self.resources.pack_files(pack.metadata.id, "functions")
                if resource.path.startswith("functions/")
            }
            if files:
                sources.append(FunctionPackSource(extension_id, pack.metadata.id, files))
        return tuple(sources)

    def _preflight_functions(self, definitions: Mapping[str, PluginDefinition]) -> None:
        source_map: dict[str, tuple[FunctionPackSource, ...]] = {
            extension_id: self._function_sources(
                extension_id,
                tuple(definition.manifest.resource_packs),
            )
            for extension_id, definition in definitions.items()
        }
        if self._cordis_host is not None:
            function_resource_packs = getattr(self._cordis_host, "function_resource_packs", {})
            for extension_id, declarations in function_resource_packs.items():
                source_map[extension_id] = self._function_sources(extension_id, declarations)

        provider = self._function_host_provider
        if provider is None:
            if any(source_map.values()):
                raise RuntimeError("Function resources are installed but no Alpha 7 Function Host is available")
            return

        seen_tools: set[str] = set()
        seen_prompts: set[str] = set()
        for extension_id, sources in sorted(source_map.items()):
            if not sources:
                continue
            preflight = provider.preflight(sources)
            if not isinstance(preflight, FunctionPreflight) or preflight.extension_id != extension_id:
                raise RuntimeError(f"Function Host returned an invalid preflight for extension {extension_id!r}")
            for declaration in preflight.tool_declarations:
                if declaration.id in seen_tools:
                    raise RuntimeError(f"duplicate LYF Tool declaration: {declaration.id}")
                seen_tools.add(declaration.id)
            for prompt in preflight.prompts:
                if prompt.id in seen_prompts:
                    raise RuntimeError(f"duplicate LYF prompt preset: {prompt.id}")
                seen_prompts.add(prompt.id)
            if len(preflight.prompts) > 64 or len(preflight.events) > 128:
                raise RuntimeError(f"extension {extension_id!r} exceeds Alpha 7 Function contribution limits")
            self._function_preflights[extension_id] = preflight
            self._function_prompts.update({prompt.id: prompt for prompt in preflight.prompts})

    def _create_function_hosts(self, configs: Mapping[str, Mapping[str, Any]]) -> None:
        provider = self._function_host_provider
        if provider is None:
            return
        for extension_id, preflight in sorted(self._function_preflights.items()):
            tasks = ManagedTasks(f"functions:{extension_id}", on_failure=self._function_task_failed)
            registered_tools: dict[str, ToolCallback] = {}
            registered_events: dict[str, Callable[[EventEnvelope], Awaitable[HandlerResult | None]]] = {}

            def register_tool(
                declaration: ToolDeclaration,
                callback: ToolCallback,
                *,
                extension_id: str = extension_id,
                preflight: FunctionPreflight = preflight,
                registered_tools: dict[str, ToolCallback] = registered_tools,
            ) -> None:
                expected = {item.id for item in preflight.tool_declarations}
                if declaration.id not in expected or not declaration.id.startswith(f"{extension_id}.lyf."):
                    raise RuntimeError(f"Function Host registered an undeclared Tool: {declaration.id}")
                if declaration.id in registered_tools:
                    raise RuntimeError(f"Function Host registered Tool more than once: {declaration.id}")
                registered_tools[declaration.id] = callback

            def register_event(
                contribution: FunctionEventContribution,
                callback: Callable[[EventEnvelope], Awaitable[HandlerResult | None]],
                *,
                extension_id: str = extension_id,
                preflight: FunctionPreflight = preflight,
                registered_events: dict[
                    str, Callable[[EventEnvelope], Awaitable[HandlerResult | None]]
                ] = registered_events,
            ) -> None:
                expected = {item.function_id for item in preflight.events}
                if contribution.extension_id != extension_id or contribution.function_id not in expected:
                    raise RuntimeError(f"Function Host registered an undeclared event: {contribution.function_id}")
                if contribution.function_id in registered_events:
                    raise RuntimeError(f"Function Host registered event more than once: {contribution.function_id}")
                registered_events[contribution.function_id] = callback

            def emit_log(message: str, *, extension_id: str = extension_id) -> None:
                self.logger.bind(extension=extension_id, component="functions").info("{}", message)

            bindings = FunctionHostBindings(
                extension_id=extension_id,
                config=MappingProxyType(dict(configs.get(extension_id, {}))),
                events=self.events,
                services=self.services,
                tasks=tasks,
                logger=self.logger.bind(extension=extension_id, component="functions"),
                register_tool=register_tool,
                register_event=register_event,
                emit_log=emit_log,
                select_prompt=self._select_function_prompt,
                resolve_event=(
                    lambda event_id: self._kernel_broker_peer.active_event(event_id)
                    if self._kernel_broker_peer is not None
                    else None
                ),
            )
            host = provider.create_host(preflight, bindings)
            if not callable(getattr(host, "invoke", None)) or not callable(getattr(host, "aclose", None)):
                raise RuntimeError(f"Function Host for extension {extension_id!r} has an invalid runtime contract")
            self._function_tool_callbacks.update(registered_tools)
            self._function_host_tasks[extension_id] = tasks
            self._function_hosts[extension_id] = host
            for contribution in preflight.events:
                callback = registered_events.get(contribution.function_id)

                async def handle_event(
                    event: EventEnvelope,
                    *,
                    contribution: FunctionEventContribution = contribution,
                    callback: Callable[[EventEnvelope], Awaitable[HandlerResult | None]] | None = callback,
                    host: FunctionHost = host,
                ) -> HandlerResult | None:
                    if not self._function_event_matches(event, contribution):
                        return None
                    result = await callback(event) if callback is not None else await host.invoke(
                        contribution.function_id,
                        event=event,
                    )
                    return result if isinstance(result, HandlerResult) else None

                self._function_subscriptions.append(
                    self.events.subscribe(
                        handle_event,
                        name=f"function:{extension_id}:{contribution.function_id}",
                    )
                )

    @staticmethod
    def _function_event_matches(event: EventEnvelope, contribution: FunctionEventContribution) -> bool:
        if contribution.topics and not any(
            topic == event.type or topic == "*" or topic.endswith(".*") and event.type.startswith(topic[:-1])
            for topic in contribution.topics
        ):
            return False
        projection: object = event.model_dump(mode="json")
        for path, expected in contribution.filters.items():
            value = projection
            for part in path.split("."):
                if not isinstance(value, Mapping) or part not in value:
                    return False
                value = value[part]
            if value != expected:
                return False
        return True

    async def _select_function_prompt(self, event: EventEnvelope, preset_id: str) -> Any:
        if preset_id not in self._function_prompts:
            raise ValueError("unknown prompt preset")
        peer = self._kernel_broker_peer
        if peer is None:
            raise ConnectionError("Agent bridge is unavailable")
        authorization = AuthorizationContextWire(
            event_id=event.id,
            runtime_id=event.runtime_id,
            bot_id=event.bot_id,
            actor_id=event.actor.id if event.actor is not None else None,
        )
        response = await peer.request_control(
            event,
            correlation_id=f"function-prompt:{event.id}:{uuid4()}",
            command=AGENT_PROMPT_SELECT,
            authorization=authorization,
            payload={"preset_id": preset_id},
            timeout_seconds=self.settings.broker.delivery_timeout_seconds,
        )
        if response is None or not response.success:
            raise RuntimeError(response.error_code if response is not None else "prompt selection unavailable")
        return response.result

    async def _handle_prompt_catalog(self, request: BridgeControlInvoke) -> ControlOutcome:
        peer = self._kernel_broker_peer
        if peer is None or peer.active_event(request.authorization.event_id) is None:
            return ControlOutcome(success=False, error_code="CONTROL_STALE_DELIVERY")
        if request.payload:
            return ControlOutcome(success=False, error_code="CONTROL_INVALID_PAYLOAD")
        prompts = self._function_prompt_catalog()
        return ControlOutcome(success=True, result=cast(EventJsonValue, {"prompts": prompts}))

    async def _handle_function_catalog(self, request: BridgeControlInvoke) -> ControlOutcome:
        peer = self._kernel_broker_peer
        if peer is None or peer.active_event(request.authorization.event_id) is None:
            return ControlOutcome(success=False, error_code="CONTROL_STALE_DELIVERY")
        if request.payload:
            return ControlOutcome(success=False, error_code="CONTROL_INVALID_PAYLOAD")
        tools = [
            {
                "id": declaration.id,
                "title": declaration.id.rsplit(".", 1)[-1],
                "module_id": extension_id,
                "description": declaration.description,
                "input_schema": dict(declaration.input_schema),
                "required_capabilities": list(declaration.capabilities),
            }
            for extension_id, preflight in sorted(self._function_preflights.items())
            for declaration in preflight.tool_declarations
        ]
        return ControlOutcome(
            success=True,
            result=cast(EventJsonValue, {"tools": tools, "prompts": self._function_prompt_catalog()}),
        )

    def _function_prompt_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "prompt": item.prompt,
                "examples": [dict(example) for example in item.examples],
            }
            for item in sorted(self._function_prompts.values(), key=lambda value: value.id)
        ]

    async def start(self) -> None:
        if self.state is not AppState.CREATED:
            raise RuntimeError(f"application cannot start from state {self.state}")
        self.state = AppState.STARTING
        self._started_at = monotonic()
        self._stopped_at = None
        try:
            if self._logging_owned:
                self.logger = configure_logging(self.settings.logging)
                self.runtimes.logger = self.logger
                self.plugins.logger = self.logger
                self._logging_started = True
            self.settings.core.data_dir.mkdir(parents=True, exist_ok=True)
            self.settings.core.cache_dir.mkdir(parents=True, exist_ok=True)
            for state_directory in self._runtime_state_directories.values():
                state_directory.mkdir(parents=True, exist_ok=True)
            await self.events.start()

            definitions = self.plugins.discover(
                self.settings.plugins.enabled,
                self.settings.plugins.local_modules,
            )
            self._cordis_host = discover_cordis_host(
                self.settings.cordis,
                events=self.events,
                actions=self.actions,
                logger=self.logger,
                services=self.services,
                data_dir=self.settings.core.data_dir,
                cache_dir=self.settings.core.cache_dir,
                runtime_context_factory=self._runtime_context_factory,
                runtime_resolver=self._resolve_runtime_proxy,
                runtime_targets=self._runtime_targets,
            )
            self._runtime_manifests = {
                definition.manifest.id: definition.manifest for definition in definitions.values()
            }
            if self._cordis_host is not None:
                self._runtime_manifests.update(getattr(self._cordis_host, "runtime_manifests", {}))
            validate_extension_topology(
                self.plugins.identities(definitions),
                self._cordis_host.plugin_identities if self._cordis_host is not None else (),
            )
            declarations = tuple(
                declaration for definition in definitions.values() for declaration in definition.manifest.resource_packs
            )
            if self._cordis_host is not None:
                function_resource_packs = getattr(self._cordis_host, "function_resource_packs", {})
                declarations = (
                    *declarations,
                    *(declaration for pack_list in function_resource_packs.values() for declaration in pack_list),
                )
            self.resources = ResourceCatalog.load(self.resource_workspace, plugin_packs=declarations)
            self.translator, _warning = Translator.from_resources(self.resources, self.settings.i18n.locale)
            self.functions = FunctionDispatcher(self.resources, task_owner=self._function_tasks)
            self.services.provide(RESOURCE_CATALOG_SERVICE, self.resources, provider="liteyukibot.kernel")
            self.services.provide(I18N_SERVICE, self.translator, provider="liteyukibot.kernel")
            self.services.provide(FUNCTION_DISPATCH_SERVICE, self.functions, provider="liteyukibot.kernel")
            plugin_configs = self._plugin_configs(self.settings.plugins.config)
            self._function_host_provider = discover_function_host_provider()
            self._preflight_functions(definitions)
            self._create_function_hosts(plugin_configs)
            if self._cordis_host is not None:
                bind_hosts = getattr(self._cordis_host, "bind_function_hosts", None)
                if callable(bind_hosts):
                    bind_hosts(self._function_hosts)
            self._plugins_setup = True
            await self.plugins.setup(definitions, plugin_configs, function_hosts=self._function_hosts)
            permissions = self.services.get(_PERMISSION_SERVICE)
            allows_management = getattr(permissions, "allows_management", None)
            if callable(allows_management):
                self.management.registry.set_authorizer(allows_management)
            if os.environ.get("LITEYUKI_DAEMON_WORKER") != "1":
                await self.management.start_operations(self.settings.core.data_dir)
                self._management_started = True
            await self.runtimes.start()
            self._runtimes_started = True
            await self.plugins.start()
            if self._cordis_host is not None:
                await self._cordis_host.start()
            if self._configured_kernel_bridge is not None:
                _bridge_id, bridge = self._configured_kernel_bridge
                token = self._runtime_secrets.get(bridge.token_secret)
                if token is None:
                    raise RuntimeError("kernel broker bridge token is unavailable")
                tool_bindings = dict(self.plugins.tool_handlers)
                cordis_access = self._cordis_host.plugin_access if self._cordis_host is not None else {}
                cordis_declarations = self._cordis_host.tool_declarations if self._cordis_host is not None else ()
                for tool_id, callback in (
                    self._cordis_host.tool_handlers.items() if self._cordis_host is not None else {}
                ):
                    declared_tool = next((item for item in cordis_declarations if item.id == tool_id), None)
                    if declared_tool is None:
                        raise RuntimeError(f"Cordis Tool handler {tool_id!r} has no declaration")
                    extension_id = tool_id.rsplit(".", 1)[0]
                    tool_bindings[tool_id] = (extension_id, declared_tool, callback)
                function_tool_declarations: list[BrokerToolDeclaration] = []
                for extension_id, preflight in sorted(self._function_preflights.items()):
                    for declaration in preflight.tool_declarations:
                        if declaration.id in tool_bindings:
                            raise RuntimeError(f"LYF Tool collides with an installed Tool: {declaration.id}")
                        function_callback = self._function_tool_callbacks.get(declaration.id)
                        if function_callback is None:
                            raise RuntimeError(f"LYF Tool has no registered callback: {declaration.id}")

                        tool_bindings[declaration.id] = (
                            extension_id,
                            declaration,
                            function_callback,
                        )
                        function_tool_declarations.append(
                            BrokerToolDeclaration(
                                id=declaration.id,
                                description=declaration.description,
                                input_schema=declaration.input_schema,
                                output_schema=declaration.output_schema,
                                capabilities=declaration.capabilities,
                            )
                        )
                tool_handlers: dict[str, Callable[[ToolInvoke], Awaitable[ToolOutcome]]] = {}
                for tool_id, (extension_id, declaration, callback) in tool_bindings.items():

                    async def handle_tool(
                        request: ToolInvoke,
                        *,
                        extension_id: str = extension_id,
                        declaration: ToolDeclaration = declaration,
                        callback: ToolCallback = callback,
                    ) -> ToolOutcome:
                        try:
                            Draft202012Validator(dict(declaration.input_schema)).validate(dict(request.arguments))
                        except (TypeError, ValueError, ValidationError):
                            return ToolOutcome(success=False, error_code="TOOL_SCHEMA_INVALID")
                        context = AuthorizationContext(
                            event_id=request.authorization.event_id,
                            runtime_id=request.authorization.runtime_id,
                            bot_id=request.authorization.bot_id,
                            actor_id=request.authorization.actor_id,
                        )
                        permissions = self.services.get(_PERMISSION_SERVICE)
                        allows_extension = getattr(permissions, "allows_extension", None)
                        capabilities = getattr(declaration, "capabilities", ())
                        full_access = cordis_access.get(extension_id) == "full"
                        if any(
                            not callable(allows_extension)
                            or not allows_extension(context, extension_id, capability, full=full_access)
                            for capability in capabilities
                        ):
                            return ToolOutcome(success=False, error_code="TOOL_PERMISSION_DENIED")
                        try:
                            result = _json_safe_tool_value(
                                await callback(context, cast(Mapping[str, Any], request.arguments))
                            )
                            Draft202012Validator(dict(declaration.output_schema)).validate(result)
                        except (TypeError, ValueError, ValidationError):
                            return ToolOutcome(success=False, error_code="TOOL_SCHEMA_INVALID")
                        return ToolOutcome(success=True, result=result)

                    tool_handlers[tool_id] = handle_tool
                self._kernel_broker_peer = KernelBrokerPeer.from_settings(
                    self.settings,
                    token=token,
                    events=self.events,
                    tools=tuple(
                        [
                            BrokerToolDeclaration(
                                id=tool.id,
                                description=tool.description,
                                input_schema=tool.input_schema,
                                output_schema=tool.output_schema,
                                capabilities=tool.capabilities,
                            )
                            for definition in definitions.values()
                            for tool in definition.manifest.tools
                        ]
                        + [
                            BrokerToolDeclaration(
                                id=tool.id,
                                description=tool.description,
                                input_schema=tool.input_schema,
                                output_schema=tool.output_schema,
                                capabilities=tool.capabilities,
                            )
                            for tool in cordis_declarations
                        ]
                        + function_tool_declarations
                    ),
                    tool_handlers=tool_handlers,
                    controls=(AGENT_FUNCTION_CATALOG, AGENT_PROMPT_CATALOG) if self._function_preflights else (),
                    control_handlers=(
                        {
                            AGENT_FUNCTION_CATALOG: self._handle_function_catalog,
                            AGENT_PROMPT_CATALOG: self._handle_prompt_catalog,
                        }
                        if self._function_preflights
                        else {}
                    ),
                )
                await self._kernel_broker_peer.start()
                self._kernel_broker_started = True

            self._control_started = True
            await self.control.start()
            if self.http is not None:
                self._http_started = True
                await self.http.start()

            self._accepting_events = True
            self.state = AppState.READY
            self.logger.info(
                "LiteyukiBot is ready with {} plugin(s) and {} runtime(s)",
                len(self.plugins.loaded),
                len(self.runtimes.records),
            )
        except BaseException as start_error:
            self.state = AppState.FAILED
            try:
                await self._cleanup()
            except BaseException as cleanup_error:
                start_error.add_note(f"startup cleanup also failed: {cleanup_error}")
            self._freeze_uptime()
            raise

    async def stop(self) -> None:
        if self.state in {AppState.STOPPED, AppState.CREATED}:
            self.state = AppState.STOPPED
            self._freeze_uptime()
            return
        if self.state is AppState.STOPPING:
            return
        self.state = AppState.STOPPING
        try:
            await self._cleanup()
        except BaseException:
            self.state = AppState.FAILED
            raise
        else:
            self.state = AppState.STOPPED
        finally:
            self._freeze_uptime()

    async def run(self) -> None:
        await self.start()
        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()

    async def __aenter__(self) -> LiteyukiApp:
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.stop()

    def status_snapshot(self) -> KernelStatusSnapshot:
        return KernelStatusSnapshot(
            version=__version__,
            state=self.state.value,
            uptime_seconds=self._uptime_seconds(),
            plugins={plugin_id: plugin.state.value for plugin_id, plugin in self.plugins.loaded.items()},
            runtimes={runtime_id: record.state.value for runtime_id, record in self.runtimes.records.items()},
            runtime_health=self.runtimes.health(),
            events_outstanding=self.events.outstanding,
        )

    def status(self) -> dict[str, Any]:
        return self.status_snapshot().as_dict()

    def topology(self, *, discover_plugins: bool = False) -> dict[str, object]:
        """Return a redacted module graph without starting processes or plugins."""

        definitions = (
            self.plugins.discover(self.settings.plugins.enabled, self.settings.plugins.local_modules)
            if discover_plugins
            else {plugin_id: loaded.definition for plugin_id, loaded in self.plugins.loaded.items()}
        )
        runtime_health = self.runtimes.health()
        return {
            "schema_version": 1,
            "kernel": {"version": __version__, "state": self.state.value},
            "services": [{"key": str(item.key), "provider": item.provider} for item in self.services.snapshot()],
            "plugins": [
                {
                    "id": definition.manifest.id,
                    "name": definition.manifest.name,
                    "version": definition.manifest.version,
                    "api_version": definition.manifest.api_version,
                    "state": self.plugins.loaded[plugin_id].state.value
                    if plugin_id in self.plugins.loaded
                    else "configured",
                    "storage": definition.manifest.storage,
                    "provides": [str(key) for key in definition.manifest.provides],
                    "requires": [
                        {"key": str(requirement.key), "optional": requirement.optional}
                        for requirement in definition.manifest.requires
                    ],
                    "resource_packs": [
                        {"package": pack.package, "root": pack.root} for pack in definition.manifest.resource_packs
                    ],
                }
                for plugin_id, definition in sorted(definitions.items())
            ],
            "runtimes": [
                {
                    "id": runtime_id,
                    "kind": runtime.kind,
                    "enabled": runtime.enabled,
                    "health": runtime_health.get(runtime_id),
                }
                for runtime_id, runtime in sorted(self.settings.runtimes.items())
            ],
            "event_routes": [
                {
                    "sources": list(route.sources),
                    "target": route.target,
                    "messages_only": route.messages_only,
                }
                for route in self._runtime_event_routes
            ],
        }

    def _uptime_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        end = self._stopped_at if self._stopped_at is not None else monotonic()
        return max(0.0, end - self._started_at)

    def _freeze_uptime(self) -> None:
        if self._started_at is not None and self._stopped_at is None:
            self._stopped_at = monotonic()

    async def _cleanup(self) -> None:
        self._accepting_events = False
        errors: list[BaseException] = []
        if self._http_started and self.http is not None:
            try:
                await self.http.stop()
            except BaseException as error:
                errors.append(error)
            self._http_started = False
        if self._control_started:
            try:
                await self.control.stop()
            except BaseException as error:
                errors.append(error)
            self._control_started = False
        if self._management_started:
            try:
                await self.management.close_operations()
            except BaseException as error:
                errors.append(error)
            self._management_started = False
        if self._kernel_broker_started and self._kernel_broker_peer is not None:
            try:
                await self._kernel_broker_peer.stop()
            except BaseException as error:
                errors.append(error)
            self._kernel_broker_started = False
        if self._cordis_host is not None:
            try:
                await self._cordis_host.aclose()
            except BaseException as error:
                errors.append(error)
            self._cordis_host = None
        try:
            await self._close_function_hosts()
        except BaseException as error:
            errors.append(error)
        try:
            await self.events.aclose()
        except BaseException as error:
            errors.append(error)
        if self._plugins_setup:
            try:
                await self.plugins.stop()
            except BaseException as error:
                errors.append(error)
            self._plugins_setup = False
        if self.functions is not None:
            try:
                await self.functions.aclose()
            except BaseException as error:
                errors.append(error)
        if self._runtimes_started or self.runtimes.records:
            try:
                await self.runtimes.stop()
            except BaseException as error:
                errors.append(error)
            self._runtimes_started = False
        if self._logging_started:
            try:
                shutdown_logging()
            except BaseException as error:
                errors.append(error)
            self._logging_started = False
        if errors:
            raise BaseExceptionGroup("application cleanup failed", errors)

    async def _close_function_hosts(self) -> None:
        for subscription in reversed(self._function_subscriptions):
            self.events.unsubscribe(subscription)
        self._function_subscriptions.clear()
        errors: list[BaseException] = []
        for extension_id, host in reversed(tuple(self._function_hosts.items())):
            try:
                await host.aclose()
            except BaseException as error:
                errors.append(error)
            self._function_hosts.pop(extension_id, None)
        for extension_id, tasks in reversed(tuple(self._function_host_tasks.items())):
            try:
                await tasks.stop()
            except BaseException as error:
                errors.append(error)
            self._function_host_tasks.pop(extension_id, None)
        self._function_preflights.clear()
        self._function_prompts.clear()
        self._function_tool_callbacks.clear()
        self._function_event_callbacks.clear()
        if errors:
            raise BaseExceptionGroup("Function Host cleanup failed", errors)

    def _function_task_failed(self, name: str, error: BaseException) -> None:
        self.logger.bind(component="functions").error("function task {} failed: {}", name, error)

    async def _ingest_runtime_event(self, runtime_id: str, payload: dict[str, Any]) -> str:
        log_payload(
            self.logger,
            self.settings.logging,
            operation="runtime.event",
            payload=payload,
            runtime_id=runtime_id,
        )
        if not self._accepting_events:
            return "invalid"
        try:
            event = EventEnvelope.model_validate(payload)
        except ValueError as error:
            self.logger.bind(runtime=runtime_id, component="runtime").warning(
                "runtime event failed validation: {}", error
            )
            return "invalid"
        if event.runtime_id != runtime_id:
            self.logger.bind(runtime=runtime_id, component="runtime").warning(
                "runtime event claimed a different runtime id"
            )
            return "invalid"
        result = await self.events.publish(event)
        return "accepted" if result.status == "processed" else result.status

    async def _execute_runtime_action(
        self,
        source_runtime_id: str,
        payload: dict[str, Any],
        provenance: ActionProvenance | None,
    ) -> ActionSinkResult:
        log_payload(
            self.logger,
            self.settings.logging,
            operation="runtime.action",
            payload=payload,
            runtime_id=source_runtime_id,
        )
        try:
            action = ActionEnvelope.model_validate(payload)
        except ValueError as error:
            self.logger.bind(runtime=source_runtime_id, component="runtime").warning(
                "runtime action failed validation: {}", error
            )
            return ActionSinkResult(ok=False, error="invalid ActionEnvelope")
        if provenance is not None:
            try:
                source_event = EventEnvelope.model_validate(provenance.event_payload)
            except ValueError:
                return ActionSinkResult(ok=False, error="action provenance has an invalid EventEnvelope")
            if (
                action.event_id != source_event.id
                or action.runtime_id != source_event.runtime_id
                or action.bot_id != source_event.bot_id
            ):
                return ActionSinkResult(
                    ok=False,
                    error="child action does not match its source event provenance",
                )
        if action.runtime_id == source_runtime_id:
            return ActionSinkResult(
                ok=False,
                error="child-originated action cannot target its source runtime",
            )
        result = await self.actions.execute(action, event=source_event if provenance is not None else None)
        return ActionSinkResult(
            ok=result.success,
            data=result.model_dump(mode="json"),
            error=result.error_message,
        )

    async def _execute_runtime_management(
        self, runtime_id: str, command: str
    ) -> tuple[bool, str, JsonValue, str | None]:
        caller = ManagementCaller(runtime_id, "runtime", frozenset())
        try:
            _definition, result = await self.management.registry.execute(caller, command)
        except ManagementError as error:
            log_payload(
                self.logger,
                self.settings.logging,
                operation="runtime.management",
                payload={"command": command, "error": str(error)},
                runtime_id=runtime_id,
            )
            return False, "", None, str(error)
        data = json_value(result.data) if result.data is not None else None
        log_payload(
            self.logger,
            self.settings.logging,
            operation="runtime.management",
            payload={"command": command, "result": data if data is not None else result.text},
            runtime_id=runtime_id,
        )
        return True, result.text, data, None

    def _authorize_action(self, event: EventEnvelope | None, action: ActionEnvelope) -> ActionResult | None:
        if not isinstance(action.action, CallApi):
            return None
        if event is None:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="ACTION_PERMISSION_DENIED",
                error_message="adapter API action requires a source event",
            )
        if action.event_id != event.id or action.runtime_id != event.runtime_id or action.bot_id != event.bot_id:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error_code="ACTION_PERMISSION_DENIED",
                error_message="adapter API action does not match its source event",
            )
        permissions = _permission_service(self.services)
        decide = getattr(permissions, "decide", None)
        allows = getattr(permissions, "allows", None)
        allowed = (
            decide(event, ADAPTER_CALL_API, component="adapter.call_api")
            if callable(decide)
            else callable(allows) and allows(event, ADAPTER_CALL_API)
        )
        if not callable(decide):
            self.logger.bind(
                runtime=event.runtime_id,
                component="permissions",
                capability=ADAPTER_CALL_API,
                event_id=event.id,
                allowed=allowed,
            ).info("adapter API action permission {}", "granted" if allowed else "denied")
        if allowed:
            return None
        return ActionResult(
            action_id=action.action_id,
            success=False,
            error_code="ACTION_PERMISSION_DENIED",
            error_message="adapter API action permission is denied",
        )

    async def _execute_event_action(self, event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
        if self._kernel_broker_peer is not None:
            result = await self._kernel_broker_peer.execute_action(event, action)
            if result is not None:
                return result
        return await self.actions.execute(action, event=event)

    async def _clear_agent_history(self, event: EventEnvelope) -> int:
        permissions = _permission_service(self.services)
        decide = getattr(permissions, "decide", None)
        allows = getattr(permissions, "allows", None)
        allowed = (
            decide(event, AGENT_HISTORY_CLEAR, component="agent.history.clear")
            if callable(decide)
            else callable(allows) and allows(event, AGENT_HISTORY_CLEAR)
        )
        if not callable(decide):
            self.logger.bind(
                runtime=event.runtime_id,
                component="permissions",
                capability=AGENT_HISTORY_CLEAR,
                event_id=event.id,
                allowed=allowed,
            ).info("agent history permission {}", "granted" if allowed else "denied")
        if not allowed:
            raise PermissionError("agent history clear permission is denied")

        if self._kernel_broker_peer is None:
            raise ConnectionError("Agent bridge is unavailable")
        authorization = AuthorizationContextWire(
            event_id=event.id,
            runtime_id=event.runtime_id,
            bot_id=event.bot_id,
            actor_id=event.actor.id if event.actor is not None else None,
        )
        response = await self._kernel_broker_peer.request_control(
            event,
            correlation_id=str(uuid4()),
            command="agent.history.clear",
            authorization=authorization,
            payload={
                "runtime_id": event.runtime_id,
                "bot_id": event.bot_id,
                "conversation_id": event.conversation.ordering_key,
            },
            timeout_seconds=self.settings.broker.delivery_timeout_seconds,
        )
        if response is None:
            raise ConnectionError("Agent bridge delivery is unavailable")
        if not response.success:
            raise RuntimeError(response.error_code or "Agent history clear failed")
        if not isinstance(response.result, Mapping):
            raise RuntimeError("Agent bridge returned an invalid history clear response")
        cleared = response.result.get("cleared")
        if not isinstance(cleared, int) or isinstance(cleared, bool) or cleared < 0:
            raise RuntimeError("Agent bridge returned an invalid history clear response")
        return cleared

    def _event_routes(self, settings: AppSettings) -> tuple[RuntimeEventRoute, ...]:
        routes = list(settings.runtime_event_routes)
        configured_targets = {route.target for route in routes}
        runtime_plugins = RuntimeCatalog().discover()
        enabled_ids = tuple(runtime_id for runtime_id, runtime in settings.runtimes.items() if runtime.enabled)
        for runtime_id, runtime in settings.runtimes.items():
            plugin = runtime_plugins.get(runtime.kind)
            if (
                not runtime.enabled
                or runtime_id in configured_targets
                or plugin is None
                or not plugin.default_event_route_messages_only
            ):
                continue
            sources = tuple(source for source in enabled_ids if source != runtime_id)
            if sources:
                routes.append(
                    RuntimeEventRoute(
                        sources=sources,
                        target=runtime_id,
                        messages_only=True,
                    )
                )
        return tuple(routes)

    async def _forward_runtime_event(self, event: EventEnvelope) -> None:
        targets = tuple(
            route.target
            for route in self._runtime_event_routes
            if event.runtime_id in route.sources and (not route.messages_only or event.message is not None)
        )
        if not targets:
            return
        outcomes = await asyncio.gather(
            *(self._deliver_runtime_event(runtime_id, event) for runtime_id in targets),
            return_exceptions=True,
        )
        fatal = next(
            (
                outcome
                for outcome in outcomes
                if isinstance(outcome, BaseException) and not isinstance(outcome, Exception)
            ),
            None,
        )
        if fatal is not None:
            raise fatal
        errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        if len(errors) == 1:
            raise errors[0]
        if len(errors) > 1:
            raise ExceptionGroup("runtime event delivery failed", errors)

    async def _deliver_runtime_event(self, runtime_id: str, event: EventEnvelope) -> None:
        result = await self.runtimes.dispatch_event(
            runtime_id,
            event.id,
            event.model_dump(mode="json"),
        )
        if result.status != "accepted":
            detail = f": {result.detail}" if result.detail else ""
            raise RuntimeError(f"runtime {runtime_id} rejected event {event.id} as {result.status}{detail}")

    @staticmethod
    def _plugin_configs(config: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        normalized: dict[str, Mapping[str, Any]] = {}
        for plugin_id, value in config.items():
            if not isinstance(value, Mapping):
                raise ValueError(f"plugin config for {plugin_id} must be a mapping")
            normalized[plugin_id] = value
        return normalized


__all__ = ["ActionService", "AppState", "LiteyukiApp"]


def _json_safe_tool_value(value: object) -> EventJsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Tool result contains a non-finite number")
        return value
    if isinstance(value, list):
        return cast(EventJsonValue, [_json_safe_tool_value(item) for item in value])
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Tool result object keys must be strings")
        return {key: _json_safe_tool_value(item) for key, item in value.items()}
    raise TypeError("Tool result is not JSON-safe")
