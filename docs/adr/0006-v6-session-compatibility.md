# ADR 0006: Define The v6 Session Compatibility Contract

- Status: Accepted
- Date: 2026-08-09

## Context

LiteyukiBot v6 message plugins commonly import `MessageEvent`, `Rule`, matcher
decorators, and session identity models. The initial v7 compatibility runtime
supported plugin loading and lifecycle only, so those imports failed before an
ordinary message plugin could register.

The final v6 implementation also depended on Channel/shared-memory objects,
contained inconsistent Session scope typing, and referenced `on_startswith`
without implementing it. Restoring those defects would violate the v7 process
boundary and would not provide a deterministic compatibility contract.

## Decision

The `liteyuki.session` compatibility namespace supports these process-local
surfaces:

- `MessageEvent` with the v6 constructor fields and public attributes;
- synchronous `MessageEvent.reply()` with string or mapping payloads;
- `Rule`, including sync or async predicates and short-circuit `&`, `|`, and
  inversion;
- `Matcher.handle()` with sync or async handlers;
- `on_message`, `on_keywords`, `on_startswith`, `on_endswith`, and
  `on_fullmatch`;
- `SceneType`, `User`, `Scene`, `Role`, `Member`, and `Session`;
- `BaseSeg`, `Text`, and `Image` message-segment imports.

Matcher registration is process-local and stable. Larger numeric priorities run
first, preserving v6 ordering. Registration order is preserved within one
priority. A matching `block=True` matcher allows remaining matchers at the same
priority to run, then prevents lower priorities. An unmatched blocking matcher
does not stop dispatch.

Handler exceptions are logged through Yukilog and isolated from later handlers.
Dispatch reports matched matcher count, called handler count, block state, and
failure strings for the compatibility host; plugin handlers may ignore that
internal result as they did in v6.

`MessageEvent.reply()` records ordered reply intents on the event. It performs no
I/O. The compatibility host drains those intents only after matcher dispatch and
will translate them to protocol-neutral Actions in a separately versioned
runtime contract.

Session scope uses `SceneType`, and `session_id`/`target_id` use stable numeric
scope identifiers. `on_startswith` is implemented because shipped v6 plugin
source imports it even though the final v6 registration module omitted it.

## Unsupported

`receive_channel`, Channel, shared memory, cross-process Python objects, dynamic
matcher removal, hot reload, NoneBot dependency injection, and adapter object
emulation are outside this contract. Passing a receive channel is an explicit
`LegacyUnsupportedError`; it never becomes an inert value.

## Consequences

V6 message plugins can import and register without a runtime transport. Pure
unit dispatch is deterministic and produces ordered reply intents.

This contract alone does not make the v6 runtime advertise
`runtime.events.receive`. Protocol v2 carries core-originated events but does not
allow child-originated Actions, so reply delivery requires another negotiated
protocol version before end-to-end runtime integration.
