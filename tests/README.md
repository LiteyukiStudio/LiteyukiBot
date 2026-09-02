# Tests

`tests/` covers root-kernel behavior and cross-package integration. Package
unit and runtime-specific tests live beside their owners in
`packages/*/tests/`.

Name tests after the contract they exercise. Use temporary pytest paths for
workspaces, state, profiles, and generated plugin bundles. Do not depend on a
developer's `data/`, `plugins/`, `tmp/`, tool installation, credentials, or
network account.

Run a focused test while changing behavior:

```bash
uv run pytest tests/test_cli_v7.py tests/test_config_workspace.py
uv run pytest packages/<package>/tests
```

Before a pull request, run the full suite from the repository root:

```bash
uv run pytest
```

Process, package-wheel, and published-dependency contracts are intentionally
tested through the verifiers under `scripts/`; add one when an installation
boundary changes.
