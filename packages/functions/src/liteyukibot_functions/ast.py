"""Immutable abstract syntax tree for the Alpha 7 Liteyuki Function language."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

type JSONPrimitive = None | bool | int | float | str
type FrozenJSONValue = JSONPrimitive | tuple["FrozenJSONValue", ...] | Mapping[str, "FrozenJSONValue"]


@dataclass(frozen=True, slots=True)
class SourcePosition:
    """A zero-based source offset with one-based line and column values."""

    offset: int
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Half-open source range."""

    start: SourcePosition
    end: SourcePosition


ZERO_SPAN = SourceSpan(SourcePosition(0, 1, 1), SourcePosition(0, 1, 1))


def freeze_json(value: Any) -> FrozenJSONValue:
    """Copy a JSON-compatible value into immutable containers.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `FrozenJSONValue` result produced by the operation.
    """

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze_json(item) for key, item in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(freeze_json(item) for item in value)
    raise TypeError(f"value is not JSON-safe: {type(value).__name__}")


def thaw_json(value: FrozenJSONValue | Any) -> Any:
    """Make a mutable JSON-shaped copy for evaluator/library boundaries.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Any` result produced by the operation.
    """

    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class AstNode:
    """Represent the ast node contract."""
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class UseDeclaration(AstNode):
    """Represent the use declaration contract."""
    namespace: str
    provider: str | None


@dataclass(frozen=True, slots=True)
class DocComment(AstNode):
    """Represent the doc comment contract."""
    text: str


@dataclass(frozen=True, slots=True)
class Expr(AstNode):
    """Represent the expr contract."""
    pass


@dataclass(frozen=True, slots=True)
class LiteralExpr(Expr):
    """Represent the literal expr contract."""
    value: FrozenJSONValue


@dataclass(frozen=True, slots=True)
class NameExpr(Expr):
    """Represent the name expr contract."""
    name: str


@dataclass(frozen=True, slots=True)
class ListExpr(Expr):
    """Represent the list expr contract."""
    items: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class TupleExpr(Expr):
    """Represent the tuple expr contract."""
    items: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class ObjectEntry(AstNode):
    """Represent the object entry contract."""
    key: str
    value: Expr


@dataclass(frozen=True, slots=True)
class ObjectExpr(Expr):
    """Represent the object expr contract."""
    entries: tuple[ObjectEntry, ...]


@dataclass(frozen=True, slots=True)
class MemberExpr(Expr):
    """Represent the member expr contract."""
    value: Expr
    name: str


@dataclass(frozen=True, slots=True)
class IndexExpr(Expr):
    """Represent the index expr contract."""
    value: Expr
    index: Expr


@dataclass(frozen=True, slots=True)
class CallExpr(Expr):
    """Represent the call expr contract."""
    callee: Expr
    arguments: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class AwaitExpr(Expr):
    """Represent the await expr contract."""
    value: Expr


@dataclass(frozen=True, slots=True)
class UnaryExpr(Expr):
    """Represent the unary expr contract."""
    operator: str
    value: Expr


@dataclass(frozen=True, slots=True)
class BinaryExpr(Expr):
    """Represent the binary expr contract."""
    left: Expr
    operator: str
    right: Expr


@dataclass(frozen=True, slots=True)
class BindingTarget(AstNode):
    """Represent the binding target contract."""
    pass


@dataclass(frozen=True, slots=True)
class NameTarget(BindingTarget):
    """Represent the name target contract."""
    name: str


@dataclass(frozen=True, slots=True)
class DiscardTarget(BindingTarget):
    """Represent the discard target contract."""
    pass


@dataclass(frozen=True, slots=True)
class TupleTarget(BindingTarget):
    """Represent the tuple target contract."""
    items: tuple[BindingTarget, ...]


@dataclass(frozen=True, slots=True)
class Statement(AstNode):
    """Represent the statement contract."""
    pass


@dataclass(frozen=True, slots=True)
class BindingStatement(Statement):
    """Represent the binding statement contract."""
    kind: str
    target: BindingTarget
    value: Expr


@dataclass(frozen=True, slots=True)
class AssignmentStatement(Statement):
    """Represent the assignment statement contract."""
    target: BindingTarget
    value: Expr


