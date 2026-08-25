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
- `run_webui_daemon.ps1` builds the SPA, stages assets, and controls an
  isolated local daemon WebUI instance for manual integration testing.

Invoke scripts through uv from the repository root:

```bash
uv run python scripts/check_release.py
uv run python -m scripts.run_tool_install_smoke
```

On Windows, start and open a disposable WebUI instance with:

```powershell
.\scripts\run_webui_daemon.ps1
```

Use `-Action Start`, `-Action Status`, or `-Action Stop` for lifecycle
control. The default workspace is `tmp\webui-daemon`; pass `-SkipBuild` to
reuse already staged assets.

For Vite HMR against a real daemon, run `pnpm --dir webui run web`. It starts
an isolated development daemon with the independent WebUI distribution,
proxies `/api` through Vite with the required loopback origin, and opens the
one-use WebUI handoff in the browser.

When adding a publishable package, give it an isolated install verifier and add
the package identity to `check_release.py`, CI, and the release procedure.
Scripts must not embed credentials or modify tracked source files as a side
effect.
