# ADR 0014: Route Native Commands Through a Plugin Service

- Status: Accepted
- Date: 2026-08-10

## Context

Native plugins can subscribe directly to normalized Events, but independent
string matching would duplicate prefix handling, access checks, collision
rules, and help metadata. Commands are still application behavior rather than
a kernel or runtime wire concern.

A full parser framework would add dependencies and prematurely fix option,
subcommand, and conversion semantics before first-party plugins demonstrate
those requirements.

## Decision

`liteyukibot-v7-commands` is a separately distributable workspace plugin. It
requires `liteyukibot.permissions@1`, provides `liteyukibot.commands@1`, and
subscribes to the EventBus at order `-100`.

Version 1 parses only a configurable non-empty prefix, a command name or alias,
and the remaining unparsed argument text. The default prefix is `/`; prefixes
are matched longest first. Names and aliases are whitespace-free, compared with
Unicode `casefold()`, and never include a prefix. Empty prefixes, mention-only
activation, typed arguments, options, and subcommands are unsupported.

Registrations carry an explicit owner, immutable metadata, and a handler that
returns the kernel's `HandlerResult`. Batch registration validates every name
and alias before changing the registry. Duplicate names or aliases fail the
whole batch. Registration handles must be explicitly removed by their owner.

Unknown input continues EventBus propagation. Recognized commands stop
propagation after an access denial, a successful handler, `None`, an invalid
result, or a caught handler exception. Denials produce no action. Handler and
permission failures are logged without returning internal exception text to the
user. EventBus cancellation and timeouts are not swallowed.

## Consequences

First-party and third-party native plugins share deterministic command routing
without expanding the kernel. Disabling the command plugin removes this layer
entirely, and compatibility runtimes retain their own matcher systems.

Consumers own registration cleanup just as they own direct EventBus
subscriptions. A future typed parser or mention trigger requires evidence and
a separate service-contract revision; it is not hidden behind the current raw
argument string.
