# v7 Alpha 12: Plugin Ecosystem Activation

Alpha12 makes the existing plugin-store design usable with the current broker
bridge architecture. It activates the official index, adds discoverable and
governable metadata, and gives the stable NoneBot bridge an atomic managed
plugin-generation path. It does not broaden the portable Runtime API or claim
that third-party Python code is sandboxed.

The source and bundle identity for this stage is `7.0.0a12` / `v7.0.0a12`.
The historical `v7.0.0a11` tag is not moved or reused.

## Current gap

The source already reserves
`https://raw.githubusercontent.com/LiteyukiStudio/liteyukibot-v7-plugins/main/index.json`
as its official index, but the new repository has no committed index. The
schema-1 document identifies installable facets by bundle ID but has no
publisher, license, source, summary, or withdrawal metadata. Unknown fields are
discarded and therefore are not covered by the calculated index digest.

More importantly, plugin installation resolves targets only through the legacy
supervised-runtime configuration. NoneBot and AstrBot now run as
`broker.bridges`, so the stable NoneBot host retains a facet installer that the
CLI and daemon cannot reach. Publishing an index without repairing this target
boundary would create searchable metadata that cannot be installed into the
current stable bridge.

## License and index governance

The public LiteyukiBot v7 distributions that currently use `LicenseRef-LSO`,
the official index repository, and the Alpha12 reference plugin use an
instantiated LSO-Common v1.4. Their Python metadata identity is
`LicenseRef-LSO-Common-1.4`. Both language texts are distributed, with the
Chinese text authoritative when the translations differ. Components that
already carry a distinct third-party or derivative license, including the
AGPL-licensed AstrBot and MoFox runtimes, retain that license.

- Licensor: `Liteyuki Studio LiteyukiBot Dev Team` /
  `Liteyuki 工作室 LiteyukiBot 开发团队`.
- Dispute resolution institution: `Beijing Arbitration Commission` /
  `北京仲裁委员会`.
- The repository records that maintainers confirmed the authority required for
  this license update; private authorization conversations are not committed.
- A separate trademark notice describes permitted nominative references and
  prohibits false endorsement or impersonation. It does not claim that
  LSO-Common prevents resale of otherwise compliant copies.

The official public index accepts SPDX license expressions,
`LicenseRef-LSO-Common-1.4`, and conspicuously identified
`LicenseRef-LSO-Commercial-1.4` entries. It rejects LSO-Private, missing license
terms, and artifacts whose license forbids their public redistribution. A
plugin retains its own license; contributing index metadata does not relicense
the plugin artifact.

The index repository initially publishes the canonical schema-1 empty document
so already-built clients can fetch the previously absent endpoint. Its default
branch then requires pull requests, CODEOWNERS review, validation CI, and
disabled force-push and deletion. The documented authenticity boundary is
GitHub HTTPS plus repository governance and hash-addressed artifacts. Alpha12
does not claim protection from compromise of the repository administrators.

## Plugin index schema 2

The kernel reads schemas 1 and 2. Schema-1 parsing and digest calculation stay
compatible. Schema 2 requires every bundle to include:

- `id`, `version`, `display_name`, and a bounded `summary`;
- `publisher` with stable `id`, display `name`, and credential-free HTTPS URL;
- `license` with a validated expression and a license-text URL for every
  custom `LicenseRef`;
- a credential-free HTTPS `repository` and optional `homepage`;
- `status`, either `active` or `yanked`, plus a reason for a yanked release;
- dependencies and runtime facets with the existing platform, load-plan, and
  capability data;
- exact `bytes` and lowercase SHA-256 for every artifact and wheel.

Schema-2 canonical serialization covers all these fields in the index digest.
Unknown fields are rejected rather than silently excluded. A yanked bundle is
visible in explicit inspection output but cannot be newly installed or used as
an update candidate; an already verified local generation remains available
for rollback.

The following limits are enforced before activation:

- 8 MiB downloaded index;
- 128 bundles in one resolved dependency closure;
- 256 artifact and wheel inputs in one generation;
- 256 MiB per input, 1 GiB cumulative downloaded input, and 1 GiB cumulative
  extracted archive content per generation;
- bounded dependency, facet, capability, metadata, and load-plan collection
  sizes;
- no credential-bearing, localhost, local-domain, or private/reserved literal
  IP artifact URLs, including redirect targets.

The public CLI adds:

```text
liteyuki plugin search [query] [--source ID] [--refresh] [--json]
liteyuki plugin install BUNDLE --target TARGET [--source ID] [--yes]
```

Search defaults to the official source and reports source, ID, version,
runtime kinds, license, publisher, and summary. `--json` returns stable
discovery records. `--target` is the canonical target spelling for all
plugin lifecycle commands; `--runtime` remains an Alpha compatibility alias.

Installation displays the selected publisher, license, requested capabilities,
source, and total artifact bytes. It requires an interactive confirmation or
`--yes`. Search and validation never import or execute plugin code.

## Stable NoneBot managed generations

