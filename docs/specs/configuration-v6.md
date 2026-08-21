# Configuration v6

- Specification version: `6`
- Applies to: the Alpha8b workspace configuration and daemon-owned instance
  update contract.
- Compatibility: v6 is the active schema. Missing versions and versions `1`
  through `5` are migration input; versions greater than `6` are unsupported.

Configuration remains typed, strict, and loaded in precedence order: defaults,
root configuration, instance overlay, explicit configuration path, environment
overrides, and CLI overrides. A root workspace configuration must declare
`config_version = 6`.

## Migration Boundary

The kernel never rewrites a v5 configuration automatically. `liteyuki config
upgrade` preserves the source in a read-only timestamped backup, writes a v6
template and instructions below `.liteyuki/config-upgrades/`, and raises a
`migration_required` diagnostic. Startup, profile updates, and rollback remain
blocked until the operator installs a valid v6 configuration. A future schema
is rejected without generating migration material.

## Daemon-Owned Graph

`[daemon]` controls the instance graph and update bounds:

| Field | Default | Meaning |
| --- | ---: | --- |
| `manage_broker` | `true` | daemon owns the Broker process |
| `manage_bridges` | `true` | daemon owns configured non-kernel Bridges |
| `startup_timeout_seconds` | `30` | bounded process readiness wait |
| `stop_timeout_seconds` | `10` | bounded graceful process stop |
| `drain_timeout_seconds` | `30` | bounded Broker delivery drain |
| `health_timeout_seconds` | `30` | bounded candidate Kernel health wait |

Atomic updates require the daemon-owned Broker, bridge, and Kernel graph plus a
dedicated `broker.management_token_secret`. Standalone Broker and Bridge
commands remain supported but are not eligible for atomic profile updates.

## Bundle Compatibility

Verified Alpha8b profiles record configuration version, release tag/version,
manifest digest, dependency-lock digest, and the artifact closure. The daemon
rejects a candidate whose configuration contract is not v6 before Broker
admission is frozen.

## Evidence

Run `uv run pytest tests/test_config_v7.py tests/test_config_workspace.py
tests/test_alpha8b.py` and `uv run ruff check src/liteyukibot/config
tests/test_config_v7.py tests/test_config_workspace.py tests/test_alpha8b.py`.
