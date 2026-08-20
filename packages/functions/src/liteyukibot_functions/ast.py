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
    """Copy a JSON-compatible value into immutable containers."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze_json(item) for key, item in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(freeze_json(item) for item in value)
    raise TypeError(f"value is not JSON-safe: {type(value).__name__}")


def thaw_json(value: FrozenJSONValue | Any) -> Any:
    """Make a mutable JSON-shaped copy for evaluator/library boundaries."""

    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class AstNode:
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class UseDeclaration(AstNode):
    namespace: str
    provider: str | None


@dataclass(frozen=True, slots=True)
class DocComment(AstNode):
    text: str


@dataclass(frozen=True, slots=True)
class Expr(AstNode):
    pass


@dataclass(frozen=True, slots=True)
class LiteralExpr(Expr):
    value: FrozenJSONValue


@dataclass(frozen=True, slots=True)
class NameExpr(Expr):
    name: str


@dataclass(frozen=True, slots=True)
class ListExpr(Expr):
    items: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class TupleExpr(Expr):
    items: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class ObjectEntry(AstNode):
    key: str
    value: Expr


@dataclass(frozen=True, slots=True)
class ObjectExpr(Expr):
    entries: tuple[ObjectEntry, ...]


@dataclass(frozen=True, slots=True)
class MemberExpr(Expr):
    value: Expr
    name: str


@dataclass(frozen=True, slots=True)
class IndexExpr(Expr):
    value: Expr
    index: Expr


@dataclass(frozen=True, slots=True)
class CallExpr(Expr):
    callee: Expr
    arguments: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class AwaitExpr(Expr):
    value: Expr


@dataclass(frozen=True, slots=True)
class UnaryExpr(Expr):
    operator: str
    value: Expr


@dataclass(frozen=True, slots=True)
class BinaryExpr(Expr):
    left: Expr
    operator: str
    right: Expr


@dataclass(frozen=True, slots=True)
class BindingTarget(AstNode):
    pass


@dataclass(frozen=True, slots=True)
class NameTarget(BindingTarget):
    name: str


@dataclass(frozen=True, slots=True)
class DiscardTarget(BindingTarget):
    pass


@dataclass(frozen=True, slots=True)
class TupleTarget(BindingTarget):
    items: tuple[BindingTarget, ...]


@dataclass(frozen=True, slots=True)
class Statement(AstNode):
    pass


@dataclass(frozen=True, slots=True)
class BindingStatement(Statement):
    kind: str
    target: BindingTarget
    value: Expr


@dataclass(frozen=True, slots=True)
class AssignmentStatement(Statement):
    target: BindingTarget
    value: Expr


@dataclass(frozen=True, slots=True)
class ReturnStatement(Statement):
    value: Expr | None


@dataclass(frozen=True, slots=True)
class ExpressionStatement(Statement):
    value: Expr


@dataclass(frozen=True, slots=True)
class PassStatement(Statement):
    pass


@dataclass(frozen=True, slots=True)
class UnsupportedStatement(Statement):
    kind: str
    detail: str
    body: tuple[Statement, ...] = ()


@dataclass(frozen=True, slots=True)
class DecoratorArgument(AstNode):
    name: str
    value: Expr


@dataclass(frozen=True, slots=True)
class Decorator(AstNode):
    name: str


@dataclass(frozen=True, slots=True)
class AgentDecorator(Decorator):
    kind: str
    arguments: tuple[DecoratorArgument, ...]


@dataclass(frozen=True, slots=True)
class EventsDecorator(Decorator):
    topic: Expr
    arguments: tuple[DecoratorArgument, ...]


@dataclass(frozen=True, slots=True)
class UnknownDecorator(Decorator):
    arguments: tuple[DecoratorArgument, ...]


@dataclass(frozen=True, slots=True)
class FunctionDeclaration(AstNode):
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
        return tuple(item for item in self.declarations if isinstance(item, UseDeclaration))

    @property
    def functions(self) -> tuple[FunctionDeclaration, ...]:
        return tuple(item for item in self.declarations if isinstance(item, FunctionDeclaration))

    @property
    def module_bindings(self) -> tuple[BindingStatement, ...]:
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
