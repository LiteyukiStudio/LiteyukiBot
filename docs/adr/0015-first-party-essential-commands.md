# ADR 0015: Keep Essential Commands in a Consumer Plugin

- Status: Accepted
- Date: 2026-08-10

## Context

An operable default deployment needs command discovery and a protected status
view. Neither behavior belongs in the protocol-neutral kernel: presentation,
language, access policy, and command names are application concerns.

Introducing a general localization framework for two small responses would add
an unproven contract and dependency surface. Returning adapter-specific rich
content would also make the default commands unavailable to other runtimes.

## Decision

`liteyukibot-v7-essentials` is a separately distributable native plugin. It
requires `liteyukibot.commands@1` and `liteyukibot.kernel.status@1`, provides no
service, and registers two commands as one atomic batch:

- `help`, alias `帮助`, permission `public`;
- `status`, alias `状态`, permission `operator`.

Help calls `CommandService.visible(event)` and renders only commands allowed for
the current actor, sorted by canonical name. It uses the prefix that matched the
current invocation, so configured multi-character prefixes remain truthful.
Status renders the immutable kernel snapshot with plugin and runtime IDs sorted.
Both commands return correlated protocol-neutral plain-text `SendMessage`
actions.

The plugin accepts only `language = "zh-CN" | "en"`, defaulting to `zh-CN`.
Its small built-in dictionary owns only essentials text. Third-party summaries
are preserved, and no kernel localization or resource-loader contract is
introduced. Invalid configuration fails during setup. The plugin unregisters
both command handles during stop.

## Consequences

The default operational UI is replaceable and can be disabled without changing
the kernel. Non-operators neither see nor receive a response from status. The
package depends transitively on the permission plugin through commands, while
its plugin manifest declares only the services it consumes directly.

Additional built-in commands, rich rendering, or a shared localization system
require separate evidence and design. They are not implied by this package's
name.
