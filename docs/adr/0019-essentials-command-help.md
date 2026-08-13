# ADR 0019: Keep Help and Usage Rendering in Essentials

- Status: Accepted
- Date: 2026-08-10

## Decision

`liteyukibot-v7-essentials` consumes the commands service's visible registrations
and optional `resolve(event, path)` lookup. The root help command lists only
visible root commands. `/help <path>` resolves a canonical path or final
segment alias and renders that command's canonical path, aliases, summary,
usage, argument schema, and option schema.

Invisible commands are treated as not found, so help does not reveal their
existence. The status command continues to require the exact
`liteyukibot.status.read` capability.

Essentials owns the localized plain-text output. A `CommandParseError` from the
help schema becomes a short language-specific usage error; converter exception
messages and internal tracebacks never reach the user. Commands remains
language-neutral and does not choose a formatter or localization system.

## Consequences

The default operational UI demonstrates the structured command contract without
adding a shared i18n dependency or coupling the kernel to presentation. Other
plugins can replace essentials or render the same schemas differently.
