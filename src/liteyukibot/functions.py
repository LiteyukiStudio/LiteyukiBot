"""Resource-backed dispatch to separately distributed Liteyuki function executors."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from importlib import metadata
from pathlib import PurePosixPath
from typing import Any, Protocol

from .resource_packs import ResourceCatalog, ResourceFile
from .services import ServiceKey

FUNCTION_DISPATCH_SERVICE = ServiceKey("liteyukibot.functions", 1)


class FunctionError(RuntimeError):
    """Base error for resource function lookup and dispatch."""


class FunctionNotFoundError(FunctionError):
    pass


class FunctionExecutorUnavailableError(FunctionError):
    pass


@dataclass(frozen=True, slots=True)
class FunctionDocument:
    id: str
    extension: str
    resource: ResourceFile

    def read_text(self) -> str:
        return self.resource.read_text()


@dataclass(frozen=True, slots=True)
class FunctionCall:
    id: str
    arguments: Mapping[str, Any]


class FunctionExecutor(Protocol):
    extensions: tuple[str, ...]

    def execute(self, document: FunctionDocument, call: FunctionCall) -> Awaitable[object]: ...


class FunctionCatalog:
    def __init__(self, resources: ResourceCatalog) -> None:
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
        try:
            return self._documents[identifier]
        except KeyError as error:
            raise FunctionNotFoundError(f"function does not exist: {identifier}") from error

    def snapshot(self) -> tuple[FunctionDocument, ...]:
        return tuple(self._documents[key] for key in sorted(self._documents))


class FunctionDispatcher:
    ENTRY_POINT_GROUP = "liteyukibot.function_executors"

    def __init__(self, resources: ResourceCatalog, executors: Mapping[str, FunctionExecutor] | None = None) -> None:
        self.catalog = FunctionCatalog(resources)
        self._executors = dict(executors) if executors is not None else self.discover_executors()

    @classmethod
    def discover_executors(cls) -> dict[str, FunctionExecutor]:
        executors: dict[str, FunctionExecutor] = {}
        for entry in metadata.entry_points(group=cls.ENTRY_POINT_GROUP):
            candidate = entry.load()
            executor = candidate() if callable(candidate) and not hasattr(candidate, "execute") else candidate
            if not hasattr(executor, "extensions") or not callable(getattr(executor, "execute", None)):
                raise FunctionError(f"function executor {entry.name!r} has an invalid contract")
            for extension in executor.extensions:
                normalized = extension.lower() if extension.startswith(".") else "." + extension.lower()
                if normalized in executors:
                    raise FunctionError(f"multiple function executors handle {normalized}")
                executors[normalized] = executor
        return executors

    async def dispatch(self, call: FunctionCall) -> object:
        document = self.catalog.require(call.id)
        executor = self._executors.get(document.extension)
        if executor is None:
            raise FunctionExecutorUnavailableError(
                f"no executor is installed for {document.extension} functions; install a matching function package"
            )
        result = executor.execute(document, call)
        if not inspect.isawaitable(result):
            raise FunctionError("function executor execute() must return an awaitable")
        return await result


__all__ = [
    "FUNCTION_DISPATCH_SERVICE",
    "FunctionCall",
    "FunctionCatalog",
    "FunctionDispatcher",
    "FunctionDocument",
    "FunctionError",
    "FunctionExecutor",
    "FunctionExecutorUnavailableError",
    "FunctionNotFoundError",
]
