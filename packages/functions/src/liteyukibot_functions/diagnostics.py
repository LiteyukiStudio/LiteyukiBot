"""Stable diagnostics exposed by the Alpha 7 Function API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .ast import SourceSpan

if TYPE_CHECKING:
    from .ast import FunctionProgram

type DiagnosticSeverity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A bounded, serializable parser, preflight or runtime diagnostic."""

    code: str
    message: str
    source: str
    span: SourceSpan | None = None
    severity: DiagnosticSeverity = "error"

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    def as_dict(self) -> dict[str, object]:
        span: dict[str, object] | None = None
        if self.span is not None:
            span = {
                "start": {
                    "offset": self.span.start.offset,
                    "line": self.span.start.line,
                    "column": self.span.start.column,
                },
                "end": {
                    "offset": self.span.end.offset,
                    "line": self.span.end.line,
                    "column": self.span.end.column,
                },
            }
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "source": self.source,
            "span": span,
        }


@dataclass(frozen=True, slots=True)
class ParseResult:
    """The immutable result of parsing one LYF source string."""

    program: FunctionProgram | None
    diagnostics: tuple[Diagnostic, ...]

    @property
    def ok(self) -> bool:
        return not any(item.is_error for item in self.diagnostics)


__all__ = ["Diagnostic", "DiagnosticSeverity", "ParseResult"]
