# LiteyukiBot v7 Kernel

`liteyukibot-v7-kernel` owns the protocol-neutral Alpha15 contracts:

- immutable JSON-safe event, message and action models;
- bounded `EventBus` and source-correlated `ActionService`;
- service registry, owned background tasks and application status.

Messages support text, mention, reply and image segments. The only action is
`SendMessage`. The kernel does not own configuration, CLI, Cordis discovery,
OneBot transport or built-in business features, and it does not import the
root application package.

Applications normally install `liteyukibot-v7`; component authors may depend
directly on this package for the small contract surface.
