# LiteyukiBot v7 Profile

`liteyukibot-v7-profile` stores persistent per-bot user preferences and
provides `liteyukibot.profile@1` to native plugins.

Records are keyed by exact `(runtime_id, bot_id, actor_id)` principals. The
initial fields are `nickname` and `language`; storage lives entirely in this
plugin's private SQLite database.

## Development

Keep persistence private to this package and key records by the full principal
tuple. Run `uv run pytest packages/profile/tests` and
`uv run python -m scripts.run_profile_install` after changes.
