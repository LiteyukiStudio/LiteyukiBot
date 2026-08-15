# v7 Alpha Delivery History

- Status: Archived
- Archived: 2026-08-10

This record preserves completed alpha delivery phases that no longer belong in
the current architecture overview. It is historical context only; use the
current architecture, specifications, release guide, and changelog for active decisions.

## Phases 1-3: Kernel And Compatibility

`7.0.0a1` established the Python 3.14 kernel, non-root Docker build, and
version/tag/wheel release integrity. Kernel stabilization then added the
runtime failure matrix, early v1 contract records, three-platform verification, isolated PyPI
installation checks, and an informational performance reference.

`7.0.0a2` completed the first bounded compatibility phase: reusable child
transport, negotiated bidirectional Events and Actions, the v6 message matcher
bridge, structured NoneBot OneBot/Satori adapter contracts, and the
plugin/runtime developer kit.

## Phases 4-5: First-Party Plugin Foundation

`7.0.0a3` introduced separately distributed permissions, commands, and
essentials plugins. The status service, policy, command routing, and help
rendering stayed outside the kernel. The first package release order was root,
permissions, commands, then essentials.

The following plugin contract release advanced permissions, commands, and
essentials to `0.2.0a1`. Early contract records captured exact capabilities,
structured schemas, hierarchical routing, and Essentials-owned help rendering;
runtime IPC remained at v3.

## Phase 6: Optional Business Plugins

`liteyukibot-v7-resources==0.1.0a1` added declarative resource registration,
command generation, exact-principal targeting, and per-operation capability
checks without introducing kernel storage or migrations.

`liteyukibot-v7-profile==0.1.0a1` became the reference provider, owning a
private SQLite database keyed by `(runtime_id, bot_id, actor_id)` and exposing
nickname and language fields. Essentials advanced to `0.2.0a2` for optional
profile language integration. The release chain became root, permissions,
commands, resources, profile, then essentials.
