# LiteyukiBot AstrBot Runtime API

This package contains the framework-neutral typed facade used by the Alpha9
AstrBot runtime API. It deliberately does not depend on AstrBot itself.

The supported portable surface includes `event.snapshot()`, `event.send()` for
text or a Liteyuki `Message`, `bot.snapshot()`, and `bot.send(message,
conversation)`. These methods return JSON-safe DTOs and never expose AstrBot
objects, native message chains, or arbitrary API passthrough.
