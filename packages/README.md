# First-Party Packages

Each immediate child directory is an independently buildable uv workspace
package. Package code owns its framework integration or business capability;
`packages/kernel` owns the protocol-neutral kernel contract, while the root
`src/liteyukibot/` package owns CLI and application composition. Kernel code
must not import the root package or another first-party package.

## Package Classes

- `kernel` publishes `liteyukibot-v7-kernel` from the independent
  `liteyukibot_kernel` namespace. The branded root package re-exports its
  contracts through deliberate compatibility modules.
- `permissions`, `commands`, `resources`, `profile`, and `essentials` are
  native plugin/service packages.
- `functions` is the separate executor for documented v6 resource functions.
- Current `runtime-*` packages are independently hosted integrations.
  `runtime-nonebot` is the stable framework bridge and `runtime-adapter` is the
  shared protocol-adapter host; each owns its SDK and lifecycle and is
  discovered through `liteyukibot.bridges`.
  Retired bridge experiments live outside the workspace under
  `extras/legacy-bridges` and are not supported packages.
  The former `runtime-cordis` Rust/PyO3 package was rejected and has been
  removed.
- `cordis` is the independent Python in-process composition package introduced
  by Beta6; root composition discovers it through host entry points.
- `adapter-onebot` is a platform driver loaded by the shared `runtime-adapter`
  Broker bridge.
- `agent` publishes the experimental `agent` and `agent-sandbox` Broker bridges
  and the bounded catalog; `agent-resolver` provides declarative Tool resolver
  metadata. Neither package publishes a child runtime or native Agent plugin.

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
