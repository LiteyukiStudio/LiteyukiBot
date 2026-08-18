# LiteyukiBot v7 Resources

`liteyukibot-v7-resources` provides the optional
`liteyukibot.resources@2` service for declarative, protocol-neutral resource
management in native plugins.

The service owns resource registration, field validation, principal targeting,
and capability checks. Resource providers own their data and persistence. Its
Alpha 3 inspect/set/delete Tools always target the current invocation
principal; they cannot override actor identity.

## Development

Resources own declarations and authorization conventions, not provider data.
Run `uv run pytest packages/resources/tests` and
`uv run python -m scripts.run_resources_install` after changes.
