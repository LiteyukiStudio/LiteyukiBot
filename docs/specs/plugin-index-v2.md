# Plugin Index and Managed Generation v2

- Applies to: LiteyukiBot v7 Alpha12 (`7.0.0a12`) and later v7 clients.
- Boundary: metadata-only plugin discovery, hash-verified inputs, and runtime
  generation deployment.
- Compatibility: schema-1 indexes remain readable with their historical digest
  shape; schema-2 fields are never silently discarded.

## Index

The default source is the official raw GitHub URL recorded in
`src/liteyukibot/plugin_sources.py`. A schema-2 index contains bounded bundle
metadata, publisher identity, SPDX or accepted LSO-Common/Commercial v1.4
license terms, public repository URLs, active/yanked status, dependencies, and
one or more runtime facets. Every facet input declares an exact positive byte
length and lowercase SHA-256 digest.

Schema-2 objects reject unknown fields. The digest is calculated from the
canonical schema, sorted by bundle ID, with all validated metadata, load plans,
capabilities, and artifact records included. A yanked release remains visible
for inspection and in retained generation snapshots, but cannot be selected by
new installation or update resolution.

Sources and artifact URLs must be credential-free HTTPS and must not use local
hostnames or literal private/reserved addresses. Index downloads are capped at
8 MiB. A resolved generation is capped at 128 bundles, 256 artifact/wheel
inputs, 256 MiB per input, 1 GiB cumulative input bytes, and 1 GiB cumulative
expanded archive bytes. Load plans and metadata collections are bounded before
activation.

## Managed generations

The target ID namespace combines configured supervised runtimes and configured
broker bridges; an ID present in both is rejected. Only a stable bridge that
declares both a facet installer and a startup probe may own managed generations.
Alpha12 qualifies the NoneBot bridge only.

Composition discovers bridge entry points, applies that eligibility policy,
and supplies a resolved managed target to plugin installation. The installer
receives only the narrow artifact-store and facet contracts from
`liteyukibot.bridge_contracts`; neither Broker discovery nor the concrete
plugin-store API is part of the package-owned facet materialization contract.

Installation materializes a new generation directory and virtual environment,
installs the exact bridge distribution plus hash-verified wheels, writes a
manifest and host load plan, and runs the host probe before changing the atomic
deployment pointer. The daemon starts a bridge from the generation interpreter
and sets `LITEYUKI_PLUGIN_GENERATION`; manually configured NoneBot `plugins` or
`plugin_dirs` are rejected while that variable is present.

Each target retains its active and previous generation. Successful lifecycle
changes ask a running instance daemon to rebuild the Broker -> Bridge -> Kernel
graph. A failed candidate startup restores the previous graph, or deactivates
the target when no previous generation exists. Offline commands complete the
pointer change and report that a restart is required. Generation and artifact
collection runs after both successful and failed candidates so unreferenced
content does not accumulate. Native plugin code remains trusted process code;
managed generations are not a hostile-code sandbox.

## Verification

Run the focused contract suite with:

```bash
uv run pytest tests/test_plugin_store.py tests/test_plugin_install.py \
  tests/test_plugin_sources.py tests/test_daemon.py \
  packages/runtime-nonebot/tests/test_nonebot_bridge.py
uv run python scripts/run_nonebot_plugin_e2e.py --wheel-dir dist/workspace \
  --workspace tmp/alpha12-nonebot-e2e
```

The release workflow repeats the E2E from built wheels with `--no-project` so
the verifier does not import the source checkout.
