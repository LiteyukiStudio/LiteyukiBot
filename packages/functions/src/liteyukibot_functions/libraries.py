"""Host-neutral Function Library definitions for Alpha 7 LYF."""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from .ast import FrozenJSONValue

type LibraryCallback = Callable[[tuple[FrozenJSONValue, ...], "FunctionContext"], object]

FUNCTION_LIBRARY_ENTRY_POINT_GROUP = "liteyukibot.function_libraries"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PROVIDER = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


@dataclass(frozen=True, slots=True)
class FunctionContext:
    """Restricted context passed to a Library callback."""

    source_id: str
    function_name: str
    metadata: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    emit_log: Callable[[str], object] | None = None
    select_prompt: Callable[[str], object] | None = None


@dataclass(frozen=True, slots=True)
class LibraryExport:
    """Represent the library export contract."""
    name: str
    callback: LibraryCallback
    is_async: bool = False
    pure: bool = False
    capabilities: tuple[str, ...] = ()
    input_schema: Mapping[str, Any] | None = None
    output_schema: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class LibraryDefinition:
    """Represent the library definition contract."""
    namespace: str
    provider: str
    exports: tuple[LibraryExport, ...]
    version: str = "1.0"

    @property
    def export_map(self) -> Mapping[str, LibraryExport]:
        """Return the library definition's export map.

        Returns:
            The `Mapping[str, LibraryExport]` result produced by the operation.
        """
        return {item.name: item for item in self.exports}


