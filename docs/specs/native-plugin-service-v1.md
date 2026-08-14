# Native Plugin And Service v1

- Specification version: `1`
- Applies to: native kernel plugins and versioned in-process services
- Compatibility: pre-stable public API; dependencies and service versions are
  explicit and fail closed

## Plugin Boundary

Native plugins load in the kernel process through declared metadata and a
bounded lifecycle. They declare required services and capabilities instead of
retaining `LiteyukiApp`, importing runtime internals, or obtaining a general
kernel handle. Plugin failures are isolated at discovery/startup boundaries and
reported as diagnostics without leaking configuration secrets.

Services use a stable name and integer version. A consumer resolves only a
declared requirement; providers expose the narrow interface documented by the
owning package. The kernel status service is read-only and returns an immutable
snapshot of version, state, uptime, plugin/runtime state, runtime health, and
outstanding Event count.

## Capability And Permission Boundary

Capabilities are named, exact tokens. The first-party permissions package
resolves exact `(runtime_id, bot_id, actor_id)` principals to role/capability
snapshots and fails closed. Privileged boundaries record bounded redacted audit
decisions; message content, tool arguments, and API payloads are excluded.

## Evidence

Read the package README beside each provider and run the owning package tests.
Kernel plugin behavior is protected by `tests/test_plugins.py` and
`tests/test_app_v7.py`.
