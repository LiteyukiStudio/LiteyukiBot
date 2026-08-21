"""Lark parser and source diagnostics for the Alpha 7 LYF grammar."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from typing import Any, cast

from lark import Lark, Token, Transformer, UnexpectedInput, v_args

from .ast import (
    AgentDecorator,
    AssignmentStatement,
    AstNode,
    AwaitExpr,
    BinaryExpr,
    BindingStatement,
    BindingTarget,
    CallExpr,
    Decorator,
    DecoratorArgument,
    DiscardTarget,
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
    ObjectEntry,
    ObjectExpr,
    PassStatement,
    ReturnStatement,
    SourcePosition,
    SourceSpan,
    Statement,
    TupleExpr,
    TupleTarget,
    UnaryExpr,
    UnknownDecorator,
    UnsupportedStatement,
    UseDeclaration,
    freeze_json,
)
from .diagnostics import Diagnostic, ParseResult

_GRAMMAR = r"""
start: _nls [declaration (NEWLINE+ declaration)*] _nls

declaration: doc_block declaration_core
?declaration_core: version_decl | use_decl | decorated_function | function_decl
                 | binding_stmt | assignment_stmt | tuple_assignment_stmt
                 | legacy_stmt | while_stmt | for_in_stmt | c_for_stmt

doc_block: (DOC_COMMENT _nls)*
version_decl: VERSION NUMBER
use_decl: USE NAME [AT PROVIDER]

decorated_function: decorator _nls (decorator _nls)* function_decl
?decorator: agent_decorator | events_decorator | unknown_decorator
agent_decorator: AGENT LPAR _nls AGENT_KIND [_nls COMMA _nls decorator_arguments] _nls RPAR
events_decorator: EVENTS LPAR _nls expr [_nls COMMA _nls decorator_arguments] _nls RPAR
unknown_decorator: DECORATOR_NAME [LPAR _nls [decorator_arguments] _nls RPAR]
decorator_arguments: decorator_argument (COMMA _nls decorator_argument)* [COMMA]
decorator_argument: NAME EQUAL _nls expr

function_decl: [function_modifier] FN NAME [function_params] block
function_modifier: ASYNC | SYNC
function_params: LPAR _nls [NAME (COMMA _nls NAME)* [COMMA]] _nls RPAR

block: LBRACE _nls [statement (NEWLINE+ statement)*] _nls RBRACE
?statement: binding_stmt
          | assignment_stmt
          | compound_assignment_stmt
          | tuple_assignment_stmt
          | return_stmt
          | pass_stmt
          | while_stmt
          | for_in_stmt
          | c_for_stmt
          | command_stmt
          | legacy_await_stmt
          | legacy_stmt
          | ellipsis_stmt
          | expression_stmt
binding_stmt: BINDING_KIND binding_target EQUAL _nls expr
assignment_stmt: NAME EQUAL _nls expr -> name_assignment_stmt
               | DISCARD EQUAL _nls expr -> discard_assignment_stmt
compound_assignment_stmt: NAME ADD_ASSIGN _nls expr
tuple_assignment_stmt: NAME COMMA _nls assignment_target_item (COMMA _nls assignment_target_item)* EQUAL _nls expr
?assignment_target_item: NAME | DISCARD
?binding_target: NAME -> name_target
               | DISCARD -> discard_target
               | tuple_target
tuple_target: LPAR _nls binding_target COMMA _nls binding_target (COMMA _nls binding_target)* [COMMA] _nls RPAR
return_stmt: RETURN [return_value]
return_value: expr (COMMA _nls expr)* [COMMA]
pass_stmt: PASS
while_stmt: WHILE expr block
for_in_stmt: FOR NAME IN expr block
c_for_stmt: FOR NAME DECLARE_ASSIGN expr SEMICOLON expr SEMICOLON NAME ADD_ASSIGN expr block
command_stmt: (ECHO | PRINT) expr
legacy_await_stmt: AWAIT
legacy_stmt: LEGACY_HEAD [LEGACY_TAIL]
ellipsis_stmt: ELLIPSIS
expression_stmt: expr

?expr: or_expr
?or_expr: and_expr (OR and_expr)* -> binary_chain
?and_expr: comparison (AND comparison)* -> binary_chain
?comparison: sum_expr (COMPARE_OP sum_expr)* -> binary_chain
?sum_expr: product ((PLUS | MINUS) product)* -> binary_chain
?product: unary ((STAR | SLASH | PERCENT) unary)* -> binary_chain
?unary: (NOT | PLUS | MINUS) unary -> unary_expr
       | awaitable_expr
