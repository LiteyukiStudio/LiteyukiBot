"""Interpreter for the bounded LiteyukiBot v6 resource-function language."""

from __future__ import annotations

import ast
import asyncio
import inspect
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from liteyukibot.functions import FunctionCall, FunctionDocument, FunctionInvoker


class V6FunctionError(RuntimeError):
    """Base error for v6 resource-function execution."""


class V6FunctionSyntaxError(V6FunctionError):
    """Raised when the v6 function syntax contract cannot be satisfied."""
    pass


class V6FunctionCapabilityError(V6FunctionError):
    """Raised when the v6 function capability contract cannot be satisfied."""
    pass


class V6FunctionRuntimeError(V6FunctionError):
    """Raised when the v6 function runtime contract cannot be satisfied."""
    pass


type CapabilityMethod = Callable[..., object]

_PLACEHOLDER = re.compile(r"\$\{([^{}]*)\}")
_ESCAPED_EQUALS = "__LITEYUKI_ESCAPED_EQUALS__"


@dataclass(frozen=True, slots=True)
class _Statement:
    """Represent the statement contract."""
    head: str
    args: tuple[str, ...]
    kwargs: Mapping[str, Any]
    tail: str


@dataclass(frozen=True, slots=True)
class _Program:
    """Represent the program contract."""
    lines: tuple[str, ...]


