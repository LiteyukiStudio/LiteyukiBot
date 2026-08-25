# LiteyukiBot v7 Kernel

Protocol-neutral contracts and the in-process event kernel shared by
LiteyukiBot v7 components.

This package owns JSON-safe event and action DTOs, authorization and
capability declarations, service and lifecycle contracts, bridge contracts,
the EventBus, and the portable Runtime API contract. It does not own the CLI,
application composition, Broker service, plugin installation, daemon, WebUI,
or framework integrations.

Applications should normally install `liteyukibot-v7`. Component authors may
depend on `liteyukibot-v7-kernel` when they need only the protocol-neutral
contract surface.
