"""Public Alpha 7 Function Host adapter for the Kernel host contract."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, cast

from jsonschema import Draft202012Validator, ValidationError

from liteyukibot.authorization import AuthorizationContext
from liteyukibot.events import EventEnvelope
from liteyukibot.functions import (
    FunctionEventContribution,
    FunctionHost,
    FunctionHostBindings,
    FunctionPackSource,
    FunctionPreflight,
    FunctionPromptPreset,
)
from liteyukibot.plugins import JsonValue, ToolCallback, ToolDeclaration

from .ast import FunctionProgram
from .diagnostics import Diagnostic
from .libraries import FunctionContext, LibraryRegistry, default_library_registry
from .parser import parse
from .preflight import PreflightResult
from .preflight import preflight as check_preflight
from .runtime import FunctionRuntime


class FunctionHostError(RuntimeError):
    """Raised when an extension's LYF sources cannot enter the host."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        message = "; ".join(f"{item.code}: {item.message}" for item in diagnostics)
        super().__init__(message or "LYF Function Host preflight failed")


@dataclass(frozen=True, slots=True)
class _FunctionTarget:
    runtime: FunctionRuntime
    local_name: str


@dataclass(frozen=True, slots=True)
class _SourceArtifact:
    source_id: str
    program: FunctionProgram
    checked: PreflightResult
    function_ids: Mapping[str, str]


