# Core Event And Action v1

- Specification version: `1`
- Applies to: current v7 pre-release Event and Action models
- Compatibility: pre-stable; exact model changes require matching runtime and
  plugin updates before the first stable v7 release

## Contract

The kernel owns portable, JSON-safe Event and Action models. Framework SDK
objects, transport clients, secrets, and arbitrary Python objects never enter
these models or cross a runtime boundary. Adapters normalize platform input to
an immutable Event; plugins and runtimes consume that portable value.

An Event has a stable ID, runtime and bot provenance, time, typed segments,
and optional actor/channel context. An Action describes a requested external
effect and is routed only to its owning runtime. Event handling and Action
execution are independent asynchronous outcomes; an Action result is not a
replacement for Event completion.

The current EventBus applies bounded queueing and handler concurrency from
`core` settings. Overload, timeout, and handler failure are explicit
outcomes. Producers must not create an unbounded queue or bypass the kernel to
deliver directly to another runtime.

## Evidence

The owning models and tests are `src/liteyukibot/events/` and
`tests/test_events_v7.py`. Cross-process behavior is specified by
[Runtime IPC v6](runtime-ipc-v6.md), not this document.
