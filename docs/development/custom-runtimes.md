# Custom runtime and broker-peer development

## Broker peers (implemented B5 foundation)

New cross-process work targets the standalone broker peer contract, not the
legacy supervised-child protocol below. Run the broker with `liteyuki broker
run`; run a configured bridge with `liteyuki bridge run <bridge-id>`. Bridge
launchers are discovered from `liteyukibot.bridges`. A bridge process receives
its configured bridge ID and vault-resolved token from its launcher, constructs
`BridgeClient`, and registers a `BridgeManifest` using the protocol-6 control
and business catalogs described by [Broker Peer IPC v6](../specs/runtime-ipc-v6.md).

Registration declares `full` or `limited` access, exact topic subscriptions,
and the action `(kind, resource_prefix)` namespaces the bridge can own. The
broker assigns the session ID and kernel event ID. A bridge must not create
either value, select event recipients, set an absolute monotonic deadline, or
connect directly to another bridge.

`kind = "kernel"` is reserved for LiteyukiApp's in-process full peer. It is
not a `liteyukibot.bridges` entry point, cannot declare action-resource
ownership, and must not be launched with `liteyuki bridge run`. It must use
`access = "full"` and declare at least one subscription. The app registers it
after native plugins start; the broker remains a separate process.

For each `EventMessage`, retain its opaque lease and respond once with
`EventAccepted`, then with `EventCompleted` after the active delivery has a
terminal outcome. `lease_ttl_ms` is advisory only; the broker evaluates its
30-second default timeout. An action request is valid only while the bridge
owns that active delivery and presents the current lease. There is no retry or
replay protocol.

The broker does not provide environment bootstrap, readiness/heartbeat
messages, retries, persistence, or process supervision. The manifest and
token reference are configured under `broker.bridges`; bridge-specific startup
is supplied under its `options` mapping. The B5-4 NoneBot bridge is the
reference implementation. A new bridge must document its own lifecycle and
test it against the same peer contract before claiming compatibility.

For B5-4/B5-5, the portable surface is intentionally narrow: publish
`message.created` and handle `message.send`. The resource key for a bot owned
by bridge `bridge-id` is `bot:bridge-id:<bot-id>`. The kernel peer may issue
that action only while dispatching the matching active broker delivery. `CallApi`,
message editing, and a generic function/decorator DSL are deferred to later
version planning.

## Legacy supervised child runtimes (historical)

The remaining guidance records the former v5 child-supervisor implementation.
It is retained for existing `RuntimeClient` hosts and the matching example; it
does not define a B5 broker peer and must not be used for new broker work.

Legacy custom runtimes are supervised local subprocesses. Configure an explicit
command; the supervisor injects authenticated loopback connection values through
`LITEYUKI_RUNTIME_HOST`, `LITEYUKI_RUNTIME_PORT`, `LITEYUKI_RUNTIME_TOKEN`,
`LITEYUKI_RUNTIME_ID`, `LITEYUKI_RUNTIME_KIND`, and
`LITEYUKI_RUNTIME_RESTART_COUNT`.

```toml
[runtimes.example]
kind = "custom"
command = ["liteyuki-example-runtime"]

[runtimes.example.options]
mode = "example"
```

The complete historical protocol-v5 child is in
[`examples/custom-runtime`](../../examples/custom-runtime). It uses
`RuntimeClient.from_environment("custom")`, calls `connect()`, then declares
capabilities with `ready()`.

## Legacy kernel-mediated routes

Child runtimes never connect to each other. A runtime reports normalized
`EventEnvelope` values to the kernel and submits `ActionEnvelope` values back
to it. The kernel owns cross-runtime delivery and routes an Action to the
runtime named by its `runtime_id`.

An external compatibility host such as AstrBot or MoFox should initially use
`kind = "custom"` and an explicit command. Its bridge translates between the
framework's local event/action objects and these frozen LiteyukiBot models; it
must not serialize framework objects over IPC.

Configure core-to-child event delivery explicitly:

```toml
[[runtime_event_routes]]
sources = ["nonebot"]
target = "astrbot"
messages_only = true
```

Each source and target must name a distinct, enabled configured runtime. Route
delivery is concurrent for matching targets and a rejection is reported as an
EventBus handler failure. The v6 compatibility runtime retains its historical
message-only route by default; an explicit route targeting that runtime
replaces the default.

## Legacy single reader rule

Exactly one coroutine calls `RuntimeClient.receive()`. `execute_action()` sends
an Action request and waits on a Future; it does not read the socket. Therefore
an Event handler that calls `execute_action()` must run in a separate tracked
task while the receive pump continues routing Action responses. Calling and
awaiting it inline in the receive loop deadlocks until timeout.

The host must also:

- bound the number of handler tasks and return `overloaded` when full;
- send exactly one `EventAccepted` for each Event message;
- when declaring `runtime.events.complete`, send exactly one terminal
  `EventCompleted` after each accepted core-to-child Event;
- send exactly one `ActionResponse` for each Action request;
- validate payloads before acting on them;
- cancel and await all owned tasks on Shutdown;
- close the client in `finally`;
- never reconnect itself, because restart limits and backoff belong to the
  supervisor.

The supervisor applies the same protection to child-to-core Events. Each
runtime has `max_inbound_events` (default `100`); additional Events receive
`overloaded` without creating another handler task. Set it in the runtime's
TOML table when the adapter has a known, bounded concurrency requirement.

Protocol v2 through v5 Event receipt requires `runtime.events.receive`.
Child-originated Actions require protocol v3, v4, or v5 and `runtime.actions.send`.
Protocol v4 carries `EventTrace(trace_id, source_runtime_id, source_event_id)`
on core-to-child Events. A v4 child may opt into terminal delivery outcomes with
`runtime.events.complete`; its `EventCompleted` is operational telemetry, not a
second response to `dispatch_event()`. Capability names and protocol versions
are negotiated exactly rather than inferred.

Protocol v5 additionally permits the kernel to send an explicitly defined
control request to a child declaring `runtime.controls.execute`. It is not a
generic RPC surface. The protocol is pre-stable: v5 is the current development
target and may change without backwards-compatibility shims before the stable
v7 release. No pre-stable version will exceed v5. Pin the LiteyukiBot version
used to build and test an external runtime.

## Legacy testing

`RuntimeTestHarness` launches the real command and protocol connection:

```python
from liteyukibot.runtime import RuntimeSpec
from liteyukibot.testing import RuntimeTestHarness


async def verify(event_payload) -> None:
    spec = RuntimeSpec(
        id="example",
        kind="custom",
        command=("liteyuki-example-runtime",),
    )
    async with RuntimeTestHarness(spec) as harness:
        accepted = await harness.dispatch_event(event_payload)
        assert accepted.status == "accepted"
        assert len(harness.child_actions) == 1
```

The harness records child-originated Event and Action payloads before invoking
optional sinks. Without custom sinks it accepts Events and returns a successful
Action result. `dispatch_event()` and `execute_action()` generate correlation
IDs when none are supplied and reject non-positive timeouts through the real
supervisor contract.
