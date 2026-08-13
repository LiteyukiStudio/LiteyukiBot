# ADR 0022: Add Runtime IPC v4 Delivery Tracing

- Status: Accepted
- Date: 2026-08-11

## Context

Protocol v3 correlates the immediate acceptance of a core-to-child Event, but
an asynchronous agent or compatibility host can continue work after that
acceptance. The kernel consequently has no normalized way to connect later
runtime logs, Actions, failures, and completion to the original source Event.

Adding fields to v3 Event messages would make older strict wire models reject
the frame. The change also affects the kernel, the shared child client, and
multiple first-party runtime packages, so it meets ADR 0011's threshold for a
cross-cutting protocol generation.

## Decision

Protocol v4 retains the v3 framing, authentication, event, and Action rules.
For every core-to-child Event, the kernel sends `EventTrace` with a stable
`trace_id`, `source_runtime_id`, and `source_event_id`. When the payload is a
portable `EventEnvelope`, its source Event ID is the trace ID. Non-envelope
payloads fall back to the delivery correlation ID.

A v4 child may declare `runtime.events.complete` in READY capabilities. After
it has replied with `event_accepted: accepted`, it sends exactly one
`event_completed` message with `completed` or `failed`. The supervisor retains
the delivery context until that terminal outcome, logs the trace fields, then
releases the context. This is asynchronous operational telemetry:
`dispatch_event()` still returns after `event_accepted` and never waits for
completion.

The capability is required because previously released first-party runtimes can
negotiate v4 after sharing a newer root package but cannot emit the terminal
message. The supervisor keeps their existing bounded delivery context behavior.
V1 through v3 peers retain their old wire shape; no trace field is serialized
to those connections.

## Consequences

First-party event consumers that claim the capability must publish with a root
dependency of at least `liteyukibot-v7==7.0.0a9`. Runtime operations can group
dispatch, completion, and child logs by a stable trace ID without importing a
framework object or opening a direct child-to-child channel.

Completion is intentionally not delivery retry, distributed transactions, or a
cross-runtime RPC result. Retry policy and durable observability remain kernel
concerns and need their own configuration and recovery design.

For a v4 child Action causally produced by a delivered Event, the child may
include that Event's delivery correlation ID in `ActionRequest`. The supervisor
only accepts it while the delivery is active and passes the kernel-validated
`EventTrace` plus original Event payload to the action sink. The sink can then
enforce that action event/runtime/bot routing matches the source Event before
performing adapter-specific authorization. V3 Actions retain the existing
unattributed shape and cannot claim this provenance.

For an agent-harness Event, the kernel may additionally attach an
`agent_tool_catalog`. It is a JSON-only, per-delivery projection of the tool
schemas authorized for the source Event principal. The child receives no
executable handlers or permission state. The kernel rechecks the same
capabilities when a child submits an `agent_tool` request, so a fabricated tool
ID cannot gain authority.