class Alpha7FunctionHostProvider:
    """Adapt package-local LYF sources to the public FunctionHost protocol."""

    def __init__(self, libraries: LibraryRegistry | None = None) -> None:
        self.libraries = libraries or default_library_registry()
        self._artifacts: dict[int, tuple[_SourceArtifact, ...]] = {}

    def preflight(self, sources: tuple[FunctionPackSource, ...]) -> FunctionPreflight:
        if not sources:
            raise FunctionHostError(
                (Diagnostic("LYF_RESOURCE_EMPTY", "no Function resource pack was supplied", "<host>"),)
            )
        extension_ids = {source.extension_id for source in sources}
        if len(extension_ids) != 1:
            raise FunctionHostError(
                (Diagnostic("LYF_RESOURCE_OWNER", "all Function packs must have one extension owner", "<host>"),)
            )
        extension_id = next(iter(extension_ids))
        diagnostics: list[Diagnostic] = []
        parsed_artifacts: list[tuple[str, FunctionProgram, PreflightResult]] = []
        for source in sources:
            for relative, payload in sorted(source.files.items()):
                normalized = relative.replace("\\", "/")
                if normalized.startswith("/") or "../" in PurePosixPath(normalized).parts:
                    diagnostics.append(
                        Diagnostic(
                            "LYF_RESOURCE_PATH",
                            "Function resource path is not relative",
                            f"{source.pack_id}:{relative}",
                        )
                    )
                    continue
                if normalized.startswith("functions/"):
                    normalized = normalized.removeprefix("functions/")
                suffix = PurePosixPath(normalized).suffix.lower()
                if suffix in {".lyfunction", ".mcfunction"}:
                    diagnostics.append(
                        Diagnostic(
                            "migration_required",
                            f"historical Function extension {suffix} requires migration",
                            f"{source.pack_id}:{normalized}",
                        )
                    )
                    continue
                if suffix not in {".lyf", ".liteyukifunction", ".liteyukifunctions"}:
                    continue
                source_id = f"{source.pack_id}:{normalized}"
                if len(payload) > 256 * 1024:
                    diagnostics.append(Diagnostic("LYF_RESOURCE_LIMIT", "Function source exceeds 256 KiB", source_id))
                    continue
                try:
                    text = payload.decode("utf-8")
                except UnicodeDecodeError:
                    diagnostics.append(Diagnostic("LYF_PARSE_ENCODING", "Function source must be UTF-8", source_id))
                    continue
                parsed = parse(text, source_id=source_id)
                checked = check_preflight(parsed, extension_id=extension_id, libraries=self.libraries)
                diagnostics.extend(checked.diagnostics)
                if checked.program is not None:
                    parsed_artifacts.append((source_id, checked.program, checked))
        if diagnostics:
            raise FunctionHostError(tuple(diagnostics))

        seen_names: dict[str, tuple[str, str]] = {}
        artifacts: list[_SourceArtifact] = []
        targets: list[tuple[str, str]] = []
        for source_id, program, checked in parsed_artifacts:
            relative = source_id.split(":", 1)[1]
            stem = str(PurePosixPath(relative).with_suffix(""))
            local_ids: dict[str, str] = {}
            for function in program.functions:
                if function.name not in seen_names:
                    function_id = function.name
                else:
                    function_id = f"{stem}#{function.name}"
                    previous_source, _ = seen_names[function.name]
                    previous_stem = str(PurePosixPath(previous_source.split(":", 1)[1]).with_suffix(""))
                    for artifact in artifacts:
                        if artifact.source_id == previous_source:
                            artifact.function_ids[function.name] = f"{previous_stem}#{function.name}"  # type: ignore[index]
                            break
                seen_names[function.name] = (source_id, function.name)
                local_ids[function.name] = function_id
                targets.append((function_id, function.name))
            artifacts.append(_SourceArtifact(source_id, program, checked, local_ids))

        function_ids = tuple(function_id for function_id, _ in targets)
        tool_declarations: list[ToolDeclaration] = []
        tool_function_ids: dict[str, str] = {}
        prompts: list[FunctionPromptPreset] = []
        events: list[FunctionEventContribution] = []
        contribution_ids: set[str] = set()
        for artifact in artifacts:
            for tool in artifact.checked.tools:
                self._check_contribution_id(tool.id, contribution_ids, tool.span, artifact.program.source_id)
                tool_declarations.append(
                    ToolDeclaration(
                        id=tool.id,
                        description=tool.description,
                        input_schema=cast(Mapping[str, JsonValue], dict(tool.input_schema)),
                        output_schema=cast(Mapping[str, JsonValue], dict(tool.output_schema)),
                        capabilities=tool.capabilities,
                    )
                )
                tool_function_ids[tool.id] = artifact.function_ids[tool.function_name]
            for prompt in artifact.checked.prompts:
                self._check_contribution_id(prompt.id, contribution_ids, prompt.span, artifact.program.source_id)
                prompts.append(
                    FunctionPromptPreset(
                        extension_id=extension_id,
                        id=prompt.id,
                        name=prompt.name,
                        description=prompt.description,
                        prompt=prompt.prompt,
                        examples=prompt.examples,
                    )
                )
            for event_contribution in artifact.checked.events:
                function_id = artifact.function_ids[event_contribution.function_name]
                events.append(
                    FunctionEventContribution(
                        extension_id=extension_id,
                        function_id=function_id,
                        topics=(event_contribution.topic,),
                        filters=event_contribution.where,
                        parameters=tuple(
                            next(
                                function.parameters
                                for function in artifact.program.functions
                                if function.name == event_contribution.function_name
                            )
                        ),
                    )
                )

        result = FunctionPreflight(
            extension_id=extension_id,
            function_ids=function_ids,
            tool_declarations=tuple(tool_declarations),
            tool_function_ids=tool_function_ids,
            prompts=tuple(prompts),
            events=tuple(events),
        )
        self._artifacts[id(result)] = tuple(artifacts)
        return result

    def create_host(self, preflight: FunctionPreflight, bindings: FunctionHostBindings) -> FunctionHost:
        artifacts = self._artifacts.get(id(preflight))
        if artifacts is None:
            raise FunctionHostError(
                (Diagnostic("LYF_HOST_STATE", "FunctionPreflight was not created by this provider", "<host>"),)
            )
        return Alpha7FunctionHost(preflight, artifacts, bindings)

    @staticmethod
    def _check_contribution_id(id_value: str, seen: set[str], span: Any, source: str) -> None:
        if id_value in seen:
            raise FunctionHostError(
                (Diagnostic("LYF_TOOL_COLLISION", f"duplicate contribution id {id_value!r}", source, span),)
            )
        seen.add(id_value)


