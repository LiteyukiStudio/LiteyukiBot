# Configuration Schema 7

Alpha15 accepts only `config_version = 7`. The loader rejects the removed
Broker, daemon, HTTP, WebUI, runtime, agent, development, and vault sections.
Generate a new file with:

```bash
liteyuki --workspace my-bot init --locale en-US
liteyuki --workspace my-bot check
```

The template contains these sections:

```toml
config_version = 7

[core]
data_dir = "data"
cache_dir = "cache"
queue_capacity = 1024
enqueue_timeout_seconds = 1.0
handler_timeout_seconds = 30.0
max_concurrent_events = 100

[logging]
level = "INFO"
console = true
json_lines = false
payload_mode = "metadata"

[i18n]
locale = "auto"

[cordis]
enabled = []
config = {}

[permissions]
grants = []
roles = {}

[commands]
prefixes = ["/"]

[resources]

[profile]

[essentials]
language = "zh-CN"

[onebot.v11.accounts]
```

Built-in permissions, commands, resources, profile, and essentials are
application-owned features and are not enabled by installing separate
packages. Their settings are configured in the corresponding sections.

## OneBot v11

Install the Alpha15 adapter with the root application, then add one or more
accounts. An account selects the SnowLuma implementation explicitly:

```toml
[onebot.v11.accounts.qq-main]
implementation = "snowluma"
self_id = "123456"
ws_url = "ws://127.0.0.1:3001/"
access_token = "onebot-token"
```

Loopback `ws://` endpoints are accepted for local development. Remote
endpoints must use `wss://`. Tokens are sent as Bearer authorization headers.
The adapter publishes only supported private/group message events and
source-bound `message.send` actions.

## Security And Precedence

Keep credentials out of committed configuration and public bug reports. Use
the loader's documented environment and CLI override mechanisms for deployment
secrets. Configuration is validated before application startup; malformed or
removed sections fail `check` with a precise issue rather than being ignored.

The generated template and `src/liteyukibot/config/models.py` are the source
of truth for field names and defaults. Update this page and the focused config
tests together when schema 7 changes.
