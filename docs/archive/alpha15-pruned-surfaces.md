# Alpha15 Pruned Surfaces

**Status:** historical summary
**Date:** 2026-08-28
**Applies to:** LiteyukiBot v7.0.0a15

Alpha15 deliberately reduced the supported product to four lockstep
distributions: the root application, kernel, Cordis host, and OneBot v11
adapter. Broker, daemon, generic runtime bridges, WebUI, Satori, NoneBot,
Agent, LYF runtime integration, native IPC, and the related configuration
sections are outside this release boundary.

The former active notes and launchers for those surfaces were removed because
they referenced retired packages, CLI flags, or workflows. The old benchmark
page and schema-1 reference were also removed because their runner and current
performance contract no longer exist. These are historical decisions, not
supported installation or development paths.

Use the current architecture, configuration, release, and package documents
as the source of truth:

- `docs/architecture/v7.md`
- `docs/configuration.md`
- `docs/development/releasing.md`
- `packages/*/README.md`
