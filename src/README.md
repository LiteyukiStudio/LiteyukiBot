# Root Composition Source

`src/liteyukibot/` is the branded `liteyukibot-v7` application and CLI. It
owns configuration schema 7, workspace initialization, application lifecycle,
logging, resource packs, and the built-in Cordis feature catalog. The root
application depends directly on the independent `liteyukibot-v7-kernel`
package and does not duplicate its contracts.

The built-in feature modules under `liteyukibot/features/` provide permissions,
commands, resources, profile, and essentials in one application-owned path.
The OneBot v11 adapter remains in `packages/adapter-onebot`; framework SDKs and
transport objects do not belong in this tree.

Use the root checks after changing this directory:

```bash
uv run liteyuki check
uv run ruff check src tests
uv run mypy
uv run pytest tests
```

Public configuration, event, action, service, or plugin changes require a
focused test and an update to the owning document under `docs/`.