?awaitable_expr: AWAIT postfix -> await_expr
               | postfix
?postfix: atom postfix_part* -> postfix_expr
postfix_part: DOT NAME -> member_part
            | LPAR _nls [arguments] _nls RPAR -> call_part
            | LBRACK _nls expr _nls RBRACK -> index_part
arguments: expr (COMMA _nls expr)* [COMMA]

?atom: ESCAPED_STRING -> string_literal
     | NUMBER -> number_literal
     | TRUE -> true_literal
     | FALSE -> false_literal
     | NULL -> null_literal
     | NAME -> name_expr
     | paren_expr
     | list_literal
     | object_literal
paren_expr: LPAR _nls RPAR -> empty_tuple
          | LPAR _nls expr _nls RPAR -> grouped_expr
          | LPAR _nls expr COMMA _nls [expr (COMMA _nls expr)* [COMMA]] _nls RPAR -> tuple_literal
list_literal: LBRACK _nls [arguments] _nls RBRACK
object_literal: LBRACE _nls [object_entries] _nls RBRACE
object_entries: object_entry (COMMA _nls object_entry)* [COMMA]
object_entry: object_key COLON _nls expr
?object_key: ESCAPED_STRING -> string_key
           | NAME -> name_key

_nls: NEWLINE*

VERSION: "@version"
USE: "use"
AT: "@"
AGENT: "@agent"
EVENTS: "@events"
AGENT_KIND: "tool" | "prompt"
FN: "fn"
ASYNC: "async"
SYNC: "sync"
LET: "let"
VAL: "val"
CONST: "const"
BINDING_KIND.3: LET | VAL | CONST
RETURN: "return"
AWAIT: "await"
PASS: "pass"
WHILE: "while"
FOR: "for"
IN: "in"
TRUE: "true"
FALSE: "false"
NULL: "null"
ECHO: "echo"
PRINT: "print"
LEGACY_HEAD.2: "var" | "api" | "cmd" | "nohup" | "end" | "eval" | "function"
LEGACY_TAIL.0: /[^\r\n{} \t][^\r\n{}]*/
DECORATOR_NAME: /@[A-Za-z_][A-Za-z0-9_]*/
NAME: /[A-Za-z_][A-Za-z0-9_]*/
PROVIDER: /[A-Za-z_][A-Za-z0-9_-]*/
NUMBER: /-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/
ESCAPED_STRING: /"(?:\\.|[^"\\])*"/s
COMPARE_OP: "==" | "!=" | "<=" | ">=" | "<" | ">"
PLUS: "+"
MINUS: "-"
STAR: "*"
SLASH: "/"
PERCENT: "%"
OR: "or"
AND: "and"
NOT: "not"
DECLARE_ASSIGN: ":="
ADD_ASSIGN: "+="
ELLIPSIS: "..."
EQUAL.3: "="
SEMICOLON: ";"
DOT: "."
COMMA: ","
COLON: ":"
LPAR: "("
RPAR: ")"
LBRACK: "["
RBRACK: "]"
LBRACE: "{"
RBRACE: "}"
DISCARD: "_"
DOC_COMMENT: /(?m:^[ \t]*\/\/\/[^\r\n]*)/
NEWLINE: /\r?\n/

