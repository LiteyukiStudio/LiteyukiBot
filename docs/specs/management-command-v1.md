# Management And Command v1

- Specification version: `1`
- Applies to: kernel management registry and first-party structured commands
- Compatibility: pre-stable; command names and schemas remain subject to the
documented Beta CLI migration plan

## Management

Management commands are registered by canonical token paths with an owner,
required capability, summary, and danger class. Callers have an identity and
capabilities; authorization fails closed. The registry resolves only registered
commands and does not provide shell execution, arbitrary RPC dispatch, or
unbounded plugin callbacks.

The kernel worker owns the durable operation ledger used by authenticated CLI
and WebUI control surfaces. An operation has a canonical command-derived name,
capability, idempotency key, target, and state. Execution is FIFO per worker;
cancel is permitted only before execution for definitions that explicitly opt
in. A worker restart changes queued or running records to `unknown`; it never
replays a possibly non-idempotent operation.

The SQLite ledger stores HMAC-pseudonymized principal and target identifiers,
an input digest, state transitions, and result codes. It does not store raw
arguments, raw input JSON, session subjects, or command output. Audit keys are
instance-local 32-byte files. Records retain for 30 days or 100,000 rows,
whichever limit removes older records first.

The local terminal is the current administrator caller. Runtime-originated
management requests are allowed only through the v5 IPC capability gate and
only for a registered command. Results are structured and redacted.

## Structured Commands

First-party command routing uses explicit schemas and hierarchical canonical
paths. Usage and help rendering belong to the owning command surface. Handler
annotations are not an implicit argument schema, and conversion failures expose
stable user-facing diagnostics rather than internal tracebacks.

## Evidence

The owning implementation is `src/liteyukibot/management.py`,
`src/liteyukibot/operations.py`, plus the Commands package. Run
`uv run pytest tests/test_management.py tests/test_operations.py
packages/commands/tests`.
