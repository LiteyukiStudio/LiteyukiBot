# Changelog

## Unreleased

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
