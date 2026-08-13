# Changelog

## 7.0.0b2 - 2026-08-13

- added `EditMessage` to the portable action model and the separately
  published native OneBot v11/v12 and Satori adapter packages;
- added named instance configuration, daemon-managed workers, local development
  controls, and data-directory instance locking;
- added the interactive management console and responsive initialization flow;
- upgraded performance artifacts to schema 2 with three independent samples
  and deterministic benchmark coverage;
- require `liteyukibot-v7>=7.0.0b2` for the Satori adapter so published wheels
  always import the portable `EditMessage` action.

## 7.0.0b1 - 2026-08-12

- introduced runtime IPC protocol v5 with a kernel-originated, capability-gated
  control request for source-scoped native Agent history deletion;
- added the `liteyukibot.agent.history.clear` capability and `/agent forget`
  command, with redacted permission auditing and no model invocation;
- made `liteyukibot-v7-agent` depend on the separately published command
  package so its installed plugin contract is complete.
- fixed the AstrBot child import root so managed projected plugins are loaded,
  and added locked-upstream plugin-reply regressions for the AstrBot and MoFox
  bridge runtimes.
- made the locked Neo-MoFox upstream an explicit installation prerequisite,
  because PyPI rejects direct VCS dependencies in published wheel metadata.
- made the MoFox release verifier install that fixed upstream requirement before
  exercising the published runtime wheel.
- added `liteyukibot-v7-runtime-adapter`, a separately published Python
  platform-adapter host with managed-generation and entry-point boundaries;
- added `liteyukibot-v7-adapter-onebot`, a pure-Python OneBot v11 HTTP Post
  and HTTP API adapter with callback identity and token validation;
- marked `liteyukibot-v7-runtime-adapter` as typed for strict downstream
  adapter contracts.
- extended resource-pack metadata with localized presentation keys and optional
  validated local PNG icons for a future WebUI, without adding a WebUI route;
- added the kernel-owned `liteyukibot.i18n@1` service backed by layered resource
  packs, including per-user locale rendering for essential commands;
- moved first-party profile/resource command text and custom-init package labels
  into package-owned language resources, with workspace resources retaining the
  final overlay position.

## 7.0.0a9 - 2026-08-11

- introduced runtime IPC protocol v4 with immutable delivery tracing and an
  optional, capability-gated terminal event outcome;
- updated the agent, AstrBot, MoFox, and v6 child hosts to report completed or
  failed asynchronous event deliveries.
- added redacted runtime health snapshots and `liteyuki inspect topology` for
  protocol, capability, liveness, IPC pressure, and configured route diagnosis.

## 7.0.0a8 - 2026-08-11

- added verified, workspace-owned uv profiles with atomic activation, rollback,
  and a machine-readable lock record;
- made `run` and `check` use the selected profile interpreter.

## 7.0.0a7 - 2026-08-11

- cached v6 function source for each read-only dispatcher lifetime, reducing
  repeated resource reads without introducing a resource-pack hot-reload path;
- moved v6 `nohup` tasks into the kernel's managed task lifecycle, so shutdown
  cancels them deterministically and Yukilog records background failures;
- added a configurable function benchmark alongside the kernel event benchmark.

## 7.0.0a6 - 2026-08-11

- added nested function invocation and explicit capability plumbing to the
  resource-function dispatcher;
- added `liteyukibot-v7-functions`, the separately published executor for the
  LiteyukiBot v6 `.lyf`, `.lyfunction`, and `.mcfunction` language;
- preserved v6 control flow while replacing the legacy Python `eval` and direct
  shell execution with safe literal parsing and caller-supplied capabilities.

## 7.0.0a5 - 2026-08-11

- added an installable v7 CLI workflow with `uv tool install liteyukibot-v7`;
- added explicit workspace selection, conventional `--version`, and
  `liteyukibot`/`ly` executable aliases;
- serialized workspace initialization and foreground runs so a competing
  instance cannot replace the active local control descriptor.

## 7.0.0a3 - 2026-08-10

The third v7 alpha establishes the first-party native plugin foundation:

- added the immutable `liteyukibot.kernel.status@1` service without changing
  runtime IPC protocol v3;
- added independently distributable permissions, commands, and essentials
  packages in one uv workspace with no new third-party runtime dependencies;
- added exact-principal `public`/`operator` policy, atomic protocol-neutral
  command routing, permission-filtered help, and operator-only kernel status;
- added Chinese and English plain-text essentials rendering while keeping
  localization outside the kernel;
- added real three-plugin topology tests, isolated wheel installation checks,
  multi-package release identity validation, and Trusted Publisher workflows.

The plugin packages begin at `0.1.0a1`. Their required publication order is
root, permissions, commands, then essentials.

## 7.0.0a2 - 2026-08-09

The second v7 alpha completes kernel stabilization and the first bounded
message-plugin compatibility phase:

- completed Phase 2 kernel stabilization with accepted v1 ADRs, deterministic
  runtime failure coverage, and cross-platform published-install verification;
- recorded informational alpha performance references on Linux, macOS, and Windows;
- made installed distribution metadata the runtime version source and added
  release tag/build verification;
- retained the non-root local Docker build while remote image publication is paused.
- centralized child-runtime handshake, heartbeat, serialized writes, and cleanup
  in a reusable versioned client shared by all built-in child hosts.
- added negotiated runtime protocol v2 with capability-gated core-to-child event
  delivery while retaining concurrent v1 child support.
- restored the process-local v6 session, rule, matcher, and reply-intent API
  needed by ordinary message plugins without restoring Channel semantics.
- added negotiated runtime protocol v3 with capability-gated child-originated
  Actions routed through the core's existing protocol-neutral Action service.
- connected the v6 message matcher runtime to EventBus delivery and translated
  ordered reply intents into correlated protocol-v3 SendMessage Actions.
- added structured OneBot v11/v12 and Satori event/message translation with
  exact reply routing, supported proactive sends, and strict JSON Action results.
- added dependency-free native-plugin and custom-runtime conformance harnesses,
  installable examples, and explicit lifecycle/single-reader authoring guidance.
- bounded pre-stable protocol numbering at v5 and made v3 the direct iteration
  target without an alpha backwards-compatibility guarantee.

This remains a rapid-iteration pre-release. Protocol v3 is the current direct
development target and may change without backwards-compatibility shims under
ADR 0011.

## 7.0.0a1 - 2026-08-04

The first v7 pre-release provides the kernel foundation for a protocol-neutral,
single-host chatbot runtime:

- immutable configuration with ordered includes and environment/CLI overrides;
- Yukilog 1.x integration with structured child-runtime logs;
- native plugin entry points, services, lifecycle hooks, managed tasks, and private storage;
- bounded event/action dispatch with per-conversation ordering and backpressure;
- authenticated framed IPC, runtime supervision, heartbeat, restart, and local control;
- isolated NoneBot2 hosting and an explicit LiteyukiBot v6 compatibility boundary;
- `liteyuki`/`ly` CLI, optional loopback HTTP status API, and cross-platform CI baselines;
- Python 3.14, uv, PyPI packaging, and a non-root local Docker image.

The PyPI distribution is named `liteyukibot-v7`; the import namespaces remain
`liteyukibot` and `liteyuki`.

This is an integration pre-release. Public contracts, compatibility coverage, and
operational behavior remain subject to the Phase 2 stabilization work described
in `docs/architecture/v7.md`.
