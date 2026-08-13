# ADR 0001: Freeze Event And Action Contracts At Schema Version 1

- Status: Accepted
- Date: 2026-08-09

## Context

Native plugins and child runtimes need a portable event and action surface. The
surface must preserve adapter-specific data without allowing mutable or
non-serializable values to cross an ownership boundary.

## Decision

`liteyukibot.events` defines the v1 public data contract. Every model is frozen,
forbids unknown fields, rejects NaN and infinity, and accepts JSON-safe payloads
only. Serialization uses Pydantic JSON mode.

`EventEnvelope` has schema version `1` and these required fields:

| Field | Meaning |
| --- | --- |
| `id` | Globally unique event identifier. |
| `timestamp`, `received_at` | Timezone-aware source and core receipt times. |
| `runtime_id`, `adapter`, `bot_id` | Origin identity. |
| `type` | Adapter-neutral event type. |
| `conversation` | `ConversationRef`; used with runtime and bot for ordering. |

`actor`, `message`, `reply_token`, and `raw` are optional. Messages are tuples
of normalized `Segment` values. The initial segment kinds are `text`, `media`,
`mention`, `reply`, and `adapter`; text segments require `data.text` to be a
string. `raw` and segment data retain adapter-specific JSON-safe values.

The current pre-stable v1 actions are discriminated by `action.type`:

| Action | Required payload |
| --- | --- |
| `send_message` | `message` plus `conversation` or `reply_token`. |
| `edit_message` | `message_id` plus replacement `message`; the adapter may require `conversation`. |
| `call_api` | Non-empty `api` and JSON-safe `params`. |

`ActionEnvelope` carries `schema_version`, `action_id`, optional `event_id`,
`runtime_id`, `bot_id`, and one action. `ActionResult` correlates by `action_id`.
A successful result cannot contain error fields; a failed result requires
`error_code` and may include `error_message` and JSON-safe `data`.

`EventBus` is part of the contract rather than an implementation detail:

- FIFO order is preserved per `(runtime_id, bot_id, conversation.ordering_key)`.
- Different ordering keys may run concurrently, subject to configured capacity.
- Handlers return `HandlerResult` or `None`; returned actions execute in handler
  order, and `stop_propagation` stops later handlers for that event.
- Handler timeouts, exceptions, and invalid return values become
  `HandlerFailure` entries. Queue saturation and closure return an explicit
  `DispatchResult` status.

## Consequences

Plugins may depend on the fields and outcomes above for v1. They must not depend
on adapter-private object identity or mutate received mappings.

Because v1 models reject unknown fields, additions to an existing envelope,
action, result, or segment shape must update models, tests, and this record.
ADR 0011 permits these breaking pre-stable changes directly; stable v7 will
require a new schema version or explicitly versioned parallel type.
