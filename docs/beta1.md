# LiteyukiBot v7 Beta1 Contract

Beta1 will publish `liteyukibot-v7==7.0.0b1`. It is a single-host,
protocol-neutral integration release: the kernel owns configuration, routing,
permissions, deployment state, and IPC; platform/framework integrations run in
supervised child processes and never exchange SDK objects with one another.

This document is the release-facing contract. The implementation checklist,
open decisions, PR rules, and release gates live in `tmp/beta1-roadmap.md`.

## Installation

After the Beta1 wheels are published, install a minimal local workspace with:

```bash
uv tool install --python 3.14 "liteyukibot-v7==7.0.0b1"
liteyuki init
liteyuki check
```

Install optional runtime distributions in the same isolated tool environment
at install time. For the supported native OneBot v11 path, use the versions
listed in the release notes:

```bash
uv tool install --python 3.14 --force \
  --with "liteyukibot-v7-runtime-adapter==RELEASE_VERSION" \
  --with "liteyukibot-v7-adapter-onebot==RELEASE_VERSION" \
  "liteyukibot-v7==7.0.0b1"
```

`RELEASE_VERSION` is intentionally a placeholder: each separately distributed
runtime and adapter has its own version. Do not substitute an arbitrary latest
version. The release notes name the tested root/runtime/adapter set. Project
maintainers may instead add the same requirements to their project with `uv
add`, then invoke `uv run liteyuki ...`.

The repository CI already builds the root wheel, installs it via an isolated
`uv tool` directory, and runs `version`, non-interactive `init`, and `check` on
Windows, macOS, and Linux. The public PyPI smoke for Beta1 repeats that flow
against the released wheels.

## Compatibility Tiers

| Tier | Components | Beta1 commitment |
| --- | --- | --- |
| Supported | Native adapter host, OneBot v11 adapter, native plugins, v6 compatibility, native agent | Documented configuration plus automated end-to-end regression coverage. OneBot v11 is the only supported native platform protocol. |
| Supported bridge | NoneBot, AstrBot, MoFox | Kernel-supervised child bridge with locked upstream dependency, lifecycle, event/action, and managed-projection evidence. LiteyukiBot does not reimplement each framework's ecosystem. |
| Experimental | OneBot v12, Satori, future native adapters | Separately versioned and independently tested. Their availability or absence does not alter the supported OneBot v11 path. |

The current native OneBot v11 adapter owns an HTTP Post callback listener and
HTTP API client. It accepts private and group messages, maps text, mentions,
replies, and media into frozen envelopes, and returns `SendMessage` or guarded
`CallApi` actions through the source runtime. Malformed callbacks, path and
content-type failures, and API failures have stable error behavior; listener
restart clears stale reply routes before accepting the next generation.

The native agent is OpenAI-compatible but is not an unrestricted automation
runtime. The kernel exposes only source-principal-authorized business-tool
schemas and rechecks that capability at invocation. Agent events are bounded by
model/event timeouts, tool rounds, concurrency, and conversation history. The
SQLite store retains at most `history_limit` messages for each exact
`(runtime_id, bot_id, conversation_id)` tuple on subsequent writes.

## Runtime And Delivery Semantics

Runtime IPC uses authenticated framed JSON over loopback. An event is accepted
by the kernel, routed to configured children, and can result in a
protocol-neutral action back to the source runtime. The kernel verifies the
runtime, bot, and active event-delivery provenance before it executes a
child-originated action.

Delivery is bounded best effort, not exactly-once or durable cross-host
messaging. A failed/overloaded child, source action failure, timeout, or restart
is exposed as a terminal diagnostic. Runtime generation activation first checks
the staged immutable load plan in an isolated Python environment; a failed
health probe leaves the prior active/rollback pointers intact.

## Security Boundary

- Runtime secrets reside in the encrypted workspace vault and are injected only
  into the environment variable declared by the enabled runtime; secrets do not
  travel through IPC or diagnostic output.
- Capability grants are exact `(runtime_id, bot_id, actor_id)` decisions and
  fail closed for an unknown principal. Agent tool visibility and execution use
  the same decision path.
- `CallApi` has one guarded kernel action boundary. Direct child calls without
  an accepted source event are rejected.
- Native plugins are trusted in-process code. Third-party framework and
  platform SDK state remains inside its child runtime; this is an integration
  boundary, not a sandbox for malicious plugins.

## Upgrade And Recovery

`config_version = 1` remains the Beta1 configuration schema. Configurations
with an older or missing version block startup after LiteyukiBot writes a backup
and a current upgrade template below `.liteyuki/`; newer configurations are
rejected without modification. Review the template, merge it manually, then
run `liteyuki config upgrade --refresh` only to regenerate recovery material.

Managed profiles and runtime generations retain a verified previous pointer.
Use `liteyuki profile rollback` to restore the preceding profile. Package-owned
state is never copied or migrated automatically; a package must provide an
explicit compatible migration/backup path before that behavior becomes part of
the Beta1 release contract.

## Known Limits

- There are no runtime-to-runtime sockets, distributed clustering, durable
  delivery, or WebUI implementation in Beta1.
- OneBot v12 and Satori are not substitutes for the supported OneBot v11 path.
- Agent routes cannot install packages, edit configuration, execute arbitrary
  shell commands, or use unrestricted filesystem tools.
- Agent history has a bounded retention policy. A user-facing, capability-gated
  clear-history control is not part of Beta1 until its authorization and audit
  contract is released.

## Release Evidence

A Beta1 tag is created only after the release commit is merged, the full
three-platform CI and Docker checks pass, all required trusted publishers are
configured, each package wheel is installed in isolation, and the public
released-wheel smoke passes. Package tags are immutable and published in
dependency order; see [the release procedure](development/releasing.md).
