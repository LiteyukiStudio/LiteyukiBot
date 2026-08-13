# ADR 0009: Define The NoneBot Adapter Boundary

- Status: Accepted
- Date: 2026-08-09

## Context

The NoneBot child host already loads adapters and observes events, but its
generic bridge flattened messages to plain text and used adapter session IDs as
conversation keys. That loses media and mention semantics, and OneBot group
session IDs include the actor, which incorrectly splits EventBus ordering for
one group across users.

ADR 0008 now sends structured v6 replies back as schema-v1 `SendMessage`
Actions. The NoneBot boundary must translate those portable Actions into real
adapter Messages while keeping NoneBot and all adapter packages optional.

## Decision

The separately published `liteyukibot-v7-runtime-nonebot` child owns
adapter-specific translation. The core continues to see
only the frozen schema-v1 `EventEnvelope`, `Message`, `Segment`, and Action
models. Adapter modules are loaded lazily inside the child and are never
imported by core modules.

The first explicit contracts are the versions selected by the locked optional
dependencies: OneBot v11 and v12 from `nonebot-adapter-onebot` 2.4.x, and
Satori from `nonebot-adapter-satori` 1.3.x. Their stable envelope adapter IDs
are `onebot-v11`, `onebot-v12`, and `satori`; NoneBot display names are not wire
identifiers.

Source event names remain in `EventEnvelope.type`. No common notice/request
taxonomy is claimed in this version. Adapter Pydantic JSON output is retained
in `raw`, and source timestamps become aware UTC values. The child uses the
adapter bot registration ID unchanged so Actions can resolve through
`nonebot.get_bot()`.

Conversation routing is defined independently of adapter composite session
IDs:

| Source context | Conversation |
| --- | --- |
| OneBot private | user ID / `private` |
| OneBot group | group ID / `group` |
| OneBot v12 channel | channel ID / `channel`, parent guild ID |
| Satori direct channel | channel ID / `private` |
| Satori public channel | channel ID / `channel`, parent channel or guild ID |

Other contextual events use a group, private, or synthetic bot conversation
only when the source data supports it. Actor display names prefer contextual
member or group names. Only message-bearing events receive an opaque reply
token and enter the bounded reply cache.

Message normalization reads `original_message` when available because adapter
preprocessing may remove a quote, bot mention, or nickname from the matcher
message. Segment mappings are:

| Portable type | Meaning |
| --- | --- |
| `text` | `text`, plus JSON-safe Satori style ranges |
| `mention` | `user_id`, `role_id`, or `scope = all|here` |
| `reply` | `message_id`, with optional normalized children |
| `media` | `media_type`, portable URL when available, and required native fields |
| `adapter` | stable adapter ID, native type/data, and optional children |

Unknown native segments use `adapter` rather than being stringified or
discarded. Outbound adapter segments must target the selected adapter. The
adapter-less `{type, data}` form created by the v6 compatibility bridge remains
valid as a same-target legacy escape hatch. Malformed segments and media that
cannot be represented by the target adapter fail deterministically.

A reply-token `SendMessage` resolves the exact cached bot/event and calls
`Bot.send(event, native_message)`. An invalid token or bot/adapter mismatch
does not fall back to conversation routing. A visual quote is represented only
by an explicit `reply` segment.

Proactive routing supports only unambiguous schema-v1 conversations:

- OneBot v11 private/group calls `send_private_msg` or `send_group_msg`;
- OneBot v12 private/group/channel calls its unified `send_message` API;
- Satori private/channel treats the conversation ID as a channel ID and calls
  `Bot.send_message`.

Creating a Satori direct channel from a user ID, unsupported conversation
types, uploads that require bytes or paths, and other adapter-only operations
remain explicit `CallApi` workflows or require a future versioned Action.
`CallApi` names and JSON parameters pass through without a Liteyuki allowlist.

Action results recursively convert Pydantic models, datetimes, enums, mappings,
and sequences into strict JSON. Non-string object keys, arbitrary objects, NaN,
and infinity are rejected instead of being hidden by `str()` conversion.

## Consequences

OneBot and Satori message events can traverse the portable EventBus and v6
compatibility bridge and return structured native replies without sharing
adapter objects across processes. Group FIFO identity is stable across actors,
and unknown adapter segments remain available through an explicit escape hatch.

The default kernel dependency set is unchanged. Adapter contract tests run in
a dedicated CI job that installs the runtime package with its OneBot and Satori
extras; the normal three-platform quality matrix continues to prove the minimal
kernel installation.

Native adapter deployments and NoneBot deployments are both supported, but one
account has exactly one ingress owner. The AstrBot and MoFox headless bridges
consume portable events and emit portable actions; they do not activate an
upstream platform adapter for the same account.

This record does not promise a portable notice/request taxonomy, arbitrary
cross-adapter media conversion, automatic file upload, user-ID-based Satori
direct-message creation, or support for every future adapter version.
