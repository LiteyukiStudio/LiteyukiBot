# Releasing v7 Packages

v7 uses PyPI Trusted Publishing and immutable, package-specific tags. Release
from a clean `v7` commit only after the full CI matrix passes.

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
| `liteyukibot-v7-essentials` | `pypi-essentials` |

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
| `liteyukibot-v7==7.0.0a3` | `pyproject.toml` | `v7.0.0a3` |
| `liteyukibot-v7-permissions==0.2.0a1` | `packages/permissions` | `permissions-v0.2.0a1` |
| `liteyukibot-v7-commands==0.2.0a1` | `packages/commands` | `commands-v0.2.0a1` |
| `liteyukibot-v7-essentials==0.2.0a1` | `packages/essentials` | `essentials-v0.2.0a1` |

`scripts/check_release.py` owns this mapping. Both publish workflows reject a
tag that does not exactly match the selected source version and distribution.

## Order

Push and wait for each release before creating the next tag:

1. `v7.0.0a3`;
2. `permissions-v0.2.0a1`;
3. `commands-v0.2.0a1`;
4. `essentials-v0.2.0a1`.

Each plugin workflow builds only its selected project, installs that wheel in a
temporary uv environment against already published dependencies, exercises its
real entry point, then uploads that package. This makes an out-of-order release
fail before publication.

After the final upload, verify the public dependency chain without a checkout:

```bash
uv run --no-project --python 3.14 \
  --with "liteyukibot-v7-essentials==0.2.0a1" \
  python -c "import importlib.metadata as m; print(m.version('liteyukibot-v7'))"
```

Never move or reuse a release tag. Correct source and publish a new pre-release
version when an uploaded artifact is wrong.