Plugin target resolution accepts either a configured supervised runtime or a
configured broker bridge and rejects ambiguous IDs. Alpha12 enables managed
facets only when the installed bridge definition explicitly supplies an
installer and generation probe and has the `stable` support grade. NoneBot is
the only broker bridge meeting that contract in this stage. AstrBot, v6, and
MoFox remain outside the new path even where they retain package-local
compatibility helpers.

A candidate NoneBot generation is built in a new directory and virtual
environment. It contains the exact installed NoneBot runtime distribution plus
hash-verified plugin wheels. Its host-specific installer produces a bounded
`load-plan.json`, and its probe imports the runtime and every declared plugin
before the deployment pointer changes.

When a managed generation is active, the NoneBot host obtains its interpreter
and `LITEYUKI_PLUGIN_GENERATION` from the daemon-owned process graph. It
loads only the verified generation plan. Non-empty manually configured
`plugins` or `plugin_dirs` are rejected in this mode so one bridge cannot mix
configuration-owned and generation-owned executable code.

Every successful install, update, enable, disable, uninstall, or rollback asks
a running instance daemon to rebuild the Broker -> Bridge -> Kernel graph. If
there is no daemon, the command completes the atomic pointer change and states
that a restart is required. If the candidate bridge fails its startup health
gate, the daemon restores the previous generation or deactivates a failed
first generation, then starts the previous graph before reopening admission.

Generation and artifact residency is bounded by default. Each target retains
only its active and previous generation. Successful activation and failed
candidate cleanup remove older generation directories and content-addressed
artifacts not referenced by any retained generation. `plugin gc` remains an
explicit repair/audit command and reports both generation and artifact counts;
normal update traffic no longer requires it to prevent unbounded disk growth.

## Reference artifact and release order

The Alpha12 bundle includes
`liteyukibot-v7-example-nonebot-plugin==0.1.0`, a minimal reference wheel used
to prove plugin loading and lifecycle without a network account or platform
adapter. It is independently versioned and is not represented as a lockstep
kernel component.

Release work follows this order:

1. Commit the schema-1 empty index and repository governance controls.
2. Merge the main-repository schema-2, NoneBot-generation, license, reference
   artifact, test, benchmark, and `7.0.0a12` changes.
3. Build and verify the complete signed candidate bundle from a clean checkout.
4. Create the immutable `v7.0.0a12` GitHub Release.
5. Generate the first schema-2 official entry from the released signed
   manifest, never from a manually predicted filename or digest.
6. Merge the generated index and repeat installation through the public raw
   index and immutable GitHub Release URLs.

The release is not declared complete until step 6 passes. A bad immutable
artifact is corrected with a new pre-release version rather than a moved tag.

## External-host and performance proof

Before the tag, an isolated workspace outside the checkout installs the built
reference wheel into a NoneBot generation and proves install, real host load,
disable, enable, rollback, uninstall, and cleanup. Deterministic repository
tests separately prove daemon restart, bridge registration, candidate-startup
rollback, and previous-graph recovery. After the tag, the external workflow
runs against the public official index and release URLs. Local retained
evidence may use `F:\tmp`; repository and CI tests use temporary directories
and do not depend on local state.

Benchmark schema 2 keeps independent child processes and the existing event,
function, EventBus, and Broker workloads. Alpha12 adds index search/parse and
generation churn measurements. The churn workload repeatedly activates
generations and collects artifacts while the stores remain alive; it must end
with at most active plus previous state and no unreferenced artifacts. Timing,
RSS, retained Python allocations, and disk counts remain manually reviewed
evidence rather than shared-runner pass/fail thresholds.

## Exit criteria

- The public empty index is fetchable before schema-2 rollout, and the final
  schema-2 index passes governance, canonicalization, URL, size, license, and
  artifact-hash validation.
- Schema-1 clients remain compatible; schema-2 metadata is preserved in the
  digest, search output, generation snapshot, and rollback path.
- The stable NoneBot bridge passes candidate probe, full graph restart,
  startup-failure rollback, first-install deactivation, and manual-configuration
  conflict tests.
- Repeated plugin updates retain at most two generations per target and remove
  every artifact not referenced by a retained generation.
- The pre-release and public-endpoint external-host workflows pass from built
  artifacts without importing the source checkout.
- Ruff, strict mypy, full pytest, dependency audits, WebUI build, workspace and
  example builds, install verifiers, Alpha bundle verification, and both
  three-sample benchmark profiles pass.

## Deferred work

Alpha12 does not add a hostile-code sandbox, managed AstrBot plugin workspace,
distributed or durable broker delivery, automatic benchmark failure
thresholds, generic `CallApi`, or message editing.

The WebUI refresh and extraction of LYF TextMate rendering into the separate
`LiteyukiStudio/lyf-textmate` / `@liteyuki/lyf-textmate` project are not part of
Alpha12. The maintainer will open Alpha13 only after joining the `@liteyuki`
npm team; Alpha12 does not create that repository, package, or milestone.

The 72-hour soak is a stable-release qualification gate rather than an Alpha12
gate.
