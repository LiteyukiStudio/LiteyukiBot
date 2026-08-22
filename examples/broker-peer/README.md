# B7 broker-peer example

This installable example uses the public `BrokerPeerServer` and `BridgeClient`
APIs. Its self-test completes bridge registration, an event ingress and lease,
an `experimental.echo` runtime API call, event completion, unregister, and
shutdown over the real ZMQ transport.

Build it from the repository root:

```bash
uv build --project examples/broker-peer --out-dir dist/examples
```

The example does not create bridge IDs, session IDs, kernel event IDs, leases,
or delivery recipients. It is intentionally a protocol sample, not a process
supervisor or a framework adapter.
