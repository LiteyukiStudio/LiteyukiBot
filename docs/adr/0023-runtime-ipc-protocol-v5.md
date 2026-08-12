# ADR 0023: Add Runtime IPC v5 Kernel Controls

- Status: Accepted
- Date: 2026-08-12

## Context

The native Agent owns its SQLite conversation state, while a user-facing
history deletion request must be authorized and audited by the kernel against
the source Event principal. Direct database access by a native plugin would
cross a child-runtime ownership boundary. Reusing child-originated Actions
would incorrectly model the direction and permit a control surface to resemble
a platform action.

The change affects the shared protocol, supervisor, native Agent host,
permission boundary, and user command. It therefore consumes the final
cross-cutting pre-stable protocol generation reserved by ADR 0011.

## Decision

Protocol v5 retains every v4 message and adds kernel-originated `control` and
child-originated `control_result` frames. A v5 child must declare
`runtime.controls.execute` before the supervisor sends a control request. The
supervisor correlates exactly one result, applies a bounded timeout, fails the
request on disconnect, and exposes only the pending-control count in runtime
health.

This generation intentionally defines one command only:
`agent.history.clear`. Its payload contains the exact source `runtime_id`,
`bot_id`, and conversation ordering key. The kernel selects exactly one native
Agent runtime, rechecks `liteyukibot.agent.history.clear` through the
permission service, and emits the existing redacted permission audit record.
The native Agent validates the complete payload shape and deletes only that
SQLite partition. It returns the removed row count; no event content, history,
or model input crosses the control frame.

The native Agent plugin registers `/agent forget` only when the optional
Commands, kernel Agent-history, and i18n services are present. The command
also carries the same capability, so ordinary command routing hides and stops
it for an unauthorized principal before the kernel performs its authoritative
second check.

V1 through v4 children remain supported where their existing capabilities
allow. They cannot receive v5 controls. Protocol v5 is not a generic RPC
mechanism: new control commands require an explicit reviewed wire contract,
kernel authorization path, child validation, documentation, and regression
coverage.

## Consequences

First-party runtimes using the shared client negotiate v5 after updating their
root dependency, without opting into controls. The native Agent declares the
control capability and publishes with `liteyukibot-v7>=7.0.0a17`.

This is the final pre-stable protocol generation. Subsequent non-redesign
protocol adjustments modify v5 directly under ADR 0011; another numbered
generation requires a documented large redesign decision before stable v7.