class LibraryRegistry:
    """Deterministic Provider registry used by parser hosts and runtimes."""

    def __init__(self, definitions: Iterable[LibraryDefinition] = ()) -> None:
        """Initialize the library registry.

        Args:
            definitions: The definitions value used by the operation.

        Returns:
            None.
        """
        self._definitions = tuple(definitions)
        self._validate()

    @classmethod
    def with_core(cls) -> LibraryRegistry:
        """Implement the with core operation for the library registry.

        Returns:
            The `LibraryRegistry` result produced by the operation.
        """
        return cls(default_library_definitions())

    @classmethod
    def discover(cls, *, include_core: bool = True) -> LibraryRegistry:
        """Load the built-in and installed Library Providers deterministically.

        Args:
            include_core: The include core value used by the operation.

        Returns:
            The `LibraryRegistry` result produced by the operation.
        """

        definitions = list(default_library_definitions() if include_core else ())
        for entry in metadata.entry_points(group=FUNCTION_LIBRARY_ENTRY_POINT_GROUP):
            try:
                loaded = entry.load()
                candidate = loaded() if inspect.isclass(loaded) or callable(loaded) else loaded
                if isinstance(candidate, LibraryDefinition):
                    loaded_definitions = (candidate,)
                elif isinstance(candidate, Iterable) and not isinstance(candidate, (str, bytes, Mapping)):
                    loaded_definitions = tuple(candidate)
                else:
                    raise TypeError("entry point must return LibraryDefinition or an iterable of definitions")
                if not all(isinstance(item, LibraryDefinition) for item in loaded_definitions):
                    raise TypeError("entry point returned a non-LibraryDefinition value")
                definitions.extend(loaded_definitions)
            except Exception as error:
                raise ValueError(f"Function Library entry point {entry.name!r} is invalid") from error
        return cls(definitions)

    @property
    def definitions(self) -> tuple[LibraryDefinition, ...]:
        """Return the library registry's definitions.

        Returns:
            The `tuple[LibraryDefinition, ...]` result produced by the operation.
        """
        return self._definitions

    def resolve(self, namespace: str, provider: str | None = None) -> LibraryDefinition | None:
        """Resolve the library registry operation.

        Args:
            namespace: The namespace value used by the operation.
            provider: The provider value used by the operation.

        Returns:
            The requested `LibraryDefinition | None` value.
        """
        matches = tuple(item for item in self._definitions if item.namespace == namespace)
        if provider is not None:
            matches = tuple(item for item in matches if item.provider == provider)
        return matches[0] if len(matches) == 1 else None

    def matches(self, namespace: str) -> tuple[LibraryDefinition, ...]:
        """Implement the matches operation for the library registry.

        Args:
            namespace: The namespace value used by the operation.

        Returns:
            The `tuple[LibraryDefinition, ...]` result produced by the operation.
        """
        return tuple(item for item in self._definitions if item.namespace == namespace)

    def export(self, namespace: str, provider: str, name: str) -> LibraryExport | None:
        """Implement the export operation for the library registry.

        Args:
            namespace: The namespace value used by the operation.
            provider: The provider value used by the operation.
            name: Stable name used to identify the value.

        Returns:
            The `LibraryExport | None` result produced by the operation.
        """
        definition = self.resolve(namespace, provider)
        return None if definition is None else definition.export_map.get(name)

    def _validate(self) -> None:
        """Validate the library registry operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `LibraryRegistry._validate`. It delegates to
            `_validate_identifier`, `fullmatch`, `strip`, `any` while keeping intermediate state local to
            the owning operation.
        """
        seen: set[tuple[str, str]] = set()
        for definition in self._definitions:
            if not isinstance(definition, LibraryDefinition):
                raise TypeError("Function Library definitions must be LibraryDefinition instances")
            _validate_identifier(definition.namespace, "Library namespace")
            if not _PROVIDER.fullmatch(definition.provider):
                raise ValueError(f"invalid Library Provider name: {definition.provider!r}")
            if not definition.version.strip() or any(character.isspace() for character in definition.version):
                raise ValueError("Library Provider version must be a non-empty token")
            key = (definition.namespace, definition.provider)
            if key in seen:
                raise ValueError(f"duplicate Function Library Provider: {definition.namespace}@{definition.provider}")
            seen.add(key)
            exports: set[str] = set()
            for export in definition.exports:
                if not isinstance(export, LibraryExport):
                    raise TypeError("Function Library exports must be LibraryExport instances")
                if not export.name or any(not _IDENTIFIER.fullmatch(part) for part in export.name.split(".")):
                    raise ValueError(f"invalid Function Library export name: {export.name!r}")
                if export.name in exports:
                    raise ValueError(f"duplicate Function Library export: {definition.namespace}.{export.name}")
                exports.add(export.name)
                if not callable(export.callback):
                    raise TypeError(f"Function Library export is not callable: {definition.namespace}.{export.name}")
                try:
                    inspect.signature(export.callback).bind((), FunctionContext("<validate>", export.name))
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        f"Function Library callback must accept (arguments, context): "
                        f"{definition.namespace}.{export.name}"
                    ) from error
                for schema_name, schema in (("input", export.input_schema), ("output", export.output_schema)):
                    if schema is None:
                        continue
                    if not isinstance(schema, Mapping):
                        raise TypeError(
                            f"Function Library {schema_name} schema must be a JSON object: "
                            f"{definition.namespace}.{export.name}"
                        )
                    try:
                        Draft202012Validator.check_schema(dict(schema))
                    except SchemaError as error:
                        raise ValueError(
                            f"Function Library {schema_name} schema is invalid: "
                            f"{definition.namespace}.{export.name}"
                        ) from error
                if any(
                    not capability.strip() or any(character.isspace() for character in capability)
                    for capability in export.capabilities
                ):
                    raise ValueError(f"Function Library capabilities must be non-empty tokens: {export.name!r}")
                if len(set(export.capabilities)) != len(export.capabilities):
                    raise ValueError(f"Function Library capabilities must be unique: {export.name!r}")


