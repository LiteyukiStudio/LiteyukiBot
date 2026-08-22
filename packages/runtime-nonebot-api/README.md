# LiteyukiBot NoneBot Runtime API

This package contains the framework-neutral typed facade for the Alpha10.1
NoneBot runtime API v1.2. It deliberately does not depend on NoneBot or any
NoneBot adapter.

The supported portable surface includes `event.snapshot()`,
`event.send()` for text or a Liteyuki `Message`, `bot.snapshot()`, and
`bot.send(message, conversation)`. These methods return JSON-safe DTOs and
never expose NoneBot objects, adapter objects, or arbitrary API passthrough.
Snapshot and send result types are kernel-owned portable DTOs; provider-specific
values are available only under explicit extensions.

Native/Cordis extensions declare a matching `RuntimeRequirement` and use the
kernel `@runtime` decorator. Keep the requirement optional when the provider
is an enhancement; check `proxy.available` before calling it and handle
`RuntimeUnavailable` or stable `RUNTIME_*` errors. The isolated API verifier
is the reference for the installed entry-point and DTO boundary.
