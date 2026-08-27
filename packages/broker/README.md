# LiteyukiBot v7 Broker

The `liteyukibot-v7-broker` distribution owns the authenticated cross-process
Broker boundary for LiteyukiBot v7. It contains LYIP transport, bridge
registration, capability and resource admission, event delivery leases, the
bounded in-memory ledger, diagnostics, lifecycle control, and reusable bridge
host coordination.

The package depends only on the protocol-neutral kernel plus transport and
schema libraries. Application configuration, vault resolution, EventBus
integration, daemon orchestration, and framework lifecycle remain owned by the
root composition package or the bridge package that owns the framework.

The public Python namespace is `liteyukibot_broker`.
