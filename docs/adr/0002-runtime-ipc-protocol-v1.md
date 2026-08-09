# ADR 0002: Freeze The Local Runtime IPC Protocol At Version 1

- Status: Accepted
- Date: 2026-08-09

## Context

NoneBot, v6 compatibility, and custom adapters run as supervised child
processes. Their control plane needs a small, bounded local protocol with clear
authentication and failure behavior.

## Decision

The runtime protocol is loopback TCP only. A supervisor generates one random
token per runtime launch and validates it during the handshake. Each frame is a
four-byte unsigned big-endian length followed by UTF-8 JSON. Empty frames and
frames larger than 8 MiB are invalid.

All v1 messages are frozen Pydantic models with `type` as a discriminator,
`protocol = 1` where applicable, and unknown fields forbidden.

| Type | Direction | Required v1 fields |
| --- | --- | --- |
| `hello` | child -> core | `protocol`, `runtime_id`, `kind`, `token` |
| `welcome` | core -> child | `protocol`, `heartbeat_interval` |
| `config` | core -> child | JSON-safe `options` |
| `ready` | child -> core | optional `capabilities` |
| `heartbeat` | child -> core | `monotonic` |
| `event` | child -> core | `correlation_id`, JSON-safe `payload` |
| `event_accepted` | core -> child | `correlation_id`, `accepted|overloaded|invalid` status, optional detail |
| `action` | core -> child | `correlation_id`, JSON-safe `payload` |
| `action_result` | child -> core | `correlation_id`, `ok`, optional data or error |
| `shutdown` | core -> child | optional `reason` |
| `error` | either direction | `code`, `message`, optional `correlation_id` |

The child sends `hello` first. The core replies with `welcome` and `config`; the
child then sends `ready` and periodic `heartbeat` messages. Event and action
correlation identifiers are opaque strings supplied by the requester.

Malformed JSON, invalid message shapes, invalid frame sizes, and truncated
frames are protocol failures. Authentication or duplicate-connection failures
close the offending connection without replacing a healthy runtime connection.

## Consequences

Child runtimes must treat protocol validation errors as fatal to the current
connection. The supervisor owns reconnect, timeout, restart, and terminal
failure policy; children do not retry by creating competing connections.

No field or message-type additions are silently compatible with v1 because
wire models reject extras. Such a change requires protocol version negotiation
and a new `hello`/`welcome` version, or a separately negotiated capability.
