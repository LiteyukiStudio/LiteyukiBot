# LiteyukiBot NoneBot Runtime API

This package contains the framework-neutral typed facade for the Alpha9
NoneBot runtime API. It deliberately does not depend on NoneBot or any
NoneBot adapter.

The supported portable surface includes `event.snapshot()`,
`event.send()` for text or a Liteyuki `Message`, `bot.snapshot()`, and
`bot.send(message, conversation)`. These methods return JSON-safe DTOs and
never expose NoneBot objects, adapter objects, or arbitrary API passthrough.