%ignore /[ \t\f]+/
%ignore /#[^\r\n]*/
%ignore /\/\/(?!\/)[^\r\n]*/
%ignore /\/\*(?s:.*?)\*\//
"""

LYF_GRAMMAR = _GRAMMAR


@dataclass(frozen=True, slots=True)
class _Version:
    value: str
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class _ParsedFile:
    versions: tuple[_Version, ...]
    declarations: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _MemberPart:
    name: str
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class _CallPart:
    arguments: tuple[Expr, ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class _IndexPart:
    index: Expr
    span: SourceSpan


def _span(meta: Any) -> SourceSpan:
    return SourceSpan(
        SourcePosition(meta.start_pos, meta.line, meta.column),
        SourcePosition(meta.end_pos, meta.end_line, meta.end_column),
    )


def _node_span(node: object) -> SourceSpan:
    return cast(AstNode, node).span


def _join_span(first: object, last: object) -> SourceSpan:
    left = _node_span(first)
    right = _node_span(last)
    return SourceSpan(left.start, right.end)


@v_args(meta=True)
class _AstTransformer(Transformer[Any, Any]):
    def start(self, meta: Any, children: list[Any]) -> _ParsedFile:
        versions = tuple(item for item in children if isinstance(item, _Version))
        declarations = tuple(
            item
            for item in children
            if isinstance(
                item, (UseDeclaration, BindingStatement, AssignmentStatement, FunctionDeclaration, UnsupportedStatement)
            )
        )
        return _ParsedFile(versions, declarations)

    def declaration(self, _meta: Any, children: list[Any]) -> object:
        docs: tuple[str, ...] = ()
        item: object | None = None
        for child in children:
            if isinstance(child, tuple) and all(isinstance(value, str) for value in child):
                docs = cast(tuple[str, ...], child)
            else:
                item = child
        if isinstance(item, FunctionDeclaration) and docs:
            return replace(item, documentation="\n".join(docs))
        if item is None:
            raise ValueError("declaration has no AST node")
        return item

    def doc_block(self, _meta: Any, children: list[Any]) -> tuple[str, ...]:
        return tuple(
            str(child).strip()[3:].strip()
            for child in children
            if isinstance(child, Token) and child.type == "DOC_COMMENT"
        )

    def version_decl(self, meta: Any, children: list[Any]) -> _Version:
        return _Version(
            next(str(item) for item in children if isinstance(item, Token) and item.type == "NUMBER"), _span(meta)
        )

    def use_decl(self, meta: Any, children: list[Any]) -> UseDeclaration:
        names = [str(child) for child in children if isinstance(child, Token) and child.type in {"NAME", "PROVIDER"}]
        provider = names[1] if len(names) > 1 else None
        return UseDeclaration(_span(meta), names[0], provider)

    def decorated_function(self, meta: Any, children: list[Any]) -> FunctionDeclaration:
        function = next(item for item in children if isinstance(item, FunctionDeclaration))
        decorators = tuple(item for item in children if isinstance(item, Decorator))
        return replace(function, decorators=decorators, span=_span(meta))

    def agent_decorator(self, meta: Any, children: list[Any]) -> AgentDecorator:
        kind = next(str(item) for item in children if isinstance(item, Token) and item.type == "AGENT_KIND")
        arguments = next(
            (
                item
                for item in children
                if isinstance(item, tuple) and all(isinstance(value, DecoratorArgument) for value in item)
            ),
            (),
        )
        return AgentDecorator(_span(meta), "agent", kind, cast(tuple[DecoratorArgument, ...], arguments))

    def events_decorator(self, meta: Any, children: list[Any]) -> EventsDecorator:
        topic = next(item for item in children if isinstance(item, Expr))
        arguments = next(
            (
                item
                for item in children
                if isinstance(item, tuple) and all(isinstance(value, DecoratorArgument) for value in item)
            ),
            (),
        )
        return EventsDecorator(_span(meta), "events", topic, cast(tuple[DecoratorArgument, ...], arguments))

    def unknown_decorator(self, meta: Any, children: list[Any]) -> UnknownDecorator:
        name = next(str(item)[1:] for item in children if isinstance(item, Token) and item.type == "DECORATOR_NAME")
        arguments = next(
            (
                item
                for item in children
                if isinstance(item, tuple) and all(isinstance(value, DecoratorArgument) for value in item)
            ),
            (),
        )
        return UnknownDecorator(_span(meta), name, cast(tuple[DecoratorArgument, ...], arguments))

    def decorator_arguments(self, _meta: Any, children: list[Any]) -> tuple[DecoratorArgument, ...]:
        return tuple(item for item in children if isinstance(item, DecoratorArgument))

    def decorator_argument(self, meta: Any, children: list[Any]) -> DecoratorArgument:
        return DecoratorArgument(_span(meta), str(children[0]), cast(Expr, children[-1]))

    def function_decl(self, meta: Any, children: list[Any]) -> FunctionDeclaration:
        modifier = next((str(item) for item in children if isinstance(item, str) and item in {"async", "sync"}), None)
        name = next(str(item) for item in children if isinstance(item, Token) and item.type == "NAME")
        tuples = [item for item in children if isinstance(item, tuple)]
        parameters = next((item for item in tuples if all(isinstance(value, str) for value in item)), ())
        body = next((item for item in reversed(tuples) if all(isinstance(value, Statement) for value in item)), ())
        return FunctionDeclaration(
            _span(meta),
            name,
            cast(tuple[str, ...], parameters),
            cast(tuple[Statement, ...], body),
            is_async=modifier == "async",
            is_sync=modifier == "sync",
        )

    def function_params(self, _meta: Any, children: list[Any]) -> tuple[str, ...]:
        return tuple(str(item) for item in children if isinstance(item, Token) and item.type == "NAME")

    def function_modifier(self, _meta: Any, children: list[Any]) -> str:
        return str(children[0])

    def block(self, _meta: Any, children: list[Any]) -> tuple[Statement, ...]:
        return tuple(item for item in children if isinstance(item, Statement))

    def binding_stmt(self, meta: Any, children: list[Any]) -> BindingStatement:
        kind = str(next(item for item in children if isinstance(item, Token) and item.type == "BINDING_KIND"))
        target = next(item for item in children if isinstance(item, BindingTarget))
        value = next(item for item in children if isinstance(item, Expr))
        return BindingStatement(_span(meta), kind, target, value)

    def name_assignment_stmt(self, meta: Any, children: list[Any]) -> AssignmentStatement:
        target = NameTarget(_span(meta), str(next(item for item in children if isinstance(item, Token))))
        value = next(item for item in children if isinstance(item, Expr))
        return AssignmentStatement(_span(meta), target, value)

    def discard_assignment_stmt(self, meta: Any, children: list[Any]) -> AssignmentStatement:
        target = DiscardTarget(_span(meta))
        value = next(item for item in children if isinstance(item, Expr))
        return AssignmentStatement(_span(meta), target, value)

    def compound_assignment_stmt(self, meta: Any, _children: list[Any]) -> UnsupportedStatement:
        return UnsupportedStatement(
            _span(meta),
            "compound-assignment",
            "compound assignment is parse-only in Alpha 7",
        )

    def tuple_assignment_stmt(self, meta: Any, children: list[Any]) -> AssignmentStatement:
        targets = tuple(
            NameTarget(_span(meta), str(item))
            if isinstance(item, Token) and item.type == "NAME"
            else DiscardTarget(_span(meta))
            for item in children
            if isinstance(item, Token) and item.type in {"NAME", "DISCARD"}
        )
        value = next(item for item in children if isinstance(item, Expr))
        return AssignmentStatement(_span(meta), TupleTarget(_span(meta), targets), value)

    def return_stmt(self, meta: Any, children: list[Any]) -> ReturnStatement:
        value = next((item for item in children if isinstance(item, Expr)), None)
        return ReturnStatement(_span(meta), value)

    def return_value(self, meta: Any, children: list[Any]) -> Expr:
        values = tuple(item for item in children if isinstance(item, Expr))
        if len(values) == 1:
            return values[0]
        return TupleExpr(_span(meta), values)

    def pass_stmt(self, meta: Any, _children: list[Any]) -> PassStatement:
        return PassStatement(_span(meta))

    def while_stmt(self, meta: Any, children: list[Any]) -> UnsupportedStatement:
        body = next((item for item in children if isinstance(item, tuple)), ())
        return UnsupportedStatement(_span(meta), "while", "while loops are parse-only in Alpha 7", body)

    def for_in_stmt(self, meta: Any, children: list[Any]) -> UnsupportedStatement:
        body = next((item for item in children if isinstance(item, tuple)), ())
        return UnsupportedStatement(_span(meta), "for", "for loops are parse-only in Alpha 7", body)

    def c_for_stmt(self, meta: Any, children: list[Any]) -> UnsupportedStatement:
        body = next((item for item in children if isinstance(item, tuple)), ())
        return UnsupportedStatement(_span(meta), "for-c", "C-style for loops are parse-only in Alpha 7", body)

    def command_stmt(self, meta: Any, children: list[Any]) -> ExpressionStatement:
        value = next(item for item in children if isinstance(item, Expr))
        command = str(next(item for item in children if isinstance(item, Token)))
        callee = MemberExpr(_span(meta), NameExpr(_span(meta), "terminal"), command)
        return ExpressionStatement(_span(meta), CallExpr(_span(meta), callee, (value,)))

    def legacy_await_stmt(self, meta: Any, _children: list[Any]) -> UnsupportedStatement:
        return UnsupportedStatement(_span(meta), "migration_required", "v6 await instruction requires migration")

    def legacy_stmt(self, meta: Any, children: list[Any]) -> UnsupportedStatement:
        head = str(children[0])
        tail = str(children[1]).strip() if len(children) > 1 else ""
        return UnsupportedStatement(
            _span(meta), "migration_required", f"v6 instruction {head!r} requires migration: {tail}"
        )

    def ellipsis_stmt(self, meta: Any, _children: list[Any]) -> UnsupportedStatement:
        return UnsupportedStatement(_span(meta), "placeholder", "ellipsis is a parse-only placeholder")

    def expression_stmt(self, meta: Any, children: list[Any]) -> ExpressionStatement:
        return ExpressionStatement(_span(meta), cast(Expr, children[0]))

    def name_target(self, meta: Any, children: list[Any]) -> NameTarget:
        return NameTarget(_span(meta), str(children[0]))

    def discard_target(self, meta: Any, _children: list[Any]) -> DiscardTarget:
        return DiscardTarget(_span(meta))

    def tuple_target(self, meta: Any, children: list[Any]) -> TupleTarget:
        return TupleTarget(_span(meta), tuple(item for item in children if isinstance(item, BindingTarget)))

    def name_expr(self, meta: Any, children: list[Any]) -> NameExpr:
        return NameExpr(_span(meta), str(children[0]))

    def string_literal(self, meta: Any, children: list[Any]) -> LiteralExpr:
        return LiteralExpr(_span(meta), freeze_json(json.loads(str(children[0]))))

    def number_literal(self, meta: Any, children: list[Any]) -> LiteralExpr:
        value = str(children[0])
        parsed: int | float = int(value) if all(character not in value for character in ".eE") else float(value)
        if not math.isfinite(parsed):
            raise ValueError("numbers must be finite")
        return LiteralExpr(_span(meta), parsed)

    def true_literal(self, meta: Any, _children: list[Any]) -> LiteralExpr:
        return LiteralExpr(_span(meta), True)

    def false_literal(self, meta: Any, _children: list[Any]) -> LiteralExpr:
        return LiteralExpr(_span(meta), False)

    def null_literal(self, meta: Any, _children: list[Any]) -> LiteralExpr:
        return LiteralExpr(_span(meta), None)

    def grouped_expr(self, _meta: Any, children: list[Any]) -> Expr:
        return cast(Expr, children[0])

    def empty_tuple(self, meta: Any, _children: list[Any]) -> TupleExpr:
        return TupleExpr(_span(meta), ())

    def tuple_literal(self, meta: Any, children: list[Any]) -> TupleExpr:
        return TupleExpr(_span(meta), tuple(item for item in children if isinstance(item, Expr)))

    def list_literal(self, meta: Any, children: list[Any]) -> ListExpr:
        values = next((item for item in children if isinstance(item, tuple)), ())
        return ListExpr(_span(meta), cast(tuple[Expr, ...], values))

    def object_literal(self, meta: Any, children: list[Any]) -> ObjectExpr:
        entries = next((item for item in children if isinstance(item, tuple)), ())
        return ObjectExpr(_span(meta), cast(tuple[ObjectEntry, ...], entries))

    def arguments(self, _meta: Any, children: list[Any]) -> tuple[Expr, ...]:
        return tuple(item for item in children if isinstance(item, Expr))

    def object_entries(self, _meta: Any, children: list[Any]) -> tuple[ObjectEntry, ...]:
        return tuple(item for item in children if isinstance(item, ObjectEntry))

    def object_entry(self, meta: Any, children: list[Any]) -> ObjectEntry:
        key = next(item for item in children if isinstance(item, str))
        value = next(item for item in children if isinstance(item, Expr))
        return ObjectEntry(_span(meta), key, value)

    def string_key(self, _meta: Any, children: list[Any]) -> str:
        return cast(str, json.loads(str(children[0])))

    def name_key(self, _meta: Any, children: list[Any]) -> str:
        return str(children[0])

    def postfix_expr(self, meta: Any, children: list[Any]) -> Expr:
        expression = cast(Expr, children[0])
        for part in children[1:]:
            if isinstance(part, _MemberPart):
                expression = MemberExpr(SourceSpan(expression.span.start, part.span.end), expression, part.name)
            elif isinstance(part, _CallPart):
                expression = CallExpr(SourceSpan(expression.span.start, part.span.end), expression, part.arguments)
            elif isinstance(part, _IndexPart):
                expression = IndexExpr(SourceSpan(expression.span.start, part.span.end), expression, part.index)
        return replace(expression, span=_span(meta))

    def member_part(self, meta: Any, children: list[Any]) -> _MemberPart:
        return _MemberPart(
            next(str(item) for item in children if isinstance(item, Token) and item.type == "NAME"), _span(meta)
        )

    def call_part(self, meta: Any, children: list[Any]) -> _CallPart:
        arguments = next((item for item in children if isinstance(item, tuple)), ())
        return _CallPart(cast(tuple[Expr, ...], arguments), _span(meta))

    def index_part(self, meta: Any, children: list[Any]) -> _IndexPart:
        return _IndexPart(next(item for item in children if isinstance(item, Expr)), _span(meta))

    def await_expr(self, meta: Any, children: list[Any]) -> AwaitExpr:
        return AwaitExpr(_span(meta), next(item for item in children if isinstance(item, Expr)))

    def unary_expr(self, meta: Any, children: list[Any]) -> UnaryExpr:
        operator = str(next(item for item in children if isinstance(item, Token)))
        value = next(item for item in children if isinstance(item, Expr))
        return UnaryExpr(_span(meta), operator, value)

    def binary_chain(self, meta: Any, children: list[Any]) -> Expr:
        values = [item for item in children if isinstance(item, Expr)]
        operators = [str(item) for item in children if isinstance(item, Token)]
        if not values:
            raise ValueError("binary expression has no operands")
        expression = values[0]
        for operator, right in zip(operators, values[1:], strict=True):
            expression = BinaryExpr(SourceSpan(expression.span.start, right.span.end), expression, operator, right)
        return replace(expression, span=_span(meta))


_PARSER = Lark(
    _GRAMMAR,
    parser="lalr",
    lexer="contextual",
    propagate_positions=True,
    maybe_placeholders=False,
    start="start",
)


def _error_span(error: UnexpectedInput, source: str) -> SourceSpan:
    offset = max(0, min(len(source), int(getattr(error, "pos_in_stream", 0) or 0)))
    line = int(getattr(error, "line", 1) or 1)
    column = int(getattr(error, "column", 1) or 1)
    end = min(len(source), offset + 1)
    return SourceSpan(
        SourcePosition(offset, line, column), SourcePosition(end, line, column + (1 if end > offset else 0))
    )


def _semantic_diagnostics(parsed: _ParsedFile, source_id: str) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if not parsed.versions:
        diagnostics.append(
            Diagnostic("LYF_VERSION_UNSUPPORTED", "the first declaration must be @version 1.0", source_id)
        )
    elif len(parsed.versions) > 1:
        for version in parsed.versions[1:]:
            diagnostics.append(
                Diagnostic(
                    "LYF_VERSION_UNSUPPORTED", "only one @version declaration is allowed", source_id, version.span
                )
            )
    first = parsed.versions[0] if parsed.versions else None
    first_node = next(iter(parsed.declarations), None)
    if first is not None and first_node is not None and first.span.start.offset > _node_span(first_node).start.offset:
        diagnostics.append(
            Diagnostic("LYF_VERSION_UNSUPPORTED", "@version must be the first declaration", source_id, first.span)
        )
    if first is not None and first.value != "1.0":
        diagnostics.append(
            Diagnostic("LYF_VERSION_UNSUPPORTED", f"unsupported LYF version {first.value!r}", source_id, first.span)
        )
    for declaration in parsed.declarations:
        if isinstance(declaration, AssignmentStatement):
            diagnostics.append(
                Diagnostic(
                    "LYF_BINDING_MODULE_ASSIGNMENT",
                    "module-level bare assignment is forbidden; use let, val, or const",
                    source_id,
                    declaration.span,
                )
            )
    return tuple(diagnostics)


def parse(source: str, *, source_id: str = "<memory>") -> ParseResult:
    """Parse LYF source into an immutable :class:`FunctionProgram`."""

    try:
        tree = _PARSER.parse(source)
        parsed = _AstTransformer().transform(tree)
        if not isinstance(parsed, _ParsedFile):
            raise ValueError("Lark did not produce a parsed LYF file")
        version = parsed.versions[0].value if parsed.versions else None
        program = FunctionProgram(source_id, version, cast(tuple[Any, ...], parsed.declarations))
        return ParseResult(program, _semantic_diagnostics(parsed, source_id))
    except UnexpectedInput as error:
        diagnostic = Diagnostic(
            "LYF_PARSE_UNEXPECTED_TOKEN",
            "unexpected token while parsing LYF source",
            source_id,
            _error_span(error, source),
        )
        return ParseResult(None, (diagnostic,))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        return ParseResult(None, (Diagnostic("LYF_PARSE_INVALID_LITERAL", str(error), source_id),))


__all__ = ["LYF_GRAMMAR", "parse"]
