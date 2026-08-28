# LiteyukiBot Cordis Plugin v1

`liteyukibot-v7-cordis` is the trusted in-process extension layer for
LiteyukiBot Alpha15. It depends only on `liteyukibot-v7-kernel`.

Plugins publish one callable factory in the `liteyukibot.cordis_plugins`
entry-point group. The root application loads only IDs explicitly listed in
`[cordis].enabled`, preserves configuration order, and passes each factory a
child `Scope` with its `[cordis.config.<id>]` mapping.

The public surface is intentionally small:

- `Scope.child/provide/use/own/on/aclose`
- `CordisManager.activate/start/dispatch/aclose`

There is no separate host entry point, native plugin host, runtime API,
scheduler, middleware, parallel fanout or hot reload.

Plugin factories may be synchronous or asynchronous, but event handlers
registered through `Scope.on` must be async callables. Synchronous handlers are
rejected at registration so they cannot block the application event loop.
Owned disposers and resources exposing `aclose` or `close` must also be async
callables; synchronous cleanup is rejected instead of running outside the
shutdown deadline contract.

Root command handlers and resource-provider operations use the same async-only
boundary before they are attached to Cordis.

Run `uv run pytest packages/cordis/tests` after changes.
