# Backend Engineering Workflow

## Read And Bound The Change

- Start with `git status -sb`; preserve unrelated user changes.
- Trace the owning package, its public imports and entry points, direct callers,
  tests, configuration, docs, release registry, and install verifier before
  changing a boundary.
- Keep the root kernel protocol-neutral and JSON-safe. Do not import a
  first-party package from kernel to make a migration temporarily convenient.
- Declare inter-package dependencies in metadata. Do not use cross-package
  private imports or make an installed wheel rely on the source checkout.
- Public events, actions, IPC, configuration, services, capabilities, or plugin
  contracts require synchronized normative documentation and focused tests.

## Validation Ladder

Use CPython 3.14 and `uv`. During editing, run the smallest relevant test, for
example:

```powershell
uv run pytest tests/test_cli_v7.py
uv run pytest packages/commands/tests
```

For a package boundary, wheel, entry point, or runtime/bridge host, locate the
exact verifier in `.github/workflows/ci.yaml` and `scripts/`; names are not
mechanically derived from package names. Some packages use `run_*_install`,
while API-only packages use `run_isolated_install.py` with a `verify_*` script.
New publishable packages require a package-local test suite, isolated install
verifier, release identity, and CI/build coverage.

Before declaring a repository-wide backend change complete, use the applicable
authoritative sequence:

```powershell
uv sync --locked --all-packages --extra onebot --extra satori --extra webui
uv run liteyuki check
uv run ruff check src tests scripts examples packages
uv run mypy
uv run pytest
uv build --all-packages --out-dir dist/workspace --clear
```

Inspect `.github/workflows/ci.yaml` immediately before the final run because its
package list and frontend requirements may have changed. Do not run a formatter
that rewrites unrelated files. Tests must use temporary paths and must not
depend on local `data/`, plugins, credentials, or network accounts.

For every affected distribution, also run its `scripts/check_release.py`
variant and exact install verifier from CI. Run `scripts/check_api_docs.py` when
public Python callables or their documentation contract change. Do not report a
package-boundary change complete from only the generic workspace commands.

Use `$benchmark-tests` before changing workload semantics, performance paths,
or benchmark artifacts. Shared-runner benchmark output is review evidence, not
an automatic pass/fail threshold.

## Documentation Checks

- Label planned behavior as planned and current behavior as checked at a
  version/commit. Never repair drift by rewriting history as current fact.
- Validate relative links, metadata, version claims, and canonical ownership.
- Move promoted decisions out of `docs/tmp/` before expiry; delete superseded
  scratch content instead of growing a second archive.
- Do not place documentation in root `tmp/`.

## Delegated Work

For the Alpha14/Alpha15 architecture workstream, the owner prefers no more than
two concurrent subagents, using `gpt-5.6-luna` with `max` reasoning effort.
Each delegated prompt must forbid spawning further subagents and assign
non-overlapping files or ownership boundaries. The coordinating agent owns
shared metadata, dependency direction, integration validation, and final
judgment.

This preference does not require delegation for a small task. It also does not
authorize edits outside the user's requested scope.
