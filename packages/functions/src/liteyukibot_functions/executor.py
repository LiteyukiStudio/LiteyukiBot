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
    pass


class V6FunctionCapabilityError(V6FunctionError):
    pass


type CapabilityMethod = Callable[..., object]

_PLACEHOLDER = re.compile(r"\$\{([^{}]*)\}")
_ESCAPED_EQUALS = "__LITEYUKI_ESCAPED_EQUALS__"


@dataclass(frozen=True, slots=True)
class _Statement:
    head: str
    args: tuple[str, ...]
    kwargs: Mapping[str, Any]
    tail: str


@dataclass(slots=True)
class _Execution:
    call: FunctionCall
    invoke: FunctionInvoker
    variables: dict[str, Any] = field(init=False)
    tasks: set[asyncio.Task[None]] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.variables = dict(self.call.arguments)

    async def run(self, document: FunctionDocument) -> None:
        try:
            for source in document.read_text().splitlines():
                if not source or source.startswith("#"):
                    continue
                if await self._execute(source):
                    return
        except BaseException:
            await self.cancel_tasks()
            raise
        finally:
            self._retain_background_tasks()

    async def _execute(self, source: str) -> bool:
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
            task = asyncio.create_task(self._execute_background(statement.tail), name="liteyuki-v6-function-nohup")
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        elif statement.head == "await":
            await self.await_tasks()
        elif statement.head == "end":
            await self.cancel_tasks()
            return True
        else:
            raise V6FunctionSyntaxError(f"unsupported v6 function instruction: {statement.head!r}")
        return False

    async def _execute_background(self, source: str) -> None:
        await self._execute(source)

    def _render(self, source: str) -> str:
        if "${" in source:
            return _PLACEHOLDER.sub(lambda match: str(self.variables.get(match.group(1), "")), source)
        try:
            return source.format(*self.call.positional, **self.variables)
        except IndexError, KeyError, ValueError:
            return source

    def _parse(self, source: str) -> _Statement:
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
        try:
            return ast.literal_eval(value)
        except SyntaxError, ValueError:
            return self.variables.get(value, value)

    @staticmethod
    def _required_argument(statement: _Statement, instruction: str) -> str:
        if len(statement.args) < 2 or not statement.args[1]:
            raise V6FunctionSyntaxError(f"{instruction} requires an argument")
        return statement.args[1]

    async def _capability(self, name: str, *args: object) -> object:
        capability = self.call.capabilities
        method = getattr(capability, name, None)
        if not callable(method):
            raise V6FunctionCapabilityError(f"v6 function instruction requires the {name} capability")
        result = cast(CapabilityMethod, method)(*args)
        if not inspect.isawaitable(result):
            raise V6FunctionCapabilityError(f"the {name} capability must return an awaitable")
        return await result

    async def await_tasks(self) -> None:
        tasks = tuple(self.tasks)
        if tasks:
            await asyncio.gather(*tasks)

    async def cancel_tasks(self) -> None:
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _retain_background_tasks(self) -> None:
        for task in tuple(self.tasks):
            if task.done():
                continue
            _BACKGROUND_TASKS.add(task)
            task.add_done_callback(_BACKGROUND_TASKS.discard)


_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


class V6FunctionExecutor:
    """Execute v6 `.lyf`, `.lyfunction`, and `.mcfunction` resource files."""

    extensions: tuple[str, ...] = (".lyf", ".lyfunction", ".mcfunction")

    async def execute(
        self,
        document: FunctionDocument,
        call: FunctionCall,
        invoke: FunctionInvoker,
    ) -> None:
        await _Execution(call, invoke).run(document)


__all__ = [
    "V6FunctionCapabilityError",
    "V6FunctionError",
    "V6FunctionExecutor",
    "V6FunctionSyntaxError",
]
