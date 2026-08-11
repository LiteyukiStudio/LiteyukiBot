# Custom runtime development

Custom runtimes are supervised local subprocesses. Configure an explicit
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

The complete protocol-v3 child is in
[`examples/custom-runtime`](../../examples/custom-runtime). It uses
`RuntimeClient.from_environment("custom")`, calls `connect()`, then declares
capabilities with `ready()`.

## Kernel-mediated routes

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

## Single reader rule

Exactly one coroutine calls `RuntimeClient.receive()`. `execute_action()` sends
an Action request and waits on a Future; it does not read the socket. Therefore
an Event handler that calls `execute_action()` must run in a separate tracked
task while the receive pump continues routing Action responses. Calling and
awaiting it inline in the receive loop deadlocks until timeout.

The host must also:

- bound the number of handler tasks and return `overloaded` when full;
- send exactly one `EventAccepted` for each Event message;
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

Protocol v2/v3 Event receipt requires `runtime.events.receive`. Child-originated
Actions require protocol v3 and `runtime.actions.send`. Capability names and
protocol versions are negotiated exactly rather than inferred.

The protocol is pre-stable. v3 remains the normal development target and may
change without backwards-compatibility shims during alpha. v4/v5 are reserved
for large protocol redesigns, and no pre-stable version will exceed v5. Pin the
LiteyukiBot alpha version used to build and test an external runtime.

## Testing

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
