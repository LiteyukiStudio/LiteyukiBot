"""Static validation and contribution collection for Alpha 7 LYF."""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from jsonschema import Draft202012Validator, SchemaError

from .ast import (
    AgentDecorator,
    AssignmentStatement,
    AwaitExpr,
    BinaryExpr,
    BindingStatement,
    BindingTarget,
    CallExpr,
    EventsDecorator,
    Expr,
    ExpressionStatement,
    FunctionDeclaration,
    FunctionProgram,
    IndexExpr,
    ListExpr,
    LiteralExpr,
    MemberExpr,
    NameExpr,
    NameTarget,
    ObjectExpr,
    PassStatement,
    ReturnStatement,
    SourceSpan,
    TupleExpr,
    TupleTarget,
    UnaryExpr,
    UnknownDecorator,
    UnsupportedStatement,
    freeze_json,
    thaw_json,
)
from .diagnostics import Diagnostic, ParseResult
from .libraries import FunctionContext, LibraryDefinition, LibraryRegistry, default_library_registry
from .parser import parse

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOPIC = re.compile(r"^(?:[A-Za-z0-9_-]+|\*)(?:\.(?:[A-Za-z0-9_-]+|\*))*$")
_MISSING = object()


@dataclass(frozen=True, slots=True)
class ToolContribution:
    id: str
    name: str
    function_name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    capabilities: tuple[str, ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class PromptContribution:
    id: str
    name: str
    function_name: str
    description: str
    prompt: str
    examples: tuple[Mapping[str, Any], ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class EventContribution:
    id: str
    function_name: str
    topic: str
    where: Mapping[str, Any]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class PreflightResult:
    program: FunctionProgram | None
    diagnostics: tuple[Diagnostic, ...]
    libraries: LibraryRegistry
    tools: tuple[ToolContribution, ...] = ()
    prompts: tuple[PromptContribution, ...] = ()
    events: tuple[EventContribution, ...] = ()

    @property
    def ok(self) -> bool:
        return self.program is not None and not any(item.is_error for item in self.diagnostics)


def _diagnostic(code: str, message: str, program: FunctionProgram, span: SourceSpan | None = None) -> Diagnostic:
    return Diagnostic(code, message, program.source_id, span)


def _argument_map(decorator: AgentDecorator | EventsDecorator) -> tuple[dict[str, Expr], list[str]]:
    values: dict[str, Expr] = {}
    duplicates: list[str] = []
    for argument in decorator.arguments:
        if argument.name in values:
            duplicates.append(argument.name)
        values[argument.name] = argument.value
    return values, duplicates


def _static_value(expression: Expr, constants: Mapping[str, Any], libraries: Mapping[str, LibraryDefinition]) -> Any:
    if isinstance(expression, LiteralExpr):
        return thaw_json(expression.value)
    if isinstance(expression, NameExpr):
        return constants.get(expression.name, _MISSING)
    if isinstance(expression, ListExpr):
        values = [_static_value(item, constants, libraries) for item in expression.items]
        return _MISSING if any(item is _MISSING for item in values) else values
    if isinstance(expression, TupleExpr):
        values = [_static_value(item, constants, libraries) for item in expression.items]
        return _MISSING if any(item is _MISSING for item in values) else tuple(values)
    if isinstance(expression, ObjectExpr):
        result: dict[str, Any] = {}
        for entry in expression.entries:
            value = _static_value(entry.value, constants, libraries)
            if value is _MISSING:
                return _MISSING
            result[entry.key] = value
        return result
    if isinstance(expression, CallExpr) and isinstance(expression.callee, MemberExpr):
        qualified = _qualified_name(expression.callee)
        if qualified is None:
            return _MISSING
        namespace, export_name = qualified
        definition = libraries.get(namespace)
        if definition is None:
            return _MISSING
        export = definition.export_map.get(export_name)
        if export is None or not export.pure:
            return _MISSING
        arguments = tuple(_static_value(item, constants, libraries) for item in expression.arguments)
        if any(item is _MISSING for item in arguments):
            return _MISSING
        frozen = tuple(freeze_json(item) for item in arguments)
        callback_result: object = export.callback(frozen, FunctionContext("<preflight>", "<static>"))
        if inspect.isawaitable(callback_result):
            return _MISSING
        return callback_result
    return _MISSING


def _qualified_name(expression: Expr) -> tuple[str, str] | None:
    parts: list[str] = []
    current: Expr = expression
    while isinstance(current, MemberExpr):
        parts.append(current.name)
        current = current.value
    if not isinstance(current, NameExpr):
        return None
    parts.append(current.name)
    parts.reverse()
    return (parts[0], ".".join(parts[1:])) if len(parts) > 1 else None


def _target_names(target: BindingTarget) -> tuple[str, ...]:
    if isinstance(target, NameTarget):
        return (target.name,)
    if isinstance(target, TupleTarget):
        return tuple(name for item in target.items for name in _target_names(item))
    return ()


def _check_expression(
    expression: Expr,
    program: FunctionProgram,
    libraries: Mapping[str, LibraryDefinition],
    names: set[str],
    diagnostics: list[Diagnostic],
    *,
    allow_await: bool,
) -> None:
    if isinstance(expression, NameExpr):
        if expression.name not in names and expression.name not in {item.name for item in program.functions}:
            diagnostics.append(
                _diagnostic("LYF_BINDING_MISSING", f"unknown binding {expression.name!r}", program, expression.span)
            )
        return
    if isinstance(expression, (LiteralExpr,)):
        return
    if isinstance(expression, (ListExpr, TupleExpr)):
        for item in expression.items:
            _check_expression(item, program, libraries, names, diagnostics, allow_await=allow_await)
        return
    if isinstance(expression, ObjectExpr):
        for entry in expression.entries:
            _check_expression(entry.value, program, libraries, names, diagnostics, allow_await=allow_await)
        return
    if isinstance(expression, (BinaryExpr, UnaryExpr, IndexExpr)):
        diagnostics.append(
            _diagnostic("LYF_UNSUPPORTED_SYNTAX", "this expression is parse-only in Alpha 7", program, expression.span)
        )
        return
    if isinstance(expression, AwaitExpr):
        if not allow_await:
            diagnostics.append(
                _diagnostic(
                    "LYF_RUNTIME_ASYNC_CONTEXT", "await is only executable in async fn", program, expression.span
                )
            )
        _check_expression(expression.value, program, libraries, names, diagnostics, allow_await=allow_await)
        return
    if isinstance(expression, MemberExpr):
        qualified = _qualified_name(expression)
        if qualified is None:
            _check_expression(expression.value, program, libraries, names, diagnostics, allow_await=allow_await)
        return
    if isinstance(expression, CallExpr):
        if isinstance(expression.callee, MemberExpr):
            qualified = _qualified_name(expression.callee)
            if qualified is None:
                diagnostics.append(
                    _diagnostic(
                        "LYF_LIBRARY_EXPORT", "library call must use namespace.export", program, expression.callee.span
                    )
                )
            else:
                namespace, export_name = qualified
                definition = libraries.get(namespace)
                export = definition.export_map.get(export_name) if definition is not None else None
                if export is None:
                    diagnostics.append(
                        _diagnostic(
                            "LYF_LIBRARY_EXPORT",
                            f"unknown Library export {namespace}.{export_name}",
                            program,
                            expression.callee.span,
                        )
                    )
                if export_name == "exec" and namespace == "terminal":
                    diagnostics.append(
                        _diagnostic(
                            "LYF_UNSUPPORTED_SYNTAX", "terminal.exec is parse-only in Alpha 7", program, expression.span
                        )
                    )
        elif isinstance(expression.callee, NameExpr):
            if expression.callee.name not in names and expression.callee.name not in {
                item.name for item in program.functions
            }:
                diagnostics.append(
                    _diagnostic(
                        "LYF_BINDING_MISSING",
                        f"unknown callable {expression.callee.name!r}",
                        program,
                        expression.callee.span,
                    )
                )
        else:
            diagnostics.append(
                _diagnostic("LYF_LIBRARY_EXPORT", "call target is not executable", program, expression.callee.span)
            )
        for argument in expression.arguments:
            _check_expression(argument, program, libraries, names, diagnostics, allow_await=allow_await)
        return
    diagnostics.append(_diagnostic("LYF_UNSUPPORTED_SYNTAX", "expression is not executable", program, expression.span))


def _check_statement_block(
    function: FunctionDeclaration,
    program: FunctionProgram,
    libraries: Mapping[str, LibraryDefinition],
    diagnostics: list[Diagnostic],
) -> None:
    names = set(function.parameters)
    const_names: set[str] = set()
    for statement in function.body:
        if isinstance(statement, UnsupportedStatement):
            code = "migration_required" if statement.kind == "migration_required" else "LYF_UNSUPPORTED_SYNTAX"
            diagnostics.append(_diagnostic(code, statement.detail, program, statement.span))
            continue
        if isinstance(statement, BindingStatement):
            _check_expression(statement.value, program, libraries, names, diagnostics, allow_await=function.is_async)
            for name in _target_names(statement.target):
                if name in names:
                    diagnostics.append(
                        _diagnostic(
                            "LYF_BINDING_DUPLICATE", f"binding {name!r} is already declared", program, statement.span
                        )
                    )
                names.add(name)
                if statement.kind == "const":
                    const_names.add(name)
            continue
        if isinstance(statement, AssignmentStatement):
            _check_expression(statement.value, program, libraries, names, diagnostics, allow_await=function.is_async)
            for name in _target_names(statement.target):
                if name not in names:
                    diagnostics.append(
                        _diagnostic(
                            "LYF_BINDING_MISSING", f"cannot assign undeclared binding {name!r}", program, statement.span
                        )
                    )
                elif name in const_names:
                    diagnostics.append(
                        _diagnostic(
                            "LYF_BINDING_CONST", f"const binding {name!r} cannot be reassigned", program, statement.span
                        )
                    )
            continue
        if isinstance(statement, ReturnStatement):
            if statement.value is not None:
                _check_expression(
                    statement.value, program, libraries, names, diagnostics, allow_await=function.is_async
                )
            continue
        if isinstance(statement, ExpressionStatement):
            _check_expression(statement.value, program, libraries, names, diagnostics, allow_await=function.is_async)


def _schema(value: Any) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    if value.get("type") != "object":
        return None
    try:
        Draft202012Validator.check_schema(dict(value))
    except SchemaError:
        return None
    return cast(Mapping[str, Any], value)


def _collect_tool(
    decorator: AgentDecorator,
    function: FunctionDeclaration,
    program: FunctionProgram,
    extension_id: str,
    constants: Mapping[str, Any],
    libraries: Mapping[str, LibraryDefinition],
    diagnostics: list[Diagnostic],
) -> ToolContribution | None:
    values, duplicates = _argument_map(decorator)
    for duplicate_name in duplicates:
        diagnostics.append(
            _diagnostic("LYF_TOOL_ARGUMENT", f"duplicate Tool option {duplicate_name!r}", program, decorator.span)
        )
    required = ("name", "description", "input", "output")
    if decorator.kind != "tool":
        return None
    missing = [name for name in required if name not in values]
    if missing:
        diagnostics.append(
            _diagnostic("LYF_TOOL_ARGUMENT", f"missing Tool options: {', '.join(missing)}", program, decorator.span)
        )
        return None
    evaluated = {name: _static_value(values[name], constants, libraries) for name in values}
    tool_name: Any = evaluated.get("name")
    description: Any = evaluated.get("description")
    input_schema = _schema(evaluated.get("input"))
    output_schema = _schema(evaluated.get("output"))
    if not isinstance(tool_name, str) or _NAME.fullmatch(tool_name) is None:
        diagnostics.append(_diagnostic("LYF_TOOL_ARGUMENT", "Tool name must be an identifier", program, decorator.span))
        return None
    if not isinstance(description, str):
        diagnostics.append(
            _diagnostic("LYF_TOOL_ARGUMENT", "Tool description must be a string", program, decorator.span)
        )
        return None
    if input_schema is None or output_schema is None:
        diagnostics.append(
            _diagnostic(
                "LYF_TOOL_SCHEMA", "Tool input and output must be Draft 2020-12 object schemas", program, decorator.span
            )
        )
        return None
    properties = input_schema.get("properties", {})
    if isinstance(properties, Mapping) and any(str(key) not in function.parameters for key in properties):
        diagnostics.append(
            _diagnostic(
                "LYF_TOOL_SIGNATURE",
                "Tool schema property is missing from the function parameters",
                program,
                function.span,
            )
        )
        return None
    capabilities_value = evaluated.get("capabilities", ())
    if not isinstance(capabilities_value, Sequence) or isinstance(capabilities_value, (str, bytes)):
        diagnostics.append(
            _diagnostic("LYF_TOOL_ARGUMENT", "Tool capabilities must be a string array", program, decorator.span)
        )
        return None
    capabilities = tuple(item for item in capabilities_value if isinstance(item, str))
    if len(capabilities) != len(capabilities_value):
        diagnostics.append(
            _diagnostic("LYF_TOOL_ARGUMENT", "Tool capabilities must be a string array", program, decorator.span)
        )
        return None
    return ToolContribution(
        f"{extension_id}.lyf.{tool_name}",
        tool_name,
        function.name,
        description,
        input_schema,
        output_schema,
        capabilities,
        decorator.span,
    )


def _collect_prompt(
    decorator: AgentDecorator,
    function: FunctionDeclaration,
    program: FunctionProgram,
    extension_id: str,
    constants: Mapping[str, Any],
    libraries: Mapping[str, LibraryDefinition],
    diagnostics: list[Diagnostic],
) -> PromptContribution | None:
    values, duplicates = _argument_map(decorator)
    for name in duplicates:
        diagnostics.append(
            _diagnostic("LYF_PROMPT_ARGUMENT", f"duplicate prompt option {name!r}", program, decorator.span)
        )
    if decorator.kind != "prompt":
        return None
    for required in ("name", "description"):
        if required not in values:
            diagnostics.append(
                _diagnostic("LYF_PROMPT_ARGUMENT", f"missing prompt option {required!r}", program, decorator.span)
            )
            return None
    if function.parameters or function.is_async or function.is_sync:
        diagnostics.append(
            _diagnostic(
                "LYF_PROMPT_NON_STATIC",
                "prompt presets must be synchronous zero-argument functions",
                program,
                function.span,
            )
        )
        return None
    name = _static_value(values["name"], constants, libraries)
    description = _static_value(values["description"], constants, libraries)
    if not isinstance(name, str) or _NAME.fullmatch(name) is None or not isinstance(description, str):
        diagnostics.append(
            _diagnostic("LYF_PROMPT_ARGUMENT", "prompt name and description must be strings", program, decorator.span)
        )
        return None
    local = dict(constants)
    result: Any = _MISSING
    for statement in function.body:
        if isinstance(statement, BindingStatement):
            value = _static_value(statement.value, local, libraries)
            if value is _MISSING or not isinstance(statement.target, NameTarget):
                diagnostics.append(
                    _diagnostic(
                        "LYF_PROMPT_NON_STATIC",
                        "prompt bindings must be static scalar or JSON values",
                        program,
                        statement.span,
                    )
                )
                return None
            local[statement.target.name] = value
        elif isinstance(statement, ReturnStatement):
            result = None if statement.value is None else _static_value(statement.value, local, libraries)
            break
        elif isinstance(statement, PassStatement):
            continue
        else:
            diagnostics.append(
                _diagnostic(
                    "LYF_PROMPT_NON_STATIC", "prompt presets may not use runtime statements", program, statement.span
                )
            )
            return None
    if (
        not isinstance(result, Mapping)
        or not isinstance(result.get("prompt"), str)
        or not isinstance(result.get("examples"), Sequence)
    ):
        diagnostics.append(
            _diagnostic(
                "LYF_PROMPT_VALUE",
                "prompt function must return {prompt: string, examples: array}",
                program,
                function.span,
            )
        )
        return None
    examples = result["examples"]
    if any(not isinstance(item, Mapping) for item in examples):
        diagnostics.append(_diagnostic("LYF_PROMPT_VALUE", "prompt examples must be objects", program, function.span))
        return None
    prompt = cast(str, result["prompt"])
    if len(prompt.encode("utf-8")) > 16 * 1024 or len(repr(examples).encode("utf-8")) > 64 * 1024:
        diagnostics.append(
            _diagnostic("LYF_PROMPT_LIMIT", "prompt preset exceeds Alpha 7 size limits", program, function.span)
        )
        return None
    return PromptContribution(
        f"{extension_id}.lyf.prompt.{name}",
        name,
        function.name,
        description,
        prompt,
        tuple(cast(Mapping[str, Any], item) for item in examples),
        decorator.span,
    )


def _collect_event(
    decorator: EventsDecorator,
    function: FunctionDeclaration,
    program: FunctionProgram,
    extension_id: str,
    constants: Mapping[str, Any],
    libraries: Mapping[str, LibraryDefinition],
    diagnostics: list[Diagnostic],
) -> EventContribution | None:
    topic = _static_value(decorator.topic, constants, libraries)
    if not isinstance(topic, str) or _TOPIC.fullmatch(topic) is None:
        diagnostics.append(
            _diagnostic("LYF_EVENT_TOPIC", "event topic must be a literal dotted topic", program, decorator.topic.span)
        )
        return None
    values, duplicates = _argument_map(decorator)
    for name in duplicates:
        diagnostics.append(
            _diagnostic("LYF_EVENT_ARGUMENT", f"duplicate event option {name!r}", program, decorator.span)
        )
    unknown = set(values) - {"where"}
    if unknown:
        diagnostics.append(
            _diagnostic(
                "LYF_EVENT_ARGUMENT",
                f"unsupported event options: {', '.join(sorted(unknown))}",
                program,
                decorator.span,
            )
        )
        return None
    where = {} if "where" not in values else _static_value(values["where"], constants, libraries)
    if not isinstance(where, Mapping):
        diagnostics.append(
            _diagnostic("LYF_EVENT_FILTER", "event where must be a JSON object", program, decorator.span)
        )
        return None
    if len(function.parameters) > 1:
        diagnostics.append(
            _diagnostic("LYF_EVENT_SIGNATURE", "event handlers accept zero or one parameter", program, function.span)
        )
        return None
    return EventContribution(f"{extension_id}.lyf.event.{function.name}", function.name, topic, where, decorator.span)


def preflight(
    source: str | ParseResult | FunctionProgram,
    *,
    source_id: str = "<memory>",
    extension_id: str = "extension",
    libraries: LibraryRegistry | None = None,
) -> PreflightResult:
    """Resolve Libraries, validate a program and collect static contributions."""

    registry = libraries or default_library_registry()
    parse_result: ParseResult | None = source if isinstance(source, ParseResult) else None
    if isinstance(source, str):
        parse_result = parse(source, source_id=source_id)
    program = (
        source.program if isinstance(source, ParseResult) else source if isinstance(source, FunctionProgram) else None
    )
    diagnostics = list(parse_result.diagnostics if parse_result is not None else ())
    if program is None:
        return PreflightResult(None, tuple(diagnostics), registry)

    resolved: dict[str, LibraryDefinition] = {}
    seen_namespaces: set[str] = set()
    for use in program.uses:
        if use.namespace in seen_namespaces:
            diagnostics.append(
                _diagnostic(
                    "LYF_PROVIDER_DUPLICATE",
                    f"Library namespace {use.namespace!r} is imported more than once",
                    program,
                    use.span,
                )
            )
            continue
        seen_namespaces.add(use.namespace)
        matches = registry.matches(use.namespace)
        selected = registry.resolve(use.namespace, use.provider)
        if use.provider is None and len(matches) != 1:
            code = "LYF_PROVIDER_MISSING" if not matches else "LYF_PROVIDER_AMBIGUOUS"
            diagnostics.append(
                _diagnostic(code, f"use {use.namespace} requires exactly one Provider", program, use.span)
            )
        elif selected is None:
            diagnostics.append(
                _diagnostic(
                    "LYF_PROVIDER_MISSING",
                    f"Provider {use.namespace}@{use.provider} is not installed",
                    program,
                    use.span,
                )
            )
        else:
            resolved[use.namespace] = selected

    names: set[str] = set()
    constants: dict[str, Any] = {}
    for binding in program.module_bindings:
        for name in _target_names(binding.target):
            if name in names:
                diagnostics.append(
                    _diagnostic(
                        "LYF_BINDING_DUPLICATE", f"module binding {name!r} is already declared", program, binding.span
                    )
                )
            names.add(name)
        value = _static_value(binding.value, constants, resolved)
        if value is not _MISSING and isinstance(binding.target, NameTarget):
            constants[binding.target.name] = value
    for declaration in program.declarations:
        if isinstance(declaration, AssignmentStatement):
            diagnostics.append(
                _diagnostic(
                    "LYF_BINDING_MISSING",
                    "module-level implicit assignments are not supported; declare let, val or const",
                    program,
                    declaration.span,
                )
            )
        elif isinstance(declaration, UnsupportedStatement):
            code = "migration_required" if declaration.kind == "migration_required" else "LYF_UNSUPPORTED_SYNTAX"
            diagnostics.append(_diagnostic(code, declaration.detail, program, declaration.span))

    function_names: set[str] = set()
    for function in program.functions:
        if function.name in function_names:
            diagnostics.append(
                _diagnostic(
                    "LYF_BINDING_DUPLICATE",
                    f"function {function.name!r} is declared more than once",
                    program,
                    function.span,
                )
            )
        function_names.add(function.name)
        if function.is_sync:
            diagnostics.append(
                _diagnostic("LYF_UNSUPPORTED_SYNTAX", "sync fn is parse-only in Alpha 7", program, function.span)
            )
        _check_statement_block(function, program, resolved, diagnostics)

    tools: list[ToolContribution] = []
    prompts: list[PromptContribution] = []
    events: list[EventContribution] = []
    contribution_ids: set[str] = set()
    for function in program.functions:
        for decorator in function.decorators:
            contribution: ToolContribution | PromptContribution | EventContribution | None = None
            if isinstance(decorator, AgentDecorator):
                contribution = (
                    _collect_tool(decorator, function, program, extension_id, constants, resolved, diagnostics)
                    if decorator.kind == "tool"
                    else _collect_prompt(decorator, function, program, extension_id, constants, resolved, diagnostics)
                )
            elif isinstance(decorator, EventsDecorator):
                contribution = _collect_event(
                    decorator, function, program, extension_id, constants, resolved, diagnostics
                )
            elif isinstance(decorator, UnknownDecorator):
                diagnostics.append(
                    _diagnostic("LYF_TOOL_DECORATOR", f"unknown decorator @{decorator.name}", program, decorator.span)
                )
            if contribution is None:
                continue
            if contribution.id in contribution_ids:
                diagnostics.append(
                    _diagnostic(
                        "LYF_TOOL_COLLISION",
                        f"duplicate contribution id {contribution.id!r}",
                        program,
                        contribution.span,
                    )
                )
                continue
            contribution_ids.add(contribution.id)
            if isinstance(contribution, ToolContribution):
                tools.append(contribution)
            elif isinstance(contribution, PromptContribution):
                prompts.append(contribution)
            else:
                events.append(contribution)

    return PreflightResult(program, tuple(diagnostics), registry, tuple(tools), tuple(prompts), tuple(events))


__all__ = [
    "EventContribution",
    "PreflightResult",
    "PromptContribution",
    "ToolContribution",
    "preflight",
]
