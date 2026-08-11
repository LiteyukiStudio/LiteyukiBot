# ADR 0021: Define Kernel-Mediated Runtime Integration

- Status: Accepted
- Date: 2026-08-10

## Context

NoneBot, v6, and external compatibility hosts such as AstrBot or MoFox need to
cooperate without importing each other's framework objects or opening
unmanaged process connections. Runtime IPC v3 already provides bidirectional
Events and Actions, but only v6 had an application-level event forwarding rule.

## Decision

The kernel is the sole runtime communication hub. Child runtimes connect only
to the authenticated supervisor socket and never to another child runtime.

Runtime IPC v3 is the external child ABI during alpha. A host depends on the
public `liteyukibot.runtime` client/protocol surface plus frozen Event and
Action models. It receives kernel Events only after declaring
`runtime.events.receive`, and it submits Actions only after declaring
`runtime.actions.send`. No new protocol version is required for this decision.

`runtime_event_routes` configures core-to-child Event forwarding. Each route
has one target, explicit distinct source runtime IDs, and an optional
`messages_only` filter. Sources and targets must be enabled configured
runtimes. The kernel concurrently delivers a matching Event to all route
targets and records a rejected delivery as an EventBus handler failure.

Runtime packages may declare a default message-only route in their discovered
runtime metadata. The v6 package uses this for its historical route when no
explicit route targets it. This is compatibility behavior, not a general
framework privilege.

An external host starts as `kind = "custom"` with an explicit command. Its
bridge owns conversion between the external framework and the portable models.
The kernel does not import AstrBot, MoFox, their plugins, or their adapters.

## Consequences

An Action produced by an AstrBot or MoFox child may target a bot owned by a
NoneBot child, but it travels through the kernel's validation and action route.
The child cannot synchronously target itself, preventing a protocol loop.

Framework-specific streaming, editing, typing, session mutation, and plugin
management are outside this contract. They need a concrete portable Action or
capability before they are exposed. Generic RPC, pickled objects, raw framework
events, and direct child sockets are not part of runtime IPC.
