# Configuration v4

- Specification version: `4`
- Applies to: current `config_version = 4` workspace configuration
- Compatibility: root configurations without `config_version`, and every
  version through `3`, are pre-release input. Startup preserves them and
  blocks for a manual upgrade. Versions greater than `4` are rejected.

Configuration is typed, strict, and loaded in precedence order: defaults, root
configuration, instance overlay, explicit configuration path, environment
overrides, and CLI overrides. Diagnostics retain provenance and redact secret
values. A root workspace configuration must declare version `4`; lower-level
configuration loading may omit it only to support partial programmatic layers.

## LYIP

`[lyip]` owns the requested transport and fixed capacity policy. It does not
claim native availability.

| Field | Default | Valid values |
| --- | --- | --- |
| `default_backend` | `auto` | `auto`, `shm`, `zmq` |
| `capacity_profile` | `balanced` | `latency`, `balanced`, `throughput` |
| `terminal_capacity` | `16384` | `1024..262144` |
| `terminal_ttl_seconds` | `3600` | `60..86400` |
| `dev_summary_ttl_seconds` | `900` | `60..3600` |
| `zmq_large_payload_fallback` | `false` | boolean |

The resolved per-direction profiles are immutable:

| Profile | Business slots | Control slots | Blob arena | ZMQ HWM |
| --- | ---: | ---: | ---: | ---: |
| `latency` | 1024 | 64 | 8 MiB | 1024 |
| `balanced` | 4096 | 256 | 32 MiB | 4096 |
| `throughput` | 16384 | 512 | 128 MiB | 16384 |

`[lyip.links."<runtime-id>"]` can set `backend` (`shm` or `zmq`) and/or
`capacity_profile`; omitted values inherit the global policy. A nested
`capacity` override is all-or-nothing: it must include `business_slots`,
`control_slots`, `blob_arena_mib`, and `zmq_hwm`. The first, second, and fourth
values are powers of two in `256..65536`, `32..4096`, and `256..65536`;
`blob_arena_mib` is a power of two in `4..512`.

A worker resolves a requested link once at startup and never switches it live.
Beta3's active child lifecycle binds ZMQ. The native diagnostics report wheel,
ABI, platform, and fallback reason without becoming a configuration flag; the
optional native package exposes an SPSC ring primitive, but no SHM LYIP
transport adapter. Consequently `auto` and `zmq` resolve to ZMQ; an explicit
`shm` request fails at startup until that adapter is implemented, regardless of
a locally importable native wheel.

## WebUI And Development

`[webui]` is loopback-only. `mode` is `disabled`, `on_demand`, or `always`.
`always` starts with the daemon; `on_demand` starts for authenticated control
requests and uses the idle timer; `disabled` rejects WebUI controls. Port `0`
selects a random port; a fixed start port probes 20 consecutive ports.

| Field | Default | Valid values |
| --- | --- | --- |
| `idle_shutdown_seconds` | `300` | `30..3600`, applies to `on_demand` |
| `ticket_ttl_seconds` | `60` | `15..300` |
| `session_idle_seconds` | `1800` | `60..14400` |
| `session_max_seconds` | `28800` | `300..86400`, at least idle window |

Origin and Host checks, CSRF and cookie flags, one-use tickets, and daemon
restart invalidation are server policy, not configuration options.

`[development]` is opt-in. `allow_drills` and `watch_auto_restart` each require
`enabled = true`; `watch_debounce_seconds` is positive. Read-only diagnostics
remain available outside development mode.

`logging.payload_mode = "full"` is a development-only exception. It requires
development enabled, a `logging.file` below `core.data_dir`, `console = false`,
and `json_lines = false`. `payload_exclude_runtimes` is nonempty only in full
mode. Full payloads never enter WebUI, APIs, SSE, evidence exports, or the
operation audit store.

## Cutover And Recovery

`liteyuki config upgrade` never edits the root `liteyuki.toml`. For a missing
version or a version through `3`, it copies the exact source to a timestamped
read-only `.liteyuki/config-backups/<timestamp>/liteyuki.toml`, then writes a
fresh v4 template and instructions under `.liteyuki/config-upgrades/`. An old
file is not parsed as v4 before backup, so removed fields do not prevent
recovery. Repeated calls use the first material until `--refresh`, which creates
a new backup and template set. Startup remains blocked until the operator
replaces the root with valid v4 TOML. The backup can only be used by an older
pre-v4 beta; v4 has no rollback command because it never changed the root.

Versions greater than `4` are rejected without backup or generated material.

## Evidence

Run `uv run ruff check src/liteyukibot/config tests/test_config_v7.py
tests/test_config_workspace.py`, `uv run mypy src/liteyukibot/config
tests/test_config_v7.py tests/test_config_workspace.py`, and `uv run pytest
tests/test_config_v7.py tests/test_config_initializer.py
tests/test_config_inspection.py tests/test_config_vault.py
tests/test_config_workspace.py`.
