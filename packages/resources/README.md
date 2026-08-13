# LiteyukiBot v7 Resources

`liteyukibot-v7-resources` provides the optional
`liteyukibot.resources@1` service for declarative, protocol-neutral resource
management in native plugins.

The service owns resource registration, field validation, principal targeting,
and capability checks. Resource providers own their data and persistence. The
first-party profile plugin uses this contract without requiring resources to
own a database or a kernel storage service.

## Development

Resources own declarations and authorization conventions, not provider data.
Run `uv run pytest packages/resources/tests` and
`uv run python -m scripts.run_resources_install` after changes.
