# Repository Guidelines

## Project Structure

LiteyukiBot v7 is a Python 3.14 `uv` workspace. The protocol-neutral kernel
lives in `packages/kernel/src/liteyukibot_kernel/`; the root application and
built-in features live in `src/liteyukibot/`. Keep framework-specific behavior
in its owning adapter package. Independently buildable first-party packages
live under `packages/<name>/`, each with its own `pyproject.toml`, `src/`,
`tests/`, and README. Root application and cross-package tests are in `tests/`.
Use `scripts/` for release and install verifiers, and `docs/` for maintained
architecture and operations.
Retired source snapshots under `extras/legacy-bridges/` are not workspace
packages, supported integrations, release inputs, or valid dependency targets.

## Build, Test, and Development Commands

Use CPython 3.14 and uv. Install the locked workspace with:

```bash
uv sync --locked --all-packages
uv run liteyuki --workspace tmp/validation-workspace init
uv run liteyuki --workspace tmp/validation-workspace check
uv run ruff check src tests scripts examples packages
uv run mypy
uv run pytest
uv build --all-packages --out-dir dist/workspace --clear
```

Run the smallest relevant test while editing, for example `uv run pytest
tests/test_alpha15_app.py` or `uv run pytest packages/kernel/tests`. Changes to
a package boundary, wheel, entry point, or adapter host also require its
matching `python -m scripts.run_*_install` verifier. CI in
`.github/workflows/ci.yaml` is the authoritative complete sequence.

For performance-path changes, add a current runner, deterministic tests, and a
reviewable artifact together. Do not use retired benchmark files as a release
gate or as a current performance contract.

## Coding Style and Contracts

Use four-space indentation, type annotations, and strict mypy-compatible
Python. Ruff enforces a 120-character line limit and E/F/I/UP/B/ASYNC rules.
Use `snake_case` for modules, functions, and tests; `PascalCase` for classes;
and name tests `test_<behavior>.py` and `test_<expected_contract>()`.

Keep kernel APIs protocol-neutral and JSON-safe. The kernel must not import
root application or first-party feature packages directly. Declare
inter-package dependencies in metadata.
Update the relevant ADR, architecture guide, or package README when public
events, actions, IPC, configuration, services, or plugin contracts change.

## Tests, Commits, and Pull Requests

Use temporary pytest paths; tests must not depend on local `data/`, `plugins/`,
credentials, or network accounts. Commit subjects follow Conventional Commits,
such as `fix(runtime): externalize dependency` or `test(onebot): cover restart`.
Target PRs to `main`, keep each focused on one owned boundary, and state the
validation commands plus configuration or release impact. Do not commit
`dist/`, caches, secrets, local workspaces, or `tmp/` artifacts.