class Alpha7FunctionHost:
    """Lifecycle-bound host that invokes preflighted source-pack functions."""

    def __init__(
        self, preflight: FunctionPreflight, artifacts: tuple[_SourceArtifact, ...], bindings: FunctionHostBindings
    ) -> None:
        self.preflight = preflight
        self._bindings = bindings
        self._closed = False
        self._targets: dict[str, _FunctionTarget] = {}
        for artifact in artifacts:
            runtime = FunctionRuntime(artifact.checked)
            for local_name, function_id in artifact.function_ids.items():
                self._targets[function_id] = _FunctionTarget(runtime, local_name)
        self._register_tools()
        self._register_events()

    async def invoke(
        self,
        function_id: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        event: EventEnvelope | None = None,
    ) -> Any:
        if self._closed:
            raise FunctionHostError((Diagnostic("LYF_RUNTIME_CLOSED", "Function Host is closed", "<host>"),))
        target = self._targets.get(function_id)
        if target is None:
            raise FunctionHostError(
                (Diagnostic("LYF_RUNTIME_FUNCTION", f"unknown Function {function_id!r}", "<host>"),)
            )
        metadata: dict[str, Any] = {}
        if event is not None:
            metadata.update({"event_id": event.id, "runtime_id": event.runtime_id, "bot_id": event.bot_id})
            if event.actor is not None:
                metadata["actor_id"] = event.actor.id
        select_prompt: Callable[[str], object] | None = None
        if self._bindings.select_prompt is not None and event is not None:
            prompt_selector = self._bindings.select_prompt

            def select_prompt(preset_id: str) -> object:
                return prompt_selector(event, preset_id)
        context = FunctionContext(
            self.preflight.extension_id,
            function_id,
            metadata,
            emit_log=self._bindings.emit_log,
            select_prompt=select_prompt,
        )
        bound_arguments = dict(arguments or {})
        if event is not None and not bound_arguments:
            function = next(
                function
                for function in target.runtime.program.functions
                if function.name == target.local_name
            )
            if len(function.parameters) == 1:
                bound_arguments[function.parameters[0]] = event.model_dump(mode="json")
        return await target.runtime.invoke(target.local_name, bound_arguments, context=context)

    async def aclose(self) -> None:
        self._closed = True

    def _register_tools(self) -> None:
        for declaration in self.preflight.tool_declarations:

            async def callback(
                authorization: AuthorizationContext,
                arguments: Mapping[str, JsonValue],
                *,
                function_id: str = self.preflight.tool_function_ids[declaration.id],
                declaration: ToolDeclaration = declaration,
            ) -> JsonValue:
                try:
                    Draft202012Validator(dict(declaration.input_schema)).validate(dict(arguments))
                    event = (
                        self._bindings.resolve_event(authorization.event_id)
                        if self._bindings.resolve_event is not None
                        else None
                    )
                    result = await self.invoke(function_id, arguments, event=event)
                    Draft202012Validator(dict(declaration.output_schema)).validate(result)
                    return cast(JsonValue, result)
                except ValidationError as error:
                    raise FunctionHostError((Diagnostic("LYF_TOOL_SCHEMA", error.message, "<tool>"),)) from error

            callback.__name__ = f"lyf_tool_{declaration.id.rsplit('.', 1)[-1]}"
            self._bindings.register_tool(declaration, cast(ToolCallback, callback))

    def _register_events(self) -> None:
        for contribution in self.preflight.events:

            async def handler(event: EventEnvelope, *, function_id: str = contribution.function_id) -> None:
                await self.invoke(function_id, event=event)

            self._bindings.register_event(contribution, handler)


def host_provider() -> Alpha7FunctionHostProvider:
    return Alpha7FunctionHostProvider()


__all__ = ["Alpha7FunctionHost", "Alpha7FunctionHostProvider", "FunctionHostError", "host_provider"]
