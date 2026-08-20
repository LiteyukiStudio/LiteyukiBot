# First-Party Packages

Each immediate child directory is an independently buildable uv workspace
package. Package code owns its framework integration or business capability;
the root `src/liteyukibot/` package remains the kernel and must not import these
packages directly.

## Package Classes

- `permissions`, `commands`, `resources`, `profile`, and `essentials` are
  native plugin/service packages.
- `functions` is the separate executor for documented v6 resource functions.
- Most `runtime-*` packages are supervised child-runtime hosts retained for
  legacy compatibility. `runtime-nonebot` is a stable broker bridge and
  `runtime-astrbot` is an experimental AstrBot platform gateway; each owns its
  framework SDK and lifecycle and is discovered through `liteyukibot.bridges`.
  The former `runtime-cordis` Rust/PyO3 package was rejected and has been
  removed.
- `cordis` is the independent Python in-process composition package introduced
  by Beta6; the root kernel discovers it through host entry points.
- `adapter-onebot` is a platform driver loaded by the shared `runtime-adapter`
  Broker bridge.
- `agent` and `agent-resolver` provide the native agent runtime and its
  declarative resolver.

## Development Rules

Keep a package's public entry points, metadata, tests, README, and resource
files together. Use a package-local `pyproject.toml` for dependencies and entry
points. A package must depend on the published kernel contract it consumes;
avoid imports into another first-party package unless that dependency is
declared in its metadata.

Run focused tests first, then validate the workspace:

```bash
uv run pytest packages/<package>/tests
uv build --project packages/<package>
uv run python -m scripts.run_<package>_install
```

The exact install-verifier names are listed under `scripts/`. Release tags and
published versions are controlled by `scripts/check_release.py` and
`docs/development/releasing.md`.
