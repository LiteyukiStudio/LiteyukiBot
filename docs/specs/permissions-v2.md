# Permission v2

- Specification version: `2`
- Applies to: Alpha 2 extension host authorization
- Compatibility: the package service is `liteyukibot.permissions@2`;
  EventEnvelope calls remain only as an explicit migration adapter for packages
  not migrated until Alpha 3.

`AuthorizationContext` contains only `event_id`, `runtime_id`, `bot_id`, and
optional `actor_id`. Message content, adapter payloads, Tool arguments/results,
and exception text never enter an authorization decision or audit record.

`plugin_capabilities` is an exact extension-ID ceiling map. Limited activation
fails closed when the target is unknown or any requested capability is outside
the ceiling. Full Cordis access bypasses principal checks by policy but retains
redacted audit evidence. New Tool and privileged host paths must authorize both
caller and provider against the original context.

Evidence: `tests/test_alpha2_contracts.py` and
`packages/permissions/tests/test_permissions.py`.
