# v7 Alpha 1 Baseline

> **Planned implementation contract.** This document records the agreed Alpha 1
> release boundary. It does not claim that `7.0.0a1` exists, that an artifact
> has been built, or that a GitHub Release is authorized.

Alpha 1 turns the B7 architecture-validation result into a reproducible,
first-party release bundle. It intentionally changes release mechanics and
version alignment, not broker, runtime, configuration, or plugin behavior.

## Lockstep release set

The release tag and every shipped lockstep distribution use the exact PEP 440
version `7.0.0a1`:

| Component | Distribution | Source |
| --- | --- | --- |
| Kernel | `liteyukibot-v7` | repository root |
| Native IPC | `liteyukibot-v7-ipc-native` | `packages/ipc-native` |
| Cordis | `liteyukibot-v7-cordis` | `packages/cordis` |
| NoneBot bridge | `liteyukibot-v7-runtime-nonebot` | `packages/runtime-nonebot` |
| AstrBot bridge | `liteyukibot-v7-runtime-astrbot` | `packages/runtime-astrbot` |
| Generic adapter bridge | `liteyukibot-v7-runtime-adapter` | `packages/runtime-adapter` |
| WebUI | `liteyukibot-v7-webui` | `packages/webui` |

`DevCLI` is a reserved component identity in the manifest and release
inventory. Alpha 1 does not create, build, or publish a DevCLI package.

Dependencies between two components in this table must use `==7.0.0a1`.
Independent first-party business packages are not part of the Alpha 1 bundle
and retain their own version line. They may not be published to PyPI during the
Alpha line.

## Tag, assets, and evidence

The immutable release tag is `v7.0.0a1`. The release consists of one GitHub
Release bundle containing only artifacts built for the lockstep set, including
every supported native IPC wheel, source distributions where the component
produces one, and these aggregate evidence files:

- `artifacts.manifest.json`: canonical UTF-8 JSON with release tag, common
  version, component inventory, artifact filename, byte count, SHA-256,
  license, fixed LYIP v2 / Runtime IPC v6 / broker v6 / configuration v5
  baseline, and the reserved DevCLI entry;
- `sbom.cdx.json`: a reproducible CycloneDX inventory for the bundle;
- `artifacts.manifest.sigstore.json`: the Sigstore bundle for the manifest.

Only the canonical aggregate manifest is Sigstore-signed. Its artifact hashes
bind every bundled asset. Verification must pin the GitHub OIDC issuer,
`LiteyukiStudio/LiteyukiBot`, the dedicated Alpha release workflow, and the
exact `v7.0.0a1` tag. A correct hash with a different workflow or tag identity
is not a first-party Alpha verification success.

Third-party plugin signatures remain optional. Alpha 1 neither bundles them
nor treats an unsigned third-party package as a first-party artifact.

## Release and CI changes

Add a dedicated Alpha workflow for `v7.0.0aN` tags. It validates the registry,
builds the lockstep set, runs each shipped component's isolated verifier from
the staged artifacts, writes the SBOM and manifest, keylessly signs the
manifest with Sigstore, and creates the GitHub Release. It has no PyPI publish
step or PyPI environment.

Existing root and package publishing workflows remain for RC and stable
releases only. They must reject Alpha versions from tags and manual dispatch,
so no path can call `uv publish` for an Alpha. CI replaces the current
PyPI-dependent published-install job with a local staged-bundle installation
check; the Alpha release workflow additionally verifies the completed bundle
from a fresh directory without importing the source tree.

The implementation supplies a release registry, bundle generator, and external
bundle verifier. The verifier checks Sigstore identity, manifest canonical
form, required component set, artifact hashes and sizes, wheel metadata, tag
and common-version agreement, and the frozen baseline values.

## Alpha 1 completion gate

Alpha 1 is complete only when a clean checkout passes the repository quality
gate, workspace build, all seven install verifiers, staged-bundle verification,
and downloaded-release-directory verification. The generated evidence must be
retained with the GitHub Release. Publishing to PyPI, DevCLI implementation,
Permission v2, broker tool RPC, and any protocol behavior change are explicitly
outside Alpha 1.

## Alpha 2 handoff

The next implementation milestone starts only after this baseline is merged.
Alpha 2 may rely on the frozen release identity and bundle verifier, then
implements [Plugin API v2, Permission v2, and the single broker catalog
extension](v7-alpha-2-plugin-permission-tools.md). It must not modify the
Alpha 1 artifact trust model. The planned independent Permissions asset is the
only Alpha 2 change to the release inventory.
