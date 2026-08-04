# Changelog

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
- Python 3.14, uv, PyPI packaging, and a non-root GHCR Docker image.

The PyPI distribution is named `liteyukibot-v7`; the import namespaces remain
`liteyukibot` and `liteyuki`.

This is an integration pre-release. Public contracts, compatibility coverage, and
operational behavior remain subject to the Phase 2 stabilization work described
in `docs/architecture/v7.md`.
