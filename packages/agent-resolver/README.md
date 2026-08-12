# LiteyukiBot Agent Resolver

This package resolves declarative agent-module closures and exposes a bounded,
searchable tool tree. It intentionally does not install packages, create
environments, execute tools, or import agent frameworks.

## Development

Keep resolution declarative and side-effect free. Run
`uv run pytest packages/agent-resolver/tests` and
`uv build --project packages/agent-resolver` after changing package metadata or
resolver contracts.
