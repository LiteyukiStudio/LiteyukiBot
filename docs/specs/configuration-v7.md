# Configuration v7

**Status:** Alpha15 active contract.

Configuration v7 is the TOML document loaded by `liteyukibot.config`. It
requires `config_version = 7` and contains `core`, `logging`, `i18n`, `cordis`,
`permissions`, `commands`, `resources`, `profile`, `essentials`, and `onebot`
sections. Built-in features are application-owned and do not require separate
distribution metadata.

The loader rejects the removed `broker`, `daemon`, `http`, `lyip`, `runtime`,
`runtimes`, `webui`, `agent`, `development`, and `vault` sections. Unknown or
malformed values fail validation before application startup. OneBot v11
accounts are configured under `[onebot.v11.accounts.<id>]` and use the
`implementation = "snowluma"` transport.

The implementation and generated template are the field/default authority:
`src/liteyukibot/config/models.py` and `src/liteyukibot/config/template.py`.
