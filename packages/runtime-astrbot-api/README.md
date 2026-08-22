# LiteyukiBot AstrBot Runtime API

This package contains the framework-neutral typed facade used by the Alpha10.1
AstrBot runtime API v1.2. It deliberately does not depend on AstrBot itself.

The supported portable surface includes `event.snapshot()`, `event.send()` for
text or a Liteyuki `Message`, `bot.snapshot()`, and `bot.send(message,
conversation)`. These methods return JSON-safe DTOs and never expose AstrBot
objects, native message chains, or arbitrary API passthrough. Snapshot and send
result types are kernel-owned portable DTOs; AstrBot platform/session fields
remain under the `astrbot` extension namespace. The old text projection is
available as `message_text`; `event.snapshot().message` is now a portable
`Message`.
