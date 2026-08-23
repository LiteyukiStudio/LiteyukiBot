# Releasing v7 Packages

This document preserves the historical B7 package procedure and records the
boundary for the planned Alpha release process. It is not evidence that a
future Alpha, RC, or stable release is ready. The forward-looking sequence is
defined in [the v7 Alpha roadmap](../roadmap/v7-alpha-roadmap.md).

## Planned Alpha boundary

The next version line starts at `7.0.0a1`; Beta1-Beta7 are architecture
validation history. Before RC1, do not publish the kernel or its lockstep
runtime components to PyPI. An Alpha may publish only an immutable GitHub
Release asset containing a signed release manifest and SHA-256 digests.

[Alpha 1 baseline](../roadmap/v7-alpha-1-baseline.md) fixes the first planned
tag as `v7.0.0a1`, defines its seven-component bundle, reserves DevCLI without
shipping it, and requires a tag-bound first-party Sigstore proof for the
aggregate manifest. The existing workflows below must be changed before that
release so that they reject every Alpha version and cannot call `uv publish`.

[Alpha 2](../roadmap/v7-alpha-2-plugin-permission-tools.md) retained that
release mechanism at `v7.0.0a2` and added only the independent Permissions
asset to the signed bundle. It did not authorize a PyPI plugin release.

[Alpha 3](../roadmap/v7-alpha-3-business-plugin-migration.md) adds the planned
first-party business assets and frozen Functions compatibility rebuild to the
signed `v7.0.0a3` bundle. It does not change the PyPI boundary.

[Alpha 4](../roadmap/v7-alpha-4-adapter-bridge.md) adds the independent OneBot
and Satori driver assets to the signed `v7.0.0a4` bundle. From this point, every
Alpha rebuilds every independent first-party package against that Alpha's exact
kernel version. It does not authorize PyPI publication or turn bridge lifecycle
ownership into broker supervision.

[Alpha 5](../roadmap/v7-alpha-5-compatibility-bridges.md) and
[Alpha 6](../roadmap/v7-alpha-6-agent-bridge.md) retain the same full-bundle
release rule while adding compatibility and Agent bridge assets.

[Alpha 7](../roadmap/v7-alpha-7-lyf-dsl.md), [Alpha 8]
(../roadmap/v7-alpha-8-devcli-updates.md), and [Alpha 9]
(../roadmap/v7-alpha-9-runtime-ecosystem.md) retain that signed bundle rule
while adding the DSL, DevCLI, updater, and bounded runtime facade surfaces. The
Alpha9 source identity is `v7.0.0a9`; its bundle includes the resolved offline
dependency lock, DevCLI wheel, read-only LYF VSIX, daemon graph lifecycle
evidence, and the typed AstrBot/NoneBot runtime API packages. It remains a
GitHub Release artifact and is not a PyPI publication.

[Alpha 12](../roadmap/v7-alpha-12-ecosystem-activation.md) advances the current
source identity to `v7.0.0a12`, adds the independently versioned reference
NoneBot plugin to the signed bundle, and requires the managed-generation
external-host E2E before release. The 72-hour soak remains deferred to stable.

[Alpha 13](../roadmap/v7-alpha-13-webui-textmate.md) advances the current
source identity to `v7.0.0a13`, adds the typed plugin WebUI and LYF TextMate
consumer, and keeps npm publication blocked until `@liteyuki` scope access is
confirmed. The temporary fixed Git dependency is not a stable publication
identity and must be replaced by an exact npm version before the Alpha13 npm
consumer release is declared complete.

Kernel, IPC, WebUI, DevCLI, Cordis, and broker-bridge components use the
lockstep Alpha version. Business plugins and independently distributed PyPI
packages retain their own versions and must declare the compatible kernel
Alpha. No Alpha stage is a release commitment: it becomes eligible only after
its roadmap exit criteria and the complete repository validation gate pass.

## Historical B7 procedure

The sections below describe the B7 package artifacts and trusted-publisher
setup. They are historical evidence only and must not be reused to publish a
pre-RC Alpha to PyPI.

### B7 qualification boundary

B7 changes the bridge and extension contracts but does not authorize a stable
release. Before any B7 tag, release qualification must include the normal CI
and package install verifiers, the schema-2 `bare` and
`installed-first-party` benchmark artifacts with their resolved manifests, and
the separately planned long-running soak. Do not claim that the 72-hour soak or
full-workspace theoretical benchmark has completed until their retained
artifacts are reviewed. Bridge support grades are package metadata: NoneBot is
`stable`; AstrBot remains `experimental` until a later release decision.

`liteyukibot-v7-runtime-cordis` was a rejected Rust/PyO3 design spike and has
no publisher, identity, tag, or release-order entry. Beta6 introduces the
independent Python `liteyukibot-v7-cordis` package; it receives release
metadata only after its host/plugin entry points and install verifier exist.

## Historical Trusted Publishers

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

## Historical B7 Identities

| Package | Source | Tag |
| --- | --- | --- |
| `liteyukibot-v7==7.0.0b2` | historical B7 release metadata | `v7.0.0b2` |
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

## Historical Order

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
