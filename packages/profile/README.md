# LiteyukiBot v7 Profile

`liteyukibot-v7-profile` stores persistent per-bot user preferences and
provides `liteyukibot.profile@1` to native plugins.

Records are keyed by exact `(runtime_id, bot_id, actor_id)` principals. The
initial fields are `nickname` and `language`; storage lives entirely in this
plugin's private SQLite database.
