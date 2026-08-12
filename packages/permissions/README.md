# LiteyukiBot v7 Permissions

`liteyukibot-v7-permissions` provides the versioned
`liteyukibot.permissions@1` service for native LiteyukiBot v7 plugins.

The service resolves exact `runtime_id`, `bot_id`, and `actor_id` principals
into named roles and capability tokens. Wildcards and actor-only global
identities are intentionally unsupported.

```toml
[plugins]
enabled = ["liteyukibot.permissions"]

[plugins.config."liteyukibot.permissions".roles]
operator = ["liteyukibot.status.read", "example.echo.manage"]

[[plugins.config."liteyukibot.permissions".grants]]
runtime_id = "nonebot"
bot_id = "10000"
actor_id = "20000"
roles = ["operator"]
capabilities = ["example.echo.use"]
```

Consumers declare `ServiceRequirement(PERMISSION_SERVICE)` and resolve a
`PermissionService` from their plugin context. `allows(event, capability)`
performs an exact, fail-closed check. `resolve(event)` returns a frozen snapshot
for diagnostics. Every event has `public`; plugins check capabilities rather
than deployment role names.

Privileged boundaries call `decide(event, capability, component=...)` instead.
It has the same exact policy outcome and keeps a bounded in-memory audit
snapshot available through `audit()`. Each record contains only the capability,
principal tuple, component, event ID, allow/deny outcome, and stable reason;
message content, API parameters, and tool arguments are never captured.

## Development

Permission decisions must remain exact-principal and fail closed. Keep audit
records redacted, then run `uv run pytest packages/permissions/tests` and
`uv run python -m scripts.run_permissions_install` after changes.