def core_library() -> LibraryDefinition:
    """Return the side-effect-bounded built-in Core Provider.

    Returns:
        The `LibraryDefinition` result produced by the operation.
    """

    def emit(arguments: tuple[FrozenJSONValue, ...], context: FunctionContext) -> FrozenJSONValue | None:
        """Implement the emit operation for the core library.

        Args:
            arguments: JSON-safe arguments supplied to the operation.
            context: Runtime or authorization context for the operation.

        Returns:
            The `FrozenJSONValue | None` result produced by the operation.

        Notes:
            Internal implementation detail for `core_library.emit`. It delegates to `emit_log`,
            `isawaitable` while keeping intermediate state local to the owning operation.
        """
        if len(arguments) != 1:
            raise ValueError("terminal output expects one value")
        value = arguments[0]
        if context.emit_log is not None:
            result = context.emit_log(str(value))
            if inspect.isawaitable(result):
                raise ValueError("terminal output callback must be synchronous")
        return value

    return LibraryDefinition(
        namespace="terminal",
        provider="core",
        exports=(
            LibraryExport("echo", emit, pure=False),
            LibraryExport("print", emit, pure=False),
        ),
    )


def core_async_library() -> LibraryDefinition:
    """Implement the core async library operation for the component.

    Returns:
        The `LibraryDefinition` result produced by the operation.
    """
    async def sleep(arguments: tuple[FrozenJSONValue, ...], _context: FunctionContext) -> None:
        """Implement the sleep operation for the core async library.

        Args:
            arguments: JSON-safe arguments supplied to the operation.
            _context: The context value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `core_async_library.sleep`. It delegates to `sleep`, `float`
            while keeping intermediate state local to the owning operation.
        """
        if len(arguments) != 1 or not isinstance(arguments[0], (int, float)) or isinstance(arguments[0], bool):
            raise ValueError("async.sleep expects one number")
        if arguments[0] < 0:
            raise ValueError("async.sleep expects a non-negative number")
        await asyncio.sleep(float(arguments[0]))

    return LibraryDefinition(
        namespace="async",
        provider="core",
        exports=(LibraryExport("sleep", sleep, is_async=True, pure=False),),
    )


def core_agent_library() -> LibraryDefinition:
    """Implement the core agent library operation for the component.

    Returns:
        The `LibraryDefinition` result produced by the operation.
    """
    def select(arguments: tuple[FrozenJSONValue, ...], context: FunctionContext) -> object:
        """Select the core agent library operation.

        Args:
            arguments: JSON-safe arguments supplied to the operation.
            context: Runtime or authorization context for the operation.

        Returns:
            The `object` result produced by the operation.

        Notes:
            Internal implementation detail for `core_agent_library.select`. It delegates to `select_prompt`
            while keeping intermediate state local to the owning operation.
        """
        if len(arguments) != 1 or not isinstance(arguments[0], str):
            raise ValueError("agent.prompt.select expects one preset id")
        if context.select_prompt is None:
            raise PermissionError("agent.prompt.select is unavailable outside an Agent Tool")
        return context.select_prompt(arguments[0])

    return LibraryDefinition(
        namespace="agent",
        provider="liteyukibot-v7-agent",
        exports=(
            LibraryExport(
                "prompt.select",
                select,
                pure=False,
                capabilities=("liteyukibot.agent.prompt.select",),
            ),
        ),
    )


def default_library_definitions() -> tuple[LibraryDefinition, ...]:
    """Implement the default library definitions operation for the component.

    Returns:
        The `tuple[LibraryDefinition, ...]` result produced by the operation.
    """
    return (core_library(), core_async_library(), core_agent_library())


def default_library_registry() -> LibraryRegistry:
    """Implement the default library registry operation for the component.

    Returns:
        The `LibraryRegistry` result produced by the operation.
    """
    return LibraryRegistry.discover()


def _validate_identifier(value: str, label: str) -> None:
    """Validate identifier.

    Args:
        value: Value to validate, transform, or store.
        label: The label value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_validate_identifier`. It delegates to `fullmatch` while
        keeping intermediate state local to the owning operation.
    """
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"invalid {label}: {value!r}")


__all__ = [
    "FUNCTION_LIBRARY_ENTRY_POINT_GROUP",
    "FunctionContext",
    "LibraryCallback",
    "LibraryDefinition",
    "LibraryExport",
    "LibraryRegistry",
    "core_agent_library",
    "core_async_library",
    "core_library",
    "default_library_definitions",
    "default_library_registry",
]
