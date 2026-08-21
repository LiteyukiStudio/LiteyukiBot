# LiteyukiBot AstrBot Runtime API

This package contains the framework-neutral typed facade used by the Alpha8
AstrBot runtime API proof. It deliberately does not depend on AstrBot itself.

Alpha8 exposes only `event.snapshot()` and `event.send(message)`. The broader
AstrBot facade is deferred to Alpha9.
