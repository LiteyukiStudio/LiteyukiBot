"""Bounded evaluator for the executable Alpha 7 LYF subset."""

from __future__ import annotations

import asyncio
import inspect
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .ast import (
    AssignmentStatement,
    AwaitExpr,
    BinaryExpr,
    BindingStatement,
    BindingTarget,
    CallExpr,
    DiscardTarget,
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
    ReturnStatement,
    SourceSpan,
    Statement,
    TupleExpr,
    TupleTarget,
    UnaryExpr,
    UnsupportedStatement,
    freeze_json,
    thaw_json,
)
from .diagnostics import Diagnostic
from .libraries import FunctionContext, LibraryDefinition, LibraryExport, LibraryRegistry, default_library_registry
from .preflight import PreflightResult, preflight

_INTERPOLATION = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")
_BRACES = re.compile(r"\{([^{}]*)\}")


class FunctionRuntimeError(RuntimeError):
    """Runtime failure carrying the same stable diagnostic shape as preflight."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        """Initialize the function runtime error.

        Args:
            diagnostic: The diagnostic value used by the operation.

        Returns:
            None.
        """
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class _ReturnSignal(Exception):
    """Represent the return signal contract."""
    def __init__(self, value: Any) -> None:
        """Initialize the return signal.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_ReturnSignal.__init__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        self.value = value


@dataclass(slots=True)
class _Frame:
    """Represent the frame contract."""
    function: FunctionDeclaration
    values: dict[str, Any]
    constants: set[str]
    context: FunctionContext
    depth: int


