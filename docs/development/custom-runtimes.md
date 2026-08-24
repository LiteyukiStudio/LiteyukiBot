# Custom runtime and broker-peer development

## Broker peers (implemented B7 contract)

New cross-process work targets the standalone broker peer contract, not the
legacy supervised-child protocol below. Run the broker with `liteyuki broker
run`; run a configured bridge with `liteyuki bridge run <bridge-id>`. Bridge
launchers are discovered from `liteyukibot.bridges`. A bridge process receives
its configured bridge ID and vault-resolved token from its launcher, constructs
`BridgeClient`, and registers a `BridgeManifest` using the protocol-7 control
and business catalogs described by [Broker Peer IPC v7](../specs/runtime-ipc-v7.md).

Registration declares `full` or `limited` access, literal or single-segment
dot-separated topic subscriptions, and action `(kind, resource)` or
`(kind, resource_prefix)` namespaces the bridge can own. The
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
is supplied under its `options` mapping. An installed bridge entry point must
return `BridgeDefinition(kind, grade, distribution, launch)`; the catalog
validates that its entry-point name, distribution, declared kind, and support
grade agree. NoneBot is the stable reference bridge. AstrBot is an experimental
platform gateway, not a supervised runtime child: it owns the public AstrBot
extension API, platform adapters, local pipeline, and native replies while it
also publishes normalized `message.created` and handles `message.send`.

A new bridge must keep framework SDK objects, credentials, connections, and
event/action conversion in the package that owns that framework. The kernel
must not import the bridge SDK. Document its lifecycle and test it against the
same peer contract before claiming a support grade.

For B7, the portable surface is intentionally narrow: publish
`message.created` and handle `message.send`. The resource key for a bot owned
by bridge `bridge-id` is `bot:bridge-id:<bot-id>`. The kernel peer may issue
that action only while dispatching the matching active broker delivery. `CallApi`,
message editing, and a generic function/decorator DSL are deferred to later
version planning.

The installable [B7 broker-peer example](../../examples/broker-peer) runs this
lifecycle over the real ZMQ transport, including registration, ingress, a
lease-bound experimental runtime API, completion, unregister, and shutdown.
Use it as a protocol smoke test, not as a framework adapter template.

## Runtime API facade for plugins

Native and Cordis extensions share the kernel-owned `RuntimeRequirement` and
`@runtime` declarations. A provider facade is an optional dependency of the
extension, not a kernel import:

```python
from typing import Any

from liteyukibot import runtime


@runtime("astrbot", api="event", version="^1.2", optional=True, as_="astrbot")
async def handler(event: object, *, astrbot: Any) -> None:
    if not astrbot.available:
        return
    snapshot = getattr(astrbot, "snapshot", None)
    if callable(snapshot):
        await snapshot()
```

The manifest must contain the same runtime, API, version, optional flag, and
operation list. Use `bridge_id` on both declarations when targeting one named
bridge. The full portable operation set, catalog fingerprint rule, provider
checklist, and failure guide are in
[`runtime-api-conformance.md`](runtime-api-conformance.md).

The v6 and MoFox compatibility packages are limited bridge examples. v6 keeps
its matcher/session compatibility process-local and loads only configured
`liteyukibot.v6_plugins` entry points. MoFox loads only a configured isolated
Neo-MoFox workspace. Neither package is a legacy runtime entry point, owns a
platform action, or uses managed plugin projection.

## Legacy supervised child runtimes (historical)

The remaining guidance records the former v5 child-supervisor implementation.
Its source, test harness, and matching example remain temporarily as migration
material, but current App, CLI, initializer, daemon, and plugin installation
paths do not discover or launch it. It does not define a Broker peer and must
not be used for new work.

Legacy custom runtimes were supervised local subprocesses. The former
supervisor injected authenticated loopback connection values through
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

This historical route model is not a recommendation for AstrBot. The B7
AstrBot integration is a broker gateway and must not use `kind = "custom"` or
`runtime_event_routes`. Compatibility hosts must now provide a dedicated Broker
bridge design.

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

The historical v5 protocol once permitted one explicitly defined kernel
control request to a child declaring `runtime.controls.execute`. Alpha6 removed
the Agent-specific Runtime IPC Tool and moved Agent controls to the then-current
Broker Peer IPC v6 `bridge.control.invoke` contract. Current peers use the v7
contract documented above. The child protocol remains historical and must not
be used for a new Agent integration.
Pin the LiteyukiBot version used to build and test any remaining legacy
runtime.

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
