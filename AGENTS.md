# Repository Guidelines

## Project Structure

LiteyukiBot v7 is a Python 3.14 `uv` workspace. The protocol-neutral kernel
lives in `src/liteyukibot/`; keep framework-specific behavior in its owning
child runtime. Independently buildable first-party packages live under
`packages/<name>/`, each with its own `pyproject.toml`, `src/`, `tests/`,
resources, and README. Root kernel and cross-package tests are in `tests/`.
Use `examples/` for installable reference integrations, `scripts/` for release
and install verifiers, and `docs/` for maintained architecture and operations.

## Build, Test, and Development Commands

Use CPython 3.14 and uv. Install the locked workspace with:

```bash
uv sync --locked --all-packages --extra onebot --extra satori
uv run liteyuki check
uv run ruff check src tests scripts examples packages
uv run mypy
uv run pytest
uv build --all-packages --out-dir dist/workspace --clear
```

Run the smallest relevant test while editing, for example `uv run pytest
tests/test_cli_v7.py` or `uv run pytest packages/commands/tests`. Changes to a
package boundary, wheel, entry point, or runtime host also require its matching
`python -m scripts.run_<package>_install` verifier. CI in
`.github/workflows/ci.yaml` is the authoritative complete sequence.

## Coding Style and Contracts

Use four-space indentation, type annotations, and strict mypy-compatible
Python. Ruff enforces a 120-character line limit and E/F/I/UP/B/ASYNC rules.
Use `snake_case` for modules, functions, and tests; `PascalCase` for classes;
and name tests `test_<behavior>.py` and `test_<expected_contract>()`.

Keep kernel APIs protocol-neutral and JSON-safe. The root kernel must not
import first-party packages directly. Declare inter-package dependencies in
metadata; child runtimes use shared `RuntimeClient` and declare capabilities.
Update the relevant ADR, architecture guide, or package README when public
events, actions, IPC, configuration, services, or plugin contracts change.

## Tests, Commits, and Pull Requests

Use temporary pytest paths; tests must not depend on local `data/`, `plugins/`,
credentials, or network accounts. Commit subjects follow Conventional Commits,
such as `fix(runtime): externalize dependency` or `test(onebot): cover restart`.
Target PRs to `v7`, keep each focused on one owned boundary, and state the
validation commands plus configuration or release impact. Do not commit
`dist/`, caches, secrets, local workspaces, or `tmp/` artifacts.