def _runtime_value(value: Any) -> Any:
    """Implement the runtime value operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_runtime_value`. It delegates to `isfinite`,
        `_runtime_value`, `items` while keeping intermediate state local to the owning operation.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("numbers must be finite")
        return value
    if isinstance(value, Mapping):
        return {str(key): _runtime_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_runtime_value(item) for item in value)
    raise TypeError(f"value is not JSON-safe: {type(value).__name__}")


def _qualified_name(expression: Expr) -> tuple[str, str] | None:
    """Implement the qualified name operation for the component.

    Args:
        expression: The expression value used by the operation.

    Returns:
        The `tuple[str, str] | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_qualified_name`. It delegates to `append`, `reverse`,
        `join` while keeping intermediate state local to the owning operation.
    """
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
    """Implement the target names operation for the component.

    Args:
        target: Target value or location for the operation.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_target_names`. It delegates to `_target_names` while
        keeping intermediate state local to the owning operation.
    """
    if isinstance(target, NameTarget):
        return (target.name,)
    if isinstance(target, TupleTarget):
        return tuple(name for item in target.items for name in _target_names(item))
    return ()


class FunctionRuntime:
    """Execute a preflighted LYF program with bounded recursion and JSON values."""

    def __init__(
        self,
        program: PreflightResult | FunctionProgram,
        *,
        libraries: LibraryRegistry | None = None,
        max_depth: int = 32,
    ) -> None:
        """Initialize the function runtime.

        Args:
            program: The program value used by the operation.
            libraries: The libraries value used by the operation.
            max_depth: The max depth value used by the operation.

        Returns:
            None.
        """
        checked = program if isinstance(program, PreflightResult) else preflight(program, libraries=libraries)
        if checked.program is None:
            raise ValueError("FunctionRuntime requires a parsed LYF program")
        if not checked.ok:
            raise ValueError("FunctionRuntime requires a preflighted LYF program without errors")
        self.program = checked.program
        self.preflight = checked
        self.libraries = libraries or checked.libraries or default_library_registry()
        self.max_depth = max_depth
        self._functions = {item.name: item for item in self.program.functions}
        self._resolved_libraries = self._resolve_libraries()

    async def invoke(
        self,
        function_name: str,
        arguments: Mapping[str, Any] | Sequence[Any] = (),
        *,
        context: FunctionContext | None = None,
    ) -> Any:
        """Invoke the function runtime operation.

        Args:
            function_name: The function name value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.
            context: Runtime or authorization context for the operation.

        Returns:
            The `Any` result produced by the operation.
        """
        function = self._functions.get(function_name)
        if function is None:
            raise self._error("LYF_RUNTIME_FUNCTION", f"unknown function {function_name!r}", None)
        context = context or FunctionContext(self.program.source_id, function_name)
        values = self._bind_arguments(function, arguments)
        frame = _Frame(function, values, set(), context, 0)
        try:
            module_values, module_constants = await self._module_environment(context)
            frame.values = {**module_values, **frame.values}
            frame.constants = module_constants
            return await self._run_function(frame)
        except FunctionRuntimeError:
            raise
        except _ReturnSignal as returned:
            return returned.value
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise self._error("LYF_RUNTIME_EXECUTION", str(error), function.span) from error

    def _resolve_libraries(self) -> dict[str, LibraryDefinition]:
        """Resolve libraries.

        Returns:
            The `dict[str, LibraryDefinition]` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._resolve_libraries`. It delegates to
            `resolve` while keeping intermediate state local to the owning operation.
        """
        resolved: dict[str, LibraryDefinition] = {}
        for use in self.program.uses:
            definition = self.libraries.resolve(use.namespace, use.provider)
            if definition is not None:
                resolved[use.namespace] = definition
        return resolved

    def _bind_arguments(
        self, function: FunctionDeclaration, arguments: Mapping[str, Any] | Sequence[Any]
    ) -> dict[str, Any]:
        """Bind arguments.

        Args:
            function: The function value used by the operation.
            arguments: JSON-safe arguments supplied to the operation.

        Returns:
            The `dict[str, Any]` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._bind_arguments`. It delegates to `sorted`,
            `_error`, `_runtime_value`, `zip` while keeping intermediate state local to the owning
            operation.
        """
        if isinstance(arguments, Mapping):
            unknown = set(arguments) - set(function.parameters)
            missing = set(function.parameters) - set(arguments)
            if unknown or missing:
                detail = f"unknown={sorted(unknown)}, missing={sorted(missing)}"
                raise self._error(
                    "LYF_RUNTIME_ARGUMENTS", f"invalid arguments for {function.name}: {detail}", function.span
                )
            values = {name: _runtime_value(arguments[name]) for name in function.parameters}
        else:
            if isinstance(arguments, (str, bytes, bytearray)) or len(arguments) != len(function.parameters):
                raise self._error(
                    "LYF_RUNTIME_ARGUMENTS", f"expected {len(function.parameters)} positional arguments", function.span
                )
            values = {name: _runtime_value(value) for name, value in zip(function.parameters, arguments, strict=True)}
        return values

    async def _module_environment(self, context: FunctionContext) -> tuple[dict[str, Any], set[str]]:
        """Implement the module environment operation for the function runtime.

        Args:
            context: Runtime or authorization context for the operation.

        Returns:
            The `tuple[dict[str, Any], set[str]]` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._module_environment`. It delegates to
            `_empty_span`, `_Frame`, `_error`, `_eval` while keeping intermediate state local to the owning
            operation.
        """
        values: dict[str, Any] = {}
        constants: set[str] = set()
        module = FunctionDeclaration(
            self.program.functions[0].span if self.program.functions else self._empty_span(), "<module>", (), ()
        )
        frame = _Frame(module, values, constants, context, 0)
        for declaration in self.program.module_bindings:
            if not isinstance(declaration.target, NameTarget):
                raise self._error("LYF_BINDING_TARGET", "module bindings require a single name", declaration.span)
            if declaration.target.name in values:
                raise self._error(
                    "LYF_BINDING_DUPLICATE",
                    f"module binding {declaration.target.name!r} is duplicated",
                    declaration.span,
                )
            values[declaration.target.name] = await self._eval(declaration.value, frame, await_result=False)
            if declaration.kind == "const":
                constants.add(declaration.target.name)
        return values, constants

    async def _run_function(self, frame: _Frame) -> Any:
        """Run function.

        Args:
            frame: The frame value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._run_function`. It delegates to `_error`,
            `_run_block` while keeping intermediate state local to the owning operation.
        """
        if frame.depth >= self.max_depth:
            raise self._error("LYF_RUNTIME_DEPTH", "maximum function nesting depth exceeded", frame.function.span)
        try:
            await self._run_block(frame, frame.function.body)
        except _ReturnSignal as returned:
            return returned.value
        return None

    async def _run_block(self, frame: _Frame, statements: tuple[Statement, ...]) -> None:
        """Run block.

        Args:
            frame: The frame value used by the operation.
            statements: The statements value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `FunctionRuntime._run_block`. It delegates to
            `_run_statement` while keeping intermediate state local to the owning operation.
        """
        for statement in statements:
            await self._run_statement(frame, statement)

    async def _run_statement(self, frame: _Frame, statement: Statement) -> None:
        """Run statement.

        Args:
            frame: The frame value used by the operation.
            statement: The statement value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `FunctionRuntime._run_statement`. It delegates to `_error`,
            `_eval`, `_bind_target`, `_assign_target` while keeping intermediate state local to the owning
            operation.
        """
        if isinstance(statement, UnsupportedStatement):
            code = "migration_required" if statement.kind == "migration_required" else "LYF_UNSUPPORTED_SYNTAX"
            raise self._error(code, statement.detail, statement.span)
        if isinstance(statement, BindingStatement):
            value = await self._eval(statement.value, frame, await_result=False)
            self._bind_target(frame, statement.target, value, statement.kind == "const", statement.span)
            return
        if isinstance(statement, AssignmentStatement):
            value = await self._eval(statement.value, frame, await_result=False)
            self._assign_target(frame, statement.target, value, statement.span)
            return
        if isinstance(statement, ReturnStatement):
            value = None if statement.value is None else await self._eval(statement.value, frame, await_result=False)
            raise _ReturnSignal(value)
        if isinstance(statement, ExpressionStatement):
            await self._eval(statement.value, frame, await_result=False)
            return
        raise self._error("LYF_RUNTIME_EXECUTION", "unknown statement", statement.span)

    def _bind_target(self, frame: _Frame, target: BindingTarget, value: Any, immutable: bool, span: SourceSpan) -> None:
        """Bind target.

        Args:
            frame: The frame value used by the operation.
            target: Target value or location for the operation.
            value: Value to validate, transform, or store.
            immutable: The immutable value used by the operation.
            span: The span value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `FunctionRuntime._bind_target`. It delegates to `_error`,
            `add`, `zip`, `_bind_target` while keeping intermediate state local to the owning operation.
        """
        if isinstance(target, NameTarget):
            if target.name in frame.values:
                raise self._error("LYF_BINDING_DUPLICATE", f"binding {target.name!r} is already declared", span)
            frame.values[target.name] = value
            if immutable:
                frame.constants.add(target.name)
            return
        if isinstance(target, DiscardTarget):
            return
        if isinstance(target, TupleTarget):
            if not isinstance(value, (tuple, list)) or len(value) != len(target.items):
                raise self._error(
                    "LYF_BINDING_DESTRUCTURE", "tuple destructuring length does not match the value", span
                )
            for item, item_value in zip(target.items, value, strict=True):
                self._bind_target(frame, item, item_value, immutable, span)
            return
        raise self._error("LYF_BINDING_TARGET", "unsupported binding target", span)

    def _assign_target(self, frame: _Frame, target: BindingTarget, value: Any, span: SourceSpan) -> None:
        """Implement the assign target operation for the function runtime.

        Args:
            frame: The frame value used by the operation.
            target: Target value or location for the operation.
            value: Value to validate, transform, or store.
            span: The span value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `FunctionRuntime._assign_target`. It delegates to `_error`,
            `zip`, `_assign_target` while keeping intermediate state local to the owning operation.
        """
        if isinstance(target, NameTarget):
            if target.name not in frame.values:
                raise self._error("LYF_BINDING_MISSING", f"cannot assign undeclared binding {target.name!r}", span)
            if target.name in frame.constants:
                raise self._error("LYF_BINDING_CONST", f"const binding {target.name!r} cannot be reassigned", span)
            frame.values[target.name] = value
            return
        if isinstance(target, DiscardTarget):
            return
        if isinstance(target, TupleTarget):
            if not isinstance(value, (tuple, list)) or len(value) != len(target.items):
                raise self._error(
                    "LYF_BINDING_DESTRUCTURE", "tuple destructuring length does not match the value", span
                )
            for item, item_value in zip(target.items, value, strict=True):
                self._assign_target(frame, item, item_value, span)
            return
        raise self._error("LYF_BINDING_TARGET", "unsupported assignment target", span)

    async def _eval(self, expression: Expr, frame: _Frame, *, await_result: bool) -> Any:
        """Implement the eval operation for the function runtime.

        Args:
            expression: The expression value used by the operation.
            frame: The frame value used by the operation.
            await_result: The await result value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._eval`. It delegates to `_interpolate`,
            `thaw_json`, `_error`, `_eval` while keeping intermediate state local to the owning operation.
        """
        if isinstance(expression, LiteralExpr):
            return self._interpolate(thaw_json(expression.value), frame, expression.span)
        if isinstance(expression, NameExpr):
            if expression.name not in frame.values:
                raise self._error("LYF_BINDING_MISSING", f"unknown binding {expression.name!r}", expression.span)
            return frame.values[expression.name]
        if isinstance(expression, ListExpr):
            return [await self._eval(item, frame, await_result=False) for item in expression.items]
        if isinstance(expression, TupleExpr):
            values = [await self._eval(item, frame, await_result=False) for item in expression.items]
            return tuple(values)
        if isinstance(expression, ObjectExpr):
            return {item.key: await self._eval(item.value, frame, await_result=False) for item in expression.entries}
        if isinstance(expression, MemberExpr):
            if _qualified_name(expression) is not None:
                raise self._error(
                    "LYF_RUNTIME_LIBRARY", "a Library export can only be used as a call target", expression.span
                )
            value = await self._eval(expression.value, frame, await_result=False)
            if not isinstance(value, Mapping) or expression.name not in value:
                raise self._error("LYF_RUNTIME_VALUE", f"member {expression.name!r} is not available", expression.span)
            return value[expression.name]
        if isinstance(expression, IndexExpr):
            raise self._error("LYF_UNSUPPORTED_SYNTAX", "indexing is parse-only in Alpha 7", expression.span)
        if isinstance(expression, AwaitExpr):
            return await self._eval_await(expression.value, frame)
        if isinstance(expression, CallExpr):
            return await self._eval_call(expression, frame, await_result=await_result)
        if isinstance(expression, (BinaryExpr, UnaryExpr)):
            raise self._error("LYF_UNSUPPORTED_SYNTAX", "operators are parse-only in Alpha 7", expression.span)
        raise self._error("LYF_RUNTIME_EXECUTION", "unknown expression", expression.span)

    async def _eval_await(self, expression: Expr, frame: _Frame) -> Any:
        """Implement the eval await operation for the function runtime.

        Args:
            expression: The expression value used by the operation.
            frame: The frame value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._eval_await`. It delegates to `_eval_call`,
            `_eval`, `isawaitable`, `_error` while keeping intermediate state local to the owning operation.
        """
        if isinstance(expression, CallExpr):
            return await self._eval_call(expression, frame, await_result=True)
        result = await self._eval(expression, frame, await_result=False)
        if not inspect.isawaitable(result):
            raise self._error("LYF_RUNTIME_AWAIT", "await requires an async call", expression.span)
        return await result

    async def _eval_call(self, expression: CallExpr, frame: _Frame, *, await_result: bool) -> Any:
        """Implement the eval call operation for the function runtime.

        Args:
            expression: The expression value used by the operation.
            frame: The frame value used by the operation.
            await_result: The await result value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._eval_call`. It delegates to `_eval`,
            `_qualified_name`, `_error`, `get` while keeping intermediate state local to the owning
            operation.
        """
        arguments = tuple([await self._eval(item, frame, await_result=False) for item in expression.arguments])
        if isinstance(expression.callee, MemberExpr):
            qualified = _qualified_name(expression.callee)
            if qualified is None:
                raise self._error(
                    "LYF_RUNTIME_LIBRARY", "Library call must use namespace.export", expression.callee.span
                )
            namespace, export_name = qualified
            definition = self._resolved_libraries.get(namespace)
            export = definition.export_map.get(export_name) if definition is not None else None
            if export is None:
                raise self._error(
                    "LYF_RUNTIME_LIBRARY", f"unknown Library export {namespace}.{export_name}", expression.callee.span
                )
            if namespace == "terminal" and export_name == "exec":
                raise self._error("LYF_UNSUPPORTED_SYNTAX", "terminal.exec is parse-only in Alpha 7", expression.span)
            try:
                result = export.callback(tuple(freeze_json(item) for item in arguments), frame.context)
            except Exception as error:
                raise self._error("LYF_RUNTIME_LIBRARY", str(error), expression.span) from error
            return await self._resolve_async_result(result, export, expression.span, await_result)
        if isinstance(expression.callee, NameExpr):
            function = self._functions.get(expression.callee.name)
            if function is None:
                raise self._error(
                    "LYF_RUNTIME_FUNCTION", f"unknown function {expression.callee.name!r}", expression.callee.span
                )
            if function.is_async and not await_result:
                raise self._error(
                    "LYF_RUNTIME_ASYNC_CALL",
                    f"async function {function.name!r} must be awaited",
                    expression.callee.span,
                )
            if len(arguments) != len(function.parameters):
                raise self._error(
                    "LYF_RUNTIME_ARGUMENTS", f"expected {len(function.parameters)} arguments", expression.span
                )
            values = {name: _runtime_value(value) for name, value in zip(function.parameters, arguments, strict=True)}
            child = _Frame(function, values, set(), frame.context, frame.depth + 1)
            result = await self._run_function_with_environment(child)
            return result
        raise self._error("LYF_RUNTIME_FUNCTION", "call target is not executable", expression.callee.span)

    async def _run_function_with_environment(self, frame: _Frame) -> Any:
        """Run function with environment.

        Args:
            frame: The frame value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._run_function_with_environment`. It
            delegates to `_module_environment`, `_run_function` while keeping intermediate state local to
            the owning operation.
        """
        module_values, module_constants = await self._module_environment(frame.context)
        frame.values = {**module_values, **frame.values}
        frame.constants = module_constants
        return await self._run_function(frame)

    async def _resolve_async_result(
        self,
        result: object,
        export: LibraryExport,
        span: SourceSpan,
        await_result: bool,
    ) -> Any:
        """Resolve async result.

        Args:
            result: Result value produced by the preceding operation.
            export: The export value used by the operation.
            span: The span value used by the operation.
            await_result: The await result value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._resolve_async_result`. It delegates to
            `isawaitable`, `_error`, `iscoroutine`, `close` while keeping intermediate state local to the
            owning operation.
        """
        if inspect.isawaitable(result):
            if not await_result and not export.is_async:
                raise self._error("LYF_RUNTIME_ASYNC_CALL", "Library callback returned an awaitable unexpectedly", span)
            if not await_result:
                if inspect.iscoroutine(result):
                    result.close()
                raise self._error("LYF_RUNTIME_ASYNC_CALL", "async Library call must be awaited", span)
            result = await result
        elif export.is_async and await_result:
            raise self._error("LYF_RUNTIME_AWAIT", "async Library export did not return an awaitable", span)
        elif export.is_async and not await_result:
            raise self._error("LYF_RUNTIME_ASYNC_CALL", "async Library call must be awaited", span)
        return _runtime_value(result)

    def _interpolate(self, value: Any, frame: _Frame, span: SourceSpan) -> Any:
        """Implement the interpolate operation for the function runtime.

        Args:
            value: Value to validate, transform, or store.
            frame: The frame value used by the operation.
            span: The span value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._interpolate`. It delegates to `group`,
            `finditer`, `fullmatch`, `_error` while keeping intermediate state local to the owning
            operation.
        """
        if not isinstance(value, str) or "{" not in value:
            return value
        invalid = [
            match.group(1) for match in _BRACES.finditer(value) if _INTERPOLATION.fullmatch(match.group(0)) is None
        ]
        if invalid:
            raise self._error("LYF_PARSE_INTERPOLATION", "string interpolation only accepts one binding name", span)

        def replace(match: re.Match[str]) -> str:
            """Implement the replace operation for the interpolate.

            Args:
                match: The match value used by the operation.

            Returns:
                The `str` result produced by the operation.

            Notes:
                Internal implementation detail for `FunctionRuntime._interpolate.replace`. It delegates to
                `group`, `_error` while keeping intermediate state local to the owning operation.
            """
            name = match.group(1)
            if name not in frame.values:
                raise self._error("LYF_BINDING_MISSING", f"unknown interpolation binding {name!r}", span)
            return str(frame.values[name])

        return _INTERPOLATION.sub(replace, value)

    def _error(self, code: str, message: str, span: SourceSpan | None) -> FunctionRuntimeError:
        """Implement the error operation for the function runtime.

        Args:
            code: The code value used by the operation.
            message: Message content associated with the operation.
            span: The span value used by the operation.

        Returns:
            The `FunctionRuntimeError` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._error`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        return FunctionRuntimeError(Diagnostic(code, message, self.program.source_id, span))

    @staticmethod
    def _empty_span() -> SourceSpan:
        """Implement the empty span operation for the function runtime.

        Returns:
            The `SourceSpan` result produced by the operation.

        Notes:
            Internal implementation detail for `FunctionRuntime._empty_span`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        from .ast import ZERO_SPAN

        return ZERO_SPAN


__all__ = ["FunctionRuntime", "FunctionRuntimeError"]
