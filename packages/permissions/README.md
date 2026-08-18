# LiteyukiBot v7 Permissions

`liteyukibot-v7-permissions` provides the versioned
`liteyukibot.permissions@2` service for Alpha 2 extension hosts.

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

Limited hosts declare requested capabilities and are activated only when every
request is inside the configured `plugin_capabilities` ceiling. The v2 host
surface accepts `AuthorizationContext`; EventEnvelope remains only for the
command/resource event path. The `permissions.check` Tool evaluates the
current invocation context and never accepts a caller-supplied principal.

Privileged v2 boundaries call `decide(context, capability, component=...)`.
The legacy adapter may accept an event only while a package is awaiting Alpha 3
migration. It has the same exact policy outcome and keeps a bounded in-memory audit
snapshot available through `audit()`. Each record contains only the capability,
principal tuple, component, event ID, allow/deny outcome, and stable reason;
message content, API parameters, and tool arguments are never captured.

## Development

Permission decisions must remain exact-principal and fail closed. Keep audit
records redacted, then run `uv run pytest packages/permissions/tests` and
`uv run python -m scripts.run_permissions_install` after changes.
