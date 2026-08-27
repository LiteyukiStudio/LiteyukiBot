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

Run `uv run pytest packages/cordis/tests` after changes.
