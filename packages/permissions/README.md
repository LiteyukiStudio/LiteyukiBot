# LiteyukiBot v7 Permissions

`liteyukibot-v7-permissions` provides the versioned
`liteyukibot.permissions@1` service for native LiteyukiBot v7 plugins.

The alpha contract recognizes `public` and `operator`. Operators are exact
`runtime_id`, `bot_id`, and `actor_id` triples; wildcards and actor-only global
identities are intentionally unsupported.

```toml
[plugins]
enabled = ["liteyukibot.permissions"]

[plugins.config."liteyukibot.permissions"]
operators = [
  { runtime_id = "nonebot", bot_id = "10000", actor_id = "20000" },
]
```

Consumers declare `ServiceRequirement(PERMISSION_SERVICE)` and resolve a
`PermissionService` from their plugin context. Unknown permission strings are
denied, allowing a later capability model without changing the service method
signature.
