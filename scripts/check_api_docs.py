"""Validate structured callable documentation across production sources."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    ROOT / "src",
    *(path / "src" for path in (ROOT / "packages").iterdir() if (path / "src").is_dir()),
    ROOT / "packages" / "ipc-native" / "python",
)
EXTRA_SOURCES = (ROOT / "scripts" / "benchmark_v7.py",)


@dataclass(frozen=True, slots=True)
class DocumentationIssue:
    """Describe one callable documentation contract violation.

    Args:
        path: Source file containing the violation.
        line: One-based source line of the callable.
        qualified_name: Module-local qualified callable name.
        message: Human-readable contract failure.

    Returns:
        A frozen issue record.
    """

    path: Path
    line: int
    qualified_name: str
    message: str


def _source_files() -> tuple[Path, ...]:
    """Collect production Python files covered by the documentation contract.

    Returns:
        Sorted, duplicate-free source paths.

    Notes:
        Internal discovery is path-based so the check does not import optional
        runtime frameworks or execute package initialization code.
    """

    files = {path for root in SOURCE_ROOTS if root.is_dir() for path in root.rglob("*.py")}
    files.update(path for path in EXTRA_SOURCES if path.is_file())
    return tuple(sorted(files))


def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    """Return documented parameter names for one callable.

    Args:
        node: Function syntax node to inspect.

    Returns:
        Parameter names excluding conventional `self` and `cls` receivers.

    Notes:
        Internal normalization treats positional-only, keyword-only, variadic,
        and ordinary parameters uniformly because all cross the call contract.
    """

    names = [argument.arg for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)]
    if node.args.vararg is not None:
        names.append(node.args.vararg.arg)
    if node.args.kwarg is not None:
        names.append(node.args.kwarg.arg)
    return tuple(name for name in names if name not in {"self", "cls"})


def _section_body(docstring: str, heading: str) -> str | None:
    """Extract an indented Google-style docstring section body.

    Args:
        docstring: Normalized callable docstring.
        heading: Section heading without the trailing colon.

    Returns:
        Section body text, or `None` when the section is absent.

    Notes:
        Internal parsing intentionally accepts any indentation and stops at the
        next unindented heading so hand-wrapped prose remains valid.
    """

    lines = docstring.splitlines()
    marker = f"{heading}:"
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == marker) + 1
    except StopIteration:
        return None
    body: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.endswith(":") and line == line.lstrip():
            break
        body.append(stripped)
    return "\n".join(body).strip()


def _walk_callables(
    statements: list[ast.stmt],
    parents: tuple[str, ...] = (),
) -> tuple[tuple[ast.FunctionDef | ast.AsyncFunctionDef, tuple[str, ...]], ...]:
    """Walk functions and methods without descending through lambda bodies.

    Args:
        statements: Statements belonging to a module, class, or function body.
        parents: Qualified-name components accumulated by the caller.

    Returns:
        Function nodes paired with their parent name components.

    Notes:
        Internal traversal includes named nested helpers because they carry
        meaningful local contracts, but excludes anonymous lambdas which cannot
        own Python docstrings.
    """

    found: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, tuple[str, ...]]] = []
    for statement in statements:
        if isinstance(statement, ast.ClassDef):
            found.extend(_walk_callables(statement.body, (*parents, statement.name)))
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((statement, parents))
            found.extend(_walk_callables(statement.body, (*parents, statement.name)))
    return tuple(found)


def _walk_classes(statements: list[ast.stmt]) -> tuple[ast.ClassDef, ...]:
    """Walk every named class in a statement tree.

    Args:
        statements: Statements belonging to a module, class, or function body.

    Returns:
        Class nodes in source traversal order.

    Notes:
        Internal traversal includes nested classes because their callable
        contracts are otherwise invisible to documentation tooling.
    """

    found: list[ast.ClassDef] = []
    for statement in statements:
        if isinstance(statement, ast.ClassDef):
            found.append(statement)
            found.extend(_walk_classes(statement.body))
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.extend(_walk_classes(statement.body))
    return tuple(found)


def _issues_for(path: Path) -> tuple[DocumentationIssue, ...]:
    """Validate every callable in one source file.

    Args:
        path: Python source file to parse.

    Returns:
        Documentation issues ordered by source traversal.

    Raises:
        SyntaxError: If the source file cannot be parsed as Python.

    Notes:
        Internal validation checks structure only. Human review remains
        responsible for semantic accuracy and security rationale quality.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    issues: list[DocumentationIssue] = []
    for class_node in _walk_classes(tree.body):
        if ast.get_docstring(class_node) is None:
            issues.append(
                DocumentationIssue(path, class_node.lineno, class_node.name, "missing class docstring")
            )
    for callable_node, parents in _walk_callables(tree.body):
        name = ".".join((*parents, callable_node.name))
        docstring = ast.get_docstring(callable_node)
        if docstring is None:
            issues.append(DocumentationIssue(path, callable_node.lineno, name, "missing docstring"))
            continue
        args_body = _section_body(docstring, "Args")
        for parameter in _parameters(callable_node):
            if args_body is None or not any(
                line.lstrip().startswith((f"{parameter}:", f"*{parameter}:", f"**{parameter}:"))
                for line in args_body.splitlines()
            ):
                issues.append(
                    DocumentationIssue(
                        path,
                        callable_node.lineno,
                        name,
                        f"missing Args entry for {parameter}",
                    )
                )
        if _section_body(docstring, "Returns") is None:
            issues.append(
                DocumentationIssue(path, callable_node.lineno, name, "missing Returns section")
            )
        if (
            callable_node.name.startswith("_")
            and not callable_node.name.startswith("__")
            and _section_body(docstring, "Notes") is None
        ):
            issues.append(
                DocumentationIssue(
                    path,
                    callable_node.lineno,
                    name,
                    "private callable is missing Notes section",
                )
            )
    return tuple(issues)


def main() -> int:
    """Run the repository callable documentation check.

    Returns:
        Zero when every callable satisfies the contract, otherwise one.
    """

    source_files = _source_files()
    issues = tuple(issue for path in source_files for issue in _issues_for(path))
    for issue in issues:
        relative = issue.path.relative_to(ROOT)
        print(f"{relative}:{issue.line}: {issue.qualified_name}: {issue.message}")
    if issues:
        print(f"Callable documentation check failed with {len(issues)} issue(s).", file=sys.stderr)
        return 1
    class_count = 0
    callable_count = 0
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        class_count += len(_walk_classes(tree.body))
        callable_count += len(_walk_callables(tree.body))
    print(
        "Callable documentation check passed for "
        f"{len(source_files)} source files, {class_count} classes, and {callable_count} callables."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
