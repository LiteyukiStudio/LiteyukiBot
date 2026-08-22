"""Resource-backed dispatch to separately distributed Liteyuki function executors."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from importlib import metadata
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol, cast

from .resource_packs import ResourceCatalog, ResourceFile
from .services import ServiceKey
from .tasks import ManagedTasks

if TYPE_CHECKING:
    from .events import EventBus, EventEnvelope, HandlerResult
    from .plugins import ToolCallback, ToolDeclaration
    from .services import ServiceRegistry

FUNCTION_DISPATCH_SERVICE = ServiceKey("liteyukibot.functions", 1)
FUNCTION_HOST_ENTRY_POINT_GROUP = "liteyukibot.function_hosts"
FUNCTION_LIBRARY_ENTRY_POINT_GROUP = "liteyukibot.function_libraries"
AGENT_FUNCTION_CATALOG = "agent.function.catalog"
AGENT_PROMPT_CATALOG = "agent.prompt.catalog"
AGENT_PROMPT_SELECT = "agent.prompt.select"


class FunctionError(RuntimeError):
    """Base error for resource function lookup and dispatch."""


class FunctionNotFoundError(FunctionError):
    """Raised when the function not found contract cannot be satisfied."""
    pass


class FunctionExecutorUnavailableError(FunctionError):
    """Raised when the function executor unavailable contract cannot be satisfied."""
    pass


class FunctionRecursionError(FunctionError):
    """Raised when the function recursion contract cannot be satisfied."""
    pass


@dataclass(frozen=True, slots=True)
class FunctionDocument:
    """Represent the function document contract."""
    id: str
    extension: str
    resource: ResourceFile

    def read_text(self) -> str:
        """Read text.

        Returns:
            The requested `str` value.
        """
        return self.resource.read_text()


@dataclass(frozen=True, slots=True)
class FunctionCall:
    """Represent the function call contract."""
    id: str
    arguments: Mapping[str, Any]
    positional: tuple[str, ...] = ()
    capabilities: object | None = None
    task_owner: ManagedTasks | None = field(default=None, repr=False, compare=False)


type FunctionInvoker = Callable[[FunctionCall], Awaitable[object]]


@dataclass(frozen=True, slots=True)
class FunctionPackSource:
    """One extension-owned resource-pack view supplied to a Function Host."""

    extension_id: str
    pack_id: str
    files: Mapping[str, bytes]


@dataclass(frozen=True, slots=True)
class FunctionPromptPreset:
    """A preflighted, bounded prompt preset contributed by one extension."""

    extension_id: str
    id: str
    name: str
    description: str
    prompt: str
    examples: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class FunctionEventContribution:
    """Static event metadata collected before host lifecycle binding."""

    extension_id: str
    function_id: str
    topics: tuple[str, ...]
    filters: Mapping[str, Any]
    parameters: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FunctionPreflight:
    """Static output of parsing and validating one extension's Function packs."""

    extension_id: str
    function_ids: tuple[str, ...] = ()
    tool_declarations: tuple[ToolDeclaration, ...] = ()
    tool_function_ids: Mapping[str, str] = field(default_factory=dict)
    prompts: tuple[FunctionPromptPreset, ...] = ()
    events: tuple[FunctionEventContribution, ...] = ()


class FunctionHost(Protocol):
    """Host-bound execution surface shared by Native and Cordis adapters."""

    preflight: FunctionPreflight

    async def invoke(
        self,
        function_id: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        event: EventEnvelope | None = None,
    ) -> Any:
        """Invoke the function host operation.

        Args:
            function_id: Stable identifier for the function.
            arguments: JSON-safe arguments supplied to the operation.
            event: Event associated with the operation.

        Returns:
            The `Any` result produced by the operation.
        """
        ...

    async def aclose(self) -> None:
        """Close the function host asynchronously.

        Returns:
            None.
        """
        ...


@dataclass(frozen=True, slots=True)
class FunctionHostBindings:
    """Host-owned capabilities supplied to a Function runtime implementation."""

    extension_id: str
    config: Mapping[str, Any]
    events: EventBus
    services: ServiceRegistry
    tasks: ManagedTasks
    logger: Any
    register_tool: Callable[[ToolDeclaration, ToolCallback], None]
    register_event: Callable[
        [FunctionEventContribution, Callable[[EventEnvelope], Awaitable[HandlerResult | None]]], Any
    ]
    emit_log: Callable[[str], Any] | None = None
    select_prompt: Callable[[EventEnvelope, str], Awaitable[Any]] | None = None
    resolve_event: Callable[[str], EventEnvelope | None] | None = None


