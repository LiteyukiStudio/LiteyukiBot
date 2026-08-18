# Release And Maintenance v1

- Specification version: `1`
- Applies to: v7 release artifacts, first-party package publication, and the
  `7.0.x` maintenance line.
- Compatibility: stable-policy contract, effective before the first stable v7
  release.

## Compatibility And Fixes

`7.0.x` preserves public Python APIs, command paths, configuration schema
semantics, resource manifests, and negotiated protocol versions. A patch may
add an optional capability or fix an incorrect behavior, but it may not change
an existing default, reassign a wire type, or make a supported configuration
invalid. Security fixes may disable an unsafe behavior only with a documented
diagnostic, migration path, and patch release note.

Pre-stable protocol and configuration changes require a new documented version
and focused compatibility tests. A stable protocol change requires a parallel
negotiated version; it cannot replace an accepted version in place.

## Reproducible Artifacts

Python dependencies are resolved by the committed `uv.lock`. WebUI builds use
the committed `webui/pnpm-lock.yaml`, pnpm 11.5.3, and Node 25.8.1 from
`.node-version`. The release pipeline stages the WebUI bundle, writes an asset
SHA-256 manifest, produces a CycloneDX SBOM, validates the declared SPDX or
`LicenseRef` identifier, and writes SHA-256 checksums for each wheel and source
distribution.

The optional native package is built by maturin with locked Cargo dependencies
for Linux x86_64/aarch64, macOS x86_64/aarch64, and Windows x86_64. It publishes
platform wheels only; Native ABI is versioned independently. Platforms without
a compatible wheel or native ABI use the documented ZMQ LYIP backend; they do
not claim shared-memory support.

Publishing accepts only wheel and source-distribution artifacts and uses the
configured PyPI Trusted Publisher environment. SBOMs, checksum manifests, and
other release evidence are retained as workflow artifacts rather than uploaded
as distributions.

## Alpha 3 Bundle

The source Alpha 3 contract uses the exact `7.0.0a3` version for the kernel,
Native IPC, Cordis, NoneBot bridge, AstrBot bridge, generic adapter bridge, and
WebUI. The DevCLI identifier is reserved in the bundle inventory but has no
artifact in Alpha 3. Independent business packages do not join this lockstep
set. Permissions, Commands, Resources, Profile, Essentials, Agent Resolver,
and Functions are independent signed assets and require exactly
`liteyukibot-v7==7.0.0a3`.

`scripts/alpha_release.py` validates source metadata, writes canonical UTF-8
`artifacts.manifest.json`, and writes the deterministic CycloneDX 1.5
`sbom.cdx.json`. The manifest records tag, common version, frozen LYIP v2 /
Runtime IPC v6 / broker v6 / configuration v5 baselines, inventory, artifact
metadata, sizes, and SHA-256 hashes. Its Sigstore sidecar is named
`artifacts.manifest.sigstore.json` and must verify the GitHub OIDC issuer,
repository, Alpha workflow path, and exact tag.

`.github/workflows/alpha-release.yaml` is the only Alpha publication path. It
builds the lockstep bundle, validates it in a fresh directory, exercises every
staged install verifier, and uploads assets to an immutable GitHub Release. It
never calls `uv publish`. The historical PyPI workflows call
`scripts/check_release.py --reject-alpha` before building, so an Alpha version
cannot reach their publish steps.

## Evidence

Run `uv build --all-packages --out-dir dist/workspace --clear`,
`uv run python -m scripts.run_webui_install`, and
`uv run pytest tests/test_release_v7.py tests/test_alpha_release.py`.
