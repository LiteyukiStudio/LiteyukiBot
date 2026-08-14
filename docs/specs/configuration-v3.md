# Configuration v3 (Superseded)

- Specification version: `3`
- Applies to: superseded `config_version = 3` workspace configuration
- Compatibility: newer schemas are rejected; older or missing schemas produce
recoverable upgrade material rather than being silently rewritten

Configuration is typed, strict, and loaded through the documented precedence:
defaults, root configuration, instance overlay, explicit configuration path,
environment overrides, and CLI overrides. Diagnostics retain provenance and
redact secret values. TOML rendering omits optional null object fields and
rejects null array values.

Secrets are vault references in configuration. Plaintext is encrypted in the
local vault and is injected only into the declared child environment. Secrets
never enter runtime IPC, control responses, logs, diagnostics, or exceptions.

`config upgrade` preserves the source, writes a backup and current template,
and is idempotent until explicitly refreshed. Validation rejects non-loopback
HTTP binding and invalid runtime, plugin, and instance settings before startup.

## Evidence

The complete operator workflow remains in `docs/configuration.md`. Run
`uv run pytest tests/test_config_v7.py tests/test_config_initializer.py tests/test_config_inspection.py tests/test_config_vault.py tests/test_config_workspace.py`.
