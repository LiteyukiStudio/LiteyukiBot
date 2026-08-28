# LiteyukiBot v7 Kernel

`liteyukibot-v7-kernel` owns the protocol-neutral Alpha15 contracts:

- immutable JSON-safe event, message and action models;
- bounded `EventBus` and source-correlated `ActionService`; EventBus queue,
  byte, handler, action and shutdown limits are explicit configuration points;
- service registry, owned background tasks and application status.

Messages support text, mention, reply and image segments. The only action is
`SendMessage`. The kernel does not own configuration, CLI, Cordis discovery,
OneBot transport or built-in business features, and it does not import the
root application package.

Applications normally install `liteyukibot-v7`; component authors may depend
directly on this package for the small contract surface.

EventBus callbacks are async callables so deadline and cancellation behavior is
observable. Synchronous callbacks are rejected instead of blocking the event
loop.

Action backends and authorization policies follow the same async-only rule.
They are validated when `ActionService` is constructed, so action deadlines do
not conceal synchronous work at the adapter boundary.
