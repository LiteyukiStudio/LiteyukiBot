# Contributing To LiteyukiBot v7

## Scope And Branches

`main` is the v7 development branch. Start a feature or fix branch from an
up-to-date `main`; do not merge v6 source or dependencies into v7 wholesale.

Keep one change focused on one kernel contract, package, adapter, test surface,
or documentation concern. The kernel owns portable models, EventBus, actions,
services, and lifecycle contracts. The root package owns configuration, CLI,
application composition, and built-in features; framework details stay in the
owning adapter package.

## Development Environment

Use CPython 3.14 and uv:

```bash
uv sync --locked --all-packages
uv run liteyuki --workspace tmp/validation-workspace init
uv run liteyuki --workspace tmp/validation-workspace check
```

`uv.lock` is the repository lockfile. Update it only when dependency metadata
changes, and keep every workspace package resolvable with the root project.

## Validation

Run the smallest relevant checks while editing, then the repository quality
suite before opening a pull request:

```bash
uv run ruff check src tests scripts packages
uv run mypy
uv run pytest
uv build
uv build --all-packages --out-dir dist/workspace --clear
uv run pip-audit --local --progress-spinner off --vulnerability-service osv
```

Changes to package metadata, entry points, release validation, runtime hosts,
or package integration must also run the relevant `scripts/run_*_install.py`
verifier. The complete CI sequence is defined in `.github/workflows/ci.yaml`.
Do not commit `dist/`, caches, local workspaces, secrets, generated profiles,
or temporary research artifacts.

## Contracts And Tests

Update the relevant specification, architecture guide, or package README when a
public Event, Action, configuration, service, or plugin contract changes. Keep
protocol models JSON-safe and versioned. Adapters own protocol details and
communicate with the kernel through its public event and action contracts.

Add or update focused tests under `tests/` or the owning `packages/*/tests/`
directory. Test real package entry points where a change crosses an
installation boundary.

## Pull Requests And Releases

Open pull requests against `main`. Keep stacks short; merge a green independent
pull request promptly and never let a Stack grow beyond 20 layers. PR text
should state the owned boundary, validation commands, and any configuration or
release impact.

Use squash merge after required checks and review pass, then delete the merged
feature branch. Do not move or reuse package tags. Published distributions use
the package-specific release process in
[`docs/development/releasing.md`](docs/development/releasing.md).

## Documentation

The root README describes current user-facing installation and package usage.
`docs/` records maintained contracts and operations. Directory README files
describe how to develop their contents. Keep completed scratch plans in ignored
`tmp/`; do not turn them into compatibility or release commitments.
