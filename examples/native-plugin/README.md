# Native/Cordis plugin example

This package exposes `example.echo` and `example.runtime` through the
`liteyukibot.plugins` entry point. The echo handler replies to message events
through protocol-neutral v7 Event and Action models. The runtime facade is a
separate optional plugin so the basic echo example keeps no-provider startup
semantics.

It also demonstrates the shared Native/Cordis runtime facade contract. The
`RuntimeRequirement` and `@runtime` declaration request the optional NoneBot
`event.snapshot` API v1.2. The handler checks `available` and tolerates an
uninstalled or disconnected provider; it never imports NoneBot.

```python
@runtime("nonebot", api="event", version="^1.2", optional=True, as_="nonebot")
async def observe(event: EventEnvelope, *, nonebot: Any) -> HandlerResult | None:
    if not nonebot.available:
        return None
    await nonebot.snapshot()
    return None
```

Install `liteyukibot-v7-runtime-nonebot-api` separately when the typed facade
is desired. The plugin remains framework-neutral.
Runtime requirements are activation capabilities, so the host permission
ceiling must allow `runtime.nonebot.event.snapshot` even when the provider is
optional.

```bash
uv build
```