class FunctionHostProvider(Protocol):
    """Entry-point contract for the installed LYF implementation."""

    def preflight(self, sources: tuple[FunctionPackSource, ...]) -> FunctionPreflight:
        """Implement the preflight operation for the function host provider.

        Args:
            sources: The sources value used by the operation.

        Returns:
            The `FunctionPreflight` result produced by the operation.
        """
        ...

    def create_host(self, preflight: FunctionPreflight, bindings: FunctionHostBindings) -> FunctionHost:
        """Create host.

        Args:
            preflight: The preflight value used by the operation.
            bindings: The bindings value used by the operation.

        Returns:
            The `FunctionHost` result produced by the operation.
        """
        ...


def discover_function_host_provider() -> FunctionHostProvider | None:
    """Discover the one installed Alpha7 Function Host provider, if present.

    Returns:
        The `FunctionHostProvider | None` result produced by the operation.
    """

    entry_points = tuple(metadata.entry_points(group=FUNCTION_HOST_ENTRY_POINT_GROUP))
    if not entry_points:
        return None
    if len(entry_points) != 1:
        names = ", ".join(sorted(entry.name for entry in entry_points))
        raise FunctionError(f"Function Host requires exactly one implementation; found: {names}")
    entry_point = entry_points[0]
    try:
        candidate = entry_point.load()
    except Exception as error:
        raise FunctionError(f"Function Host entry point {entry_point.name!r} could not be imported") from error
    provider = candidate() if inspect.isclass(candidate) else candidate
    if not callable(getattr(provider, "preflight", None)) or not callable(getattr(provider, "create_host", None)):
        raise FunctionError(f"Function Host entry point {entry_point.name!r} has an invalid contract")
    return cast(FunctionHostProvider, provider)


class FunctionExecutor(Protocol):
    """Define the structural interface required from a function executor."""
    extensions: tuple[str, ...]

    def execute(
        self,
        document: FunctionDocument,
        call: FunctionCall,
        invoke: FunctionInvoker,
    ) -> Awaitable[object]:
        """Execute one request through the function executor.

        Args:
            document: The document value used by the operation.
            call: The call value used by the operation.
            invoke: The invoke value used by the operation.

        Returns:
            The `Awaitable[object]` result produced by the operation.
        """
        ...


class FunctionCatalog:
    """Represent the function catalog contract."""
    def __init__(self, resources: ResourceCatalog) -> None:
        """Initialize the function catalog.

        Args:
            resources: The resources value used by the operation.

        Returns:
            None.
        """
        documents: dict[str, FunctionDocument] = {}
        for path in resources.paths("functions"):
            relative = path.removeprefix("functions/")
            suffix = PurePosixPath(relative).suffix.lower()
            if not suffix:
                continue
            identifier = relative[: -len(suffix)]
            if identifier in documents:
                raise FunctionError(f"multiple resources define function {identifier!r}")
            documents[identifier] = FunctionDocument(identifier, suffix, resources.require(path))
        self._documents = documents

    def require(self, identifier: str) -> FunctionDocument:
        """Return the function catalog operation, failing when it is unavailable.

        Args:
            identifier: The identifier value used by the operation.

        Returns:
            The requested `FunctionDocument` value.
        """
        try:
            return self._documents[identifier]
        except KeyError as error:
            raise FunctionNotFoundError(f"function does not exist: {identifier}") from error

    def snapshot(self) -> tuple[FunctionDocument, ...]:
        """Return an immutable snapshot of the function catalog state.

        Returns:
            The requested `tuple[FunctionDocument, ...]` value.
        """
        return tuple(self._documents[key] for key in sorted(self._documents))