@dataclass(slots=True)
class _Execution:
    """Represent the execution contract."""
    call: FunctionCall
    invoke: FunctionInvoker
    variables: dict[str, Any] = field(init=False)
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Validate and normalize the execution after initialization.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_Execution.__post_init__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        self.variables = dict(self.call.arguments)

    async def run(self, program: _Program) -> None:
        """Run the execution until its lifecycle completes.

        Args:
            program: The program value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_Execution.run`. It delegates to `_execute`, `cancel_tasks`
            while keeping intermediate state local to the owning operation.
        """
        try:
            for source in program.lines:
                if await self._execute(source):
                    return
        except BaseException:
            await self.cancel_tasks()
            raise

    async def _execute(self, source: str) -> bool:
        """Execute the execution operation.

        Args:
            source: Source value or location to process.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `_Execution._execute`. It delegates to `_parse`, `_render`,
            `update`, `_required_argument` while keeping intermediate state local to the owning operation.
        """
        statement = self._parse(self._render(source))
        if statement.head == "var":
            self.variables.update(statement.kwargs)
        elif statement.head == "api":
            api = self._required_argument(statement, "api")
            await self._capability("call_api", api, statement.kwargs)
        elif statement.head == "cmd":
            await self._capability("run_command", statement.tail)
        elif statement.head == "function":
            function_id = self._required_argument(statement, "function")
            await self.invoke(
                FunctionCall(
                    function_id,
                    statement.kwargs,
                    positional=statement.args[2:],
                    capabilities=self.call.capabilities,
                )
            )
        elif statement.head == "sleep":
            seconds = self._required_argument(statement, "sleep")
            try:
                delay = float(seconds)
            except ValueError as error:
                raise V6FunctionSyntaxError(f"sleep requires a number, got {seconds!r}") from error
            if delay < 0:
                raise V6FunctionSyntaxError("sleep requires a non-negative number")
            await asyncio.sleep(delay)
        elif statement.head == "nohup":
            if not statement.tail:
                raise V6FunctionSyntaxError("nohup requires an instruction")
            if self.call.task_owner is None:
                raise V6FunctionRuntimeError("v6 function nohup requires a dispatcher task owner")
            task = self.call.task_owner.start(self._execute_background(statement.tail), name="v6-nohup")
            self.tasks.add(task)
        elif statement.head == "await":
            await self.await_tasks()
        elif statement.head == "end":
            await self.cancel_tasks()
            return True
        else:
            raise V6FunctionSyntaxError(f"unsupported v6 function instruction: {statement.head!r}")
        return False

    async def _execute_background(self, source: str) -> None:
        """Execute background.

        Args:
            source: Source value or location to process.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_Execution._execute_background`. It delegates to `_execute`
            while keeping intermediate state local to the owning operation.
        """
        await self._execute(source)

    def _render(self, source: str) -> str:
        """Render the execution operation.

        Args:
            source: Source value or location to process.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `_Execution._render`. It delegates to `sub`, `get`, `group`,
            `format` while keeping intermediate state local to the owning operation.
        """
        if "${" in source:
            return _PLACEHOLDER.sub(lambda match: str(self.variables.get(match.group(1), "")), source)
        try:
            return source.format(*self.call.positional, **self.variables)
        except IndexError, KeyError, ValueError:
            return source

    def _parse(self, source: str) -> _Statement:
        """Parse the execution operation.

        Args:
            source: Source value or location to process.

        Returns:
            The `_Statement` result produced by the operation.

        Notes:
            Internal implementation detail for `_Execution._parse`. It delegates to `split`, `replace`,
            `enumerate`, `_literal_or_variable` while keeping intermediate state local to the owning
            operation.
        """
        tokens = source.replace(r"\=", _ESCAPED_EQUALS).split(" ")
        head = tokens[0]
        args: list[str] = []
        kwargs: dict[str, Any] = {}
        for index, token in enumerate(tokens):
            if "=" in token:
                key, raw_value = token.split("=", 1)
                if not key:
                    raise V6FunctionSyntaxError("function keyword names must not be empty")
                value = raw_value.replace(_ESCAPED_EQUALS, "=")
                kwargs[key] = self._literal_or_variable(value)
            else:
                value = token.replace(_ESCAPED_EQUALS, "=")
                if index == 0:
                    head = value
                args.append(value)
        tail = source.split(" ", 1)[1] if " " in source else ""
        return _Statement(head=head, args=tuple(args), kwargs=kwargs, tail=tail)

    def _literal_or_variable(self, value: str) -> Any:
        """Implement the literal or variable operation for the execution.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `_Execution._literal_or_variable`. It delegates to
            `literal_eval`, `get` while keeping intermediate state local to the owning operation.
        """
        try:
            return ast.literal_eval(value)
        except SyntaxError, ValueError:
            return self.variables.get(value, value)

    @staticmethod
    def _required_argument(statement: _Statement, instruction: str) -> str:
        """Implement the required argument operation for the execution.

        Args:
            statement: The statement value used by the operation.
            instruction: The instruction value used by the operation.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `_Execution._required_argument`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        if len(statement.args) < 2 or not statement.args[1]:
            raise V6FunctionSyntaxError(f"{instruction} requires an argument")
        return statement.args[1]

    async def _capability(self, name: str, *args: object) -> object:
        """Implement the capability operation for the execution.

        Args:
            name: Stable name used to identify the value.
            *args: The args value used by the operation.

        Returns:
            The `object` result produced by the operation.

        Notes:
            Internal implementation detail for `_Execution._capability`. It delegates to `getattr`,
            `callable`, `cast`, `isawaitable` while keeping intermediate state local to the owning
            operation.
        """
        capability = self.call.capabilities
        method = getattr(capability, name, None)
        if not callable(method):
            raise V6FunctionCapabilityError(f"v6 function instruction requires the {name} capability")
        result = cast(CapabilityMethod, method)(*args)
        if not inspect.isawaitable(result):
            raise V6FunctionCapabilityError(f"the {name} capability must return an awaitable")
        return await result

    async def await_tasks(self) -> None:
        """Implement the await tasks operation for the execution.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_Execution.await_tasks`. It delegates to `gather`,
            `difference_update` while keeping intermediate state local to the owning operation.
        """
        tasks = tuple(self.tasks)
        try:
            if tasks:
                await asyncio.gather(*tasks)
        finally:
            self.tasks.difference_update(tasks)

    async def cancel_tasks(self) -> None:
        """Implement the cancel tasks operation for the execution.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_Execution.cancel_tasks`. It delegates to `cancel`,
            `gather`, `difference_update` while keeping intermediate state local to the owning operation.
        """
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.difference_update(tasks)


class V6FunctionExecutor:
    """Execute v6 `.lyf`, `.lyfunction`, and `.mcfunction` resource files."""

    extensions: tuple[str, ...] = (".lyf", ".lyfunction", ".mcfunction")

    def __init__(self) -> None:
        """Initialize the v6 function executor.

        Returns:
            None.
        """
        self._programs: dict[int, _Program] = {}

    async def execute(
        self,
        document: FunctionDocument,
        call: FunctionCall,
        invoke: FunctionInvoker,
    ) -> None:
        """Execute one request through the v6 function executor.

        Args:
            document: The document value used by the operation.
            call: The call value used by the operation.
            invoke: The invoke value used by the operation.

        Returns:
            None.
        """
        await _Execution(call, invoke).run(self._program(document))

    def _program(self, document: FunctionDocument) -> _Program:
        """Implement the program operation for the v6 function executor.

        Args:
            document: The document value used by the operation.

        Returns:
            The `_Program` result produced by the operation.

        Notes:
            Internal implementation detail for `V6FunctionExecutor._program`. It delegates to `id`, `get`,
            `read_text`, `_Program` while keeping intermediate state local to the owning operation.
        """
        key = id(document.resource)
        program = self._programs.get(key)
        if program is None:
            source = document.read_text()
            program = _Program(
                lines=tuple(line for line in source.splitlines() if line and not line.startswith("#")),
            )
            self._programs[key] = program
        return program


__all__ = [
    "V6FunctionCapabilityError",
    "V6FunctionError",
    "V6FunctionExecutor",
    "V6FunctionRuntimeError",
    "V6FunctionSyntaxError",
]
