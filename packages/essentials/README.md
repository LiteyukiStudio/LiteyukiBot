# LiteyukiBot v7 Essentials

`liteyukibot-v7-essentials` provides the first-party `help` and `status`
commands for native LiteyukiBot v7 deployments.

The plugin adds no service. It consumes `liteyukibot.commands@2` and the
kernel's `liteyukibot.kernel.status@1` snapshot service. Help only lists
commands visible to the current actor; status requires the
`liteyukibot.status.read` capability.

Alpha 3 also exposes bounded `help` and `status` Tools; their schemas reject
extra fields and status remains capability-protected.

```toml
[plugins]
enabled = [
  "liteyukibot.permissions",
  "liteyukibot.commands",
  "liteyukibot.essentials",
]

[plugins.config."liteyukibot.essentials"]
language = "zh-CN"
```

Supported languages are `zh-CN` (the default) and `en`.

## Development

Essentials is a command-service consumer and does not add kernel behavior.
Keep visible text in its resource catalogs. Run
`uv run pytest packages/essentials/tests` and
`uv run python -m scripts.run_essentials_install` after changes.
