# Releasing v7 Packages

v7 uses PyPI Trusted Publishing and immutable, package-specific tags. Release
from a clean `main` commit only after the full CI matrix passes.

`liteyukibot-v7-runtime-cordis` was a rejected Rust/PyO3 design spike and has
no publisher, identity, tag, or release-order entry. Beta6 introduces the
independent Python `liteyukibot-v7-cordis` package; it receives release
metadata only after its host/plugin entry points and install verifier exist.

## Trusted Publishers

The PyPI publisher settings use:

- owner/repository: `LiteyukiStudio/LiteyukiBot`;
- root workflow/environment: `publish.yml` / `pypi`;
- plugin workflow: `publish-plugins.yaml`;
- one environment per plugin, as listed below.

Before the first plugin upload, create these Pending Publishers:

| Project | GitHub environment |
| --- | --- |
| `liteyukibot-v7-permissions` | `pypi-permissions` |
| `liteyukibot-v7-commands` | `pypi-commands` |
| `liteyukibot-v7-resources` | `pypi-resources` |
| `liteyukibot-v7-functions` | `pypi-lyfunctions` |
| `liteyukibot-v7-profile` | `pypi-profile` |
| `liteyukibot-v7-essentials` | `pypi-essentials` |
| `liteyukibot-v7-runtime-nonebot` | `pypi-runtime-nonebot` |
| `liteyukibot-v7-runtime-adapter` | `pypi-runtime-adapter` |
| `liteyukibot-v7-adapter-onebot` | `pypi-adapter-onebot` |
| `liteyukibot-v7-adapter-satori` | `pypi-adapter-satori` |
| `liteyukibot-v7-runtime-v6` | `pypi-runtime-v6` |
| `liteyukibot-v7-agent-resolver` | `pypi-agent-resolver` |
| `liteyukibot-v7-agent` | `pypi-agent` |
| `liteyukibot-v7-runtime-astrbot` | `pypi-astrbot-runtime` |
| `liteyukibot-v7-runtime-mofox` | `pypi-mofox-runtime` |

PyPI requires different pending project names to use distinct publisher
identities. The workflow selects the environment from the release tag (or the
manual dispatch package), while the repository and workflow name stay shared.

Do not create tags until every corresponding publisher is configured. A 404
from the PyPI JSON endpoint is expected before the first trusted upload; an
existing project owned elsewhere is a release blocker, not a reason to rename a
distribution inside the workflow.

## Identities

| Package | Source | Tag |
| --- | --- | --- |
| `liteyukibot-v7==7.0.0b2` | `pyproject.toml` | `v7.0.0b2` |
| `liteyukibot-v7-permissions==0.2.0a2` | `packages/permissions` | `permissions-v0.2.0a2` |
| `liteyukibot-v7-commands==0.2.0a2` | `packages/commands` | `commands-v0.2.0a2` |
| `liteyukibot-v7-resources==0.1.0a2` | `packages/resources` | `resources-v0.1.0a2` |
| `liteyukibot-v7-functions==0.1.0a2` | `packages/functions` | `functions-v0.1.0a2` |
| `liteyukibot-v7-profile==0.1.0a2` | `packages/profile` | `profile-v0.1.0a2` |
| `liteyukibot-v7-essentials==0.2.0a3` | `packages/essentials` | `essentials-v0.2.0a3` |
| `liteyukibot-v7-runtime-nonebot==0.1.0a1` | `packages/runtime-nonebot` | `runtime-nonebot-v0.1.0a1` |
| `liteyukibot-v7-runtime-adapter==0.1.0a2` | `packages/runtime-adapter` | `runtime-adapter-v0.1.0a2` |
| `liteyukibot-v7-adapter-onebot==0.1.0a1` | `packages/adapter-onebot` | `adapter-onebot-v0.1.0a1` |
| `liteyukibot-v7-adapter-satori==0.1.0a2` | `packages/adapter-satori` | `adapter-satori-v0.1.0a2` |
| `liteyukibot-v7-runtime-v6==0.1.0a2` | `packages/runtime-v6` | `runtime-v6-v0.1.0a2` |
| `liteyukibot-v7-agent-resolver==0.1.0a1` | `packages/agent-resolver` | `agent-resolver-v0.1.0a1` |
| `liteyukibot-v7-agent==0.1.0a9` | `packages/agent` | `agent-v0.1.0a9` |
| `liteyukibot-v7-runtime-astrbot==0.1.0a7` | `packages/runtime-astrbot` | `runtime-astrbot-v0.1.0a7` |
| `liteyukibot-v7-runtime-mofox==0.1.0a8` | `packages/runtime-mofox` | `runtime-mofox-v0.1.0a8` |

`scripts/check_release.py` owns this mapping. Both publish workflows reject a
tag that does not exactly match the selected source version and distribution.

## Order

Push and wait for each release before creating the next tag:

1. `v7.0.0b2`;
2. `permissions-v0.2.0a2`;
3. `commands-v0.2.0a2`;
4. `resources-v0.1.0a2`;
5. `functions-v0.1.0a2`;
6. `profile-v0.1.0a2`;
7. `essentials-v0.2.0a3`;
8. `runtime-nonebot-v0.1.0a1`.
9. `runtime-adapter-v0.1.0a2`.
10. `adapter-onebot-v0.1.0a1`.
11. `adapter-satori-v0.1.0a2`.
12. `runtime-v6-v0.1.0a2`.
13. `agent-resolver-v0.1.0a1`.
14. `agent-v0.1.0a9` (requires `commands-v0.2.0a2`).
15. `runtime-astrbot-v0.1.0a7`.
16. `runtime-mofox-v0.1.0a8`.

Each plugin workflow builds only its selected project, installs that wheel in a
temporary uv environment against already published dependencies, exercises its
real entry point, then uploads that package. This makes an out-of-order release
fail before publication.

Neo-MoFox is an explicit, fixed-commit installation prerequisite rather than a
wheel dependency because PyPI rejects direct VCS dependencies. The MoFox
release verifier installs that same requirement before exercising the runtime.

After the final upload, verify the public dependency chain without a checkout:

```bash
uv run --no-project --python 3.14 \
  --with "liteyukibot-v7-essentials==0.2.0a3" \
  python -c "import importlib.metadata as m; print(m.version('liteyukibot-v7'))"
```

Never move or reuse a release tag. Correct source and publish a new pre-release
version when an uploaded artifact is wrong.