@dataclass(frozen=True, slots=True)
class ReturnStatement(Statement):
    """Represent the return statement contract."""
    value: Expr | None


@dataclass(frozen=True, slots=True)
class ExpressionStatement(Statement):
    """Represent the expression statement contract."""
    value: Expr


@dataclass(frozen=True, slots=True)
class PassStatement(Statement):
    """Represent the pass statement contract."""
    pass


@dataclass(frozen=True, slots=True)
class UnsupportedStatement(Statement):
    """Represent the unsupported statement contract."""
    kind: str
    detail: str
    body: tuple[Statement, ...] = ()


@dataclass(frozen=True, slots=True)
class DecoratorArgument(AstNode):
    """Represent the decorator argument contract."""
    name: str
    value: Expr


@dataclass(frozen=True, slots=True)
class Decorator(AstNode):
    """Represent the decorator contract."""
    name: str


@dataclass(frozen=True, slots=True)
class AgentDecorator(Decorator):
    """Represent the agent decorator contract."""
    kind: str
    arguments: tuple[DecoratorArgument, ...]


@dataclass(frozen=True, slots=True)
class EventsDecorator(Decorator):
    """Represent the events decorator contract."""
    topic: Expr
    arguments: tuple[DecoratorArgument, ...]


@dataclass(frozen=True, slots=True)
class UnknownDecorator(Decorator):
    """Represent the unknown decorator contract."""
    arguments: tuple[DecoratorArgument, ...]


@dataclass(frozen=True, slots=True)
class FunctionDeclaration(AstNode):
    """Represent the function declaration contract."""
    name: str
    parameters: tuple[str, ...]
    body: tuple[Statement, ...]
    is_async: bool = False
    is_sync: bool = False
    decorators: tuple[Decorator, ...] = ()
    documentation: str | None = None


type TopLevelDeclaration = (
    UseDeclaration | BindingStatement | AssignmentStatement | FunctionDeclaration | UnsupportedStatement
)


@dataclass(frozen=True, slots=True)
class FunctionProgram:
    """A parsed, source-preserving Alpha 7 program."""

    source_id: str
    version: str | None
    declarations: tuple[TopLevelDeclaration, ...]

    @property
    def uses(self) -> tuple[UseDeclaration, ...]:
        """Return the function program's uses.

        Returns:
            The `tuple[UseDeclaration, ...]` result produced by the operation.
        """
        return tuple(item for item in self.declarations if isinstance(item, UseDeclaration))

    @property
    def functions(self) -> tuple[FunctionDeclaration, ...]:
        """Return the function program's functions.

        Returns:
            The `tuple[FunctionDeclaration, ...]` result produced by the operation.
        """
        return tuple(item for item in self.declarations if isinstance(item, FunctionDeclaration))

    @property
    def module_bindings(self) -> tuple[BindingStatement, ...]:
        """Return the function program's module bindings.

        Returns:
            The `tuple[BindingStatement, ...]` result produced by the operation.
        """
        return tuple(item for item in self.declarations if isinstance(item, BindingStatement))


__all__ = [
    "AgentDecorator",
    "AstNode",
    "AssignmentStatement",
    "AwaitExpr",
    "BinaryExpr",
    "BindingStatement",
    "BindingTarget",
    "CallExpr",
    "Decorator",
    "DecoratorArgument",
    "DiscardTarget",
    "DocComment",
    "EventsDecorator",
    "Expr",
    "ExpressionStatement",
    "FunctionDeclaration",
    "FunctionProgram",
    "FrozenJSONValue",
    "IndexExpr",
    "ListExpr",
    "LiteralExpr",
    "MemberExpr",
    "NameExpr",
    "NameTarget",
    "ObjectEntry",
    "ObjectExpr",
    "PassStatement",
    "ReturnStatement",
    "SourcePosition",
    "SourceSpan",
    "Statement",
    "TupleExpr",
    "TupleTarget",
    "UnaryExpr",
    "UnknownDecorator",
    "UnsupportedStatement",
    "UseDeclaration",
    "ZERO_SPAN",
    "freeze_json",
    "thaw_json",
]
