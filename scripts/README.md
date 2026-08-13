# Developer And Release Scripts

Scripts in this directory are executable verification and release-support
tools. They are not runtime imports and should remain small command-line
programs with deterministic inputs and clear exit statuses.

- `check_release.py` validates source versions, package identities, and tags.
- `run_*_install.py` creates isolated environments and exercises installed
  package entry points.
- `verify_*_install.py` contains the verifier invoked by an isolated install.
- `benchmark_v7.py` records kernel performance measurements.
- `run_tool_install_smoke.py` verifies the published CLI installation flow.

Invoke scripts through uv from the repository root:

```bash
uv run python scripts/check_release.py
uv run python -m scripts.run_tool_install_smoke
```

When adding a publishable package, give it an isolated install verifier and add
the package identity to `check_release.py`, CI, and the release procedure.
Scripts must not embed credentials or modify tracked source files as a side
effect.
