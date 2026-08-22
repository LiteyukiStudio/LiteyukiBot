# Native/Cordis plugin example

This package exposes `example.echo` and `example.runtime` through the
`liteyukibot.plugins` entry point. The echo handler replies to message events
through protocol-neutral v7 Event and Action models. The runtime facade is a
separate optional plugin so the basic echo example keeps no-provider startup
semantics.

It also demonstrates the shared Native/Cordis runtime facade contract. The
`RuntimeRequirement` and `@runtime` declaration request the optional AstrBot
`event.snapshot` API v1.2. The handler checks `available` and tolerates an
uninstalled or disconnected provider; it never imports AstrBot.

```python
@runtime("astrbot", api="event", version="^1.2", optional=True, as_="astrbot")
async def observe(event: EventEnvelope, *, astrbot: AstrBotEventProxy) -> HandlerResult | None:
    if not astrbot.available:
        return None
    await astrbot.snapshot()
    return None
```

Install `liteyukibot-v7-runtime-astrbot-api` separately when the typed
`AstrBotEventProxy` facade is desired. The plugin remains framework-neutral.
Runtime requirements are activation capabilities, so the host permission
ceiling must allow `runtime.astrbot.event.snapshot` even when the provider is
optional.

```bash
uv build
```
