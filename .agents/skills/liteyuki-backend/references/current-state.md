# Checked Alpha13 Baseline And Alpha14 Transition

This is a navigation aid, not a timeless contract. It was checked on
2026-08-24 with source version `7.0.0a13`. Recheck the live tree and commit
before relying on it.

## Implementation Facts

- The repository is a Python 3.14 `uv` workspace. The root distribution is
  `liteyukibot-v7`; independently buildable packages live under `packages/`.
- The root `src/liteyukibot/` still owns both broad application/business
  orchestration and protocol-neutral contracts. `app.py`, `cli.py`, daemon,
  plugin management, update, configuration, and Broker have not yet been split
  into the planned packages.
- The former supervised child `liteyukibot.runtime` package, client, supervisor,
  catalog, test harness, and custom-runtime example have been removed. Current
  Runtime API DTO/facade names, managed generation storage fields, and
  runtime-named Bridge distribution identities remain live contracts; do not
  classify them as the deleted child Runtime implementation.
- `packages/cordis` is an independent Python Cordis host. Current Alpha13
  documentation and code allow Native and Cordis to coexist; first-party
  packages such as permissions and essentials currently expose both Native and
  Cordis entry points. The narrower Native policy is an Alpha14 target.
- Current Cordis is trusted in-process and has full host access by design.
  Access policy is governance and accidental-misuse control, not Python code
  isolation.
- Broker owns cross-process bridge identity, routing, delivery/lease state,
  bounded ledger state, and diagnostics. A bridge host owns its framework
  lifecycle.
- Package versions may be independent. Most Alpha13 packages declare an exact
  `liteyukibot-v7==7.0.0a13` dependency, but `adapter-satori` and `agent`
  currently use `>=7.0.0a1,<8`. Treat exact
  kernel pins for every participating Alpha package as approved direction, not
  as completed Alpha13 state.
- AstrBot, Neo-MoFox, and v6 compatibility bridge source snapshots are retained
  under `extras/legacy-bridges`. They are excluded from the workspace, lock,
  CI, release inventory, publication, and v7.0.0 support surface.
- The WebUI consists of React/Vite source in `webui/` and the Python bridge and
  wheel wrapper in `packages/webui/`. Its generated static assets are staged by
  `scripts/stage_webui_assets.py`.
- Alpha publication is currently a signed GitHub bundle from
  `.github/workflows/alpha-release.yaml`. The ordinary publish workflows reject
  Alpha versions for PyPI.

## Sources Of Truth

Use implementation and executable checks before narrative documents:

1. Package metadata and entry points in root/package `pyproject.toml` files.
2. Current source and focused tests for behavior.
3. `.github/workflows/ci.yaml`, release workflows, `scripts/check_release.py`,
   and install verifiers for executable release contracts.
4. `docs/specs/` for public wire/API contracts and `docs/architecture/` for the
   maintained architecture description.
5. `docs/roadmap/`, `docs/archive/`, and unexpired `docs/tmp/` only as clearly
   labelled plans, history, or temporary decision inputs.

Documents in this repository have drifted during rapid iteration. If prose and
tested code disagree, report the mismatch; do not silently choose whichever
supports the desired conclusion.
