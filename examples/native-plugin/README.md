# Native plugin example

This package exposes `example.echo` through the `liteyukibot.plugins` entry
point. Its handler replies to message events through protocol-neutral v7 Event
and Action models. The plugin explicitly removes its EventBus subscription in
the stop callback.

```bash
uv build
```