class FunctionDispatcher:
    """Represent the function dispatcher contract."""
    ENTRY_POINT_GROUP = "liteyukibot.function_executors"

    def __init__(
        self,
        resources: ResourceCatalog,
        executors: Mapping[str, FunctionExecutor] | None = None,
        *,
        task_owner: ManagedTasks | None = None,
    ) -> None:
        """Initialize the function dispatcher.

        Args:
            resources: The resources value used by the operation.
            executors: The executors value used by the operation.
            task_owner: The task owner value used by the operation.

        Returns:
            None.
        """
        self.catalog = FunctionCatalog(resources)
        self._executors = dict(executors) if executors is not None else self.discover_executors()
        self._task_owner = task_owner or ManagedTasks("functions")
        self._closed = False

    @property
    def background_task_count(self) -> int:
        """Return the function dispatcher's background task count.

        Returns:
            The `int` result produced by the operation.
        """
        return self._task_owner.count

    @classmethod
    def discover_executors(cls) -> dict[str, FunctionExecutor]:
        """Discover executors.

        Returns:
            The `dict[str, FunctionExecutor]` result produced by the operation.
        """
        executors: dict[str, FunctionExecutor] = {}
        for entry in metadata.entry_points(group=cls.ENTRY_POINT_GROUP):
            candidate = entry.load()
            executor = (
                candidate()
                if inspect.isclass(candidate) or (callable(candidate) and not hasattr(candidate, "execute"))
                else candidate
            )
            if not hasattr(executor, "extensions") or not callable(getattr(executor, "execute", None)):
                raise FunctionError(f"function executor {entry.name!r} has an invalid contract")
            for extension in executor.extensions:
                normalized = extension.lower() if extension.startswith(".") else "." + extension.lower()
                if normalized in executors:
                    raise FunctionError(f"multiple function executors handle {normalized}")
                executors[normalized] = executor
        return executors

    async def dispatch(self, call: FunctionCall) -> object:
        """Dispatch the function dispatcher operation.

        Args:
            call: The call value used by the operation.

        Returns:
            The `object` result produced by the operation.
        """
        if self._closed:
            raise FunctionError("function dispatcher is closed")
        return await self._dispatch(call, ())

    async def aclose(self) -> None:
        """Close the function dispatcher asynchronously.

        Returns:
            None.
        """
        if self._closed:
            return
        self._closed = True
        await self._task_owner.stop()

    async def _dispatch(self, call: FunctionCall, stack: tuple[str, ...]) -> object:
        """Dispatch the function dispatcher operation.

        Args:
            call: The call value used by the operation.
            stack: The stack value used by the operation.

        Returns:
            The `object` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionDispatcher._dispatch`. It delegates to `replace`,
            `require`, `join`, `get` while keeping intermediate state local to the owning operation.
        """
        call = replace(call, task_owner=self._task_owner)
        document = self.catalog.require(call.id)
        if document.id in stack:
            cycle = " -> ".join((*stack, document.id))
            raise FunctionRecursionError(f"function recursion is not allowed: {cycle}")
        if len(stack) >= 32:
            raise FunctionRecursionError("function nesting exceeds the maximum depth of 32")
        executor = self._executors.get(document.extension)
        if executor is None:
            raise FunctionExecutorUnavailableError(
                f"no executor is installed for {document.extension} functions; install a matching function package"
            )

        async def invoke(nested_call: FunctionCall) -> object:
            """Invoke the dispatch operation.

            Args:
                nested_call: The nested call value used by the operation.

            Returns:
                The `object` result produced by the operation.

            Notes:
                Internal implementation detail for `FunctionDispatcher._dispatch.invoke`. It delegates to
                `_dispatch` while keeping intermediate state local to the owning operation.
            """
            return await self._dispatch(nested_call, (*stack, document.id))

        result = executor.execute(document, call, invoke)
        if not inspect.isawaitable(result):
            raise FunctionError("function executor execute() must return an awaitable")
        return await result


__all__ = [
    "AGENT_FUNCTION_CATALOG",
    "AGENT_PROMPT_CATALOG",
    "AGENT_PROMPT_SELECT",
    "FUNCTION_DISPATCH_SERVICE",
    "FUNCTION_HOST_ENTRY_POINT_GROUP",
    "FUNCTION_LIBRARY_ENTRY_POINT_GROUP",
    "FunctionCall",
    "FunctionCatalog",
    "FunctionDispatcher",
    "FunctionDocument",
    "FunctionError",
    "FunctionExecutor",
    "FunctionExecutorUnavailableError",
    "FunctionEventContribution",
    "FunctionHost",
    "FunctionHostBindings",
    "FunctionHostProvider",
    "FunctionNotFoundError",
    "FunctionPackSource",
    "FunctionPreflight",
    "FunctionPromptPreset",
    "FunctionRecursionError",
    "discover_function_host_provider",
]
