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
action_timeout_seconds = 30.0
shutdown_timeout_seconds = 10.0
max_concurrent_events = 100
max_event_bytes = 1048576

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

## Cordis Plugins

Alpha15 plugin management is local CLI functionality. It never exposes
installation, activation, or plugin configuration through OneBot or any
adapter command. The default metadata index is:

```text
https://raw.githubusercontent.com/LiteyukiStudio/liteyukibot-v7-plugins/main/index.json
```

The current interpreter is the install target, so run these commands from the
same `uv tool` environment that will run LiteyukiBot:

```powershell
# Run once from a verified Alpha15 release bundle directory.
$release = "C:\path\to\verified\release"
uv tool install --python 3.14 --force `
  --with "$release\liteyukibot_v7_kernel-7.0.0a15-py3-none-any.whl" `
  --with "$release\liteyukibot_v7_cordis-7.0.0a15-py3-none-any.whl" `
  --with "$release\liteyukibot_v7_adapter_onebot-7.0.0a15-py3-none-any.whl" `
  "$release\liteyukibot_v7-7.0.0a15-py3-none-any.whl"

liteyuki --workspace my-bot plugin list
liteyuki --workspace my-bot plugin show <bundle-id>
liteyuki --workspace my-bot plugin install <bundle-id>
liteyuki --workspace my-bot plugin config set <bundle-id> key=value
liteyuki --workspace my-bot plugin config show <bundle-id>
liteyuki --workspace my-bot plugin installed
liteyuki --workspace my-bot plugin disable <bundle-id>
liteyuki --workspace my-bot plugin enable <bundle-id>
liteyuki --workspace my-bot plugin remove <bundle-id>
```

`plugin install` downloads the selected Alpha15 Cordis wheel after checking
its declared size and SHA-256, then invokes `uv pip install --python` against
the running interpreter. Installation activates the bundle by default;
`--no-enable` leaves it installed but inactive. Activation state is written
to `[cordis].enabled` and local provenance is stored in
`.liteyuki/plugins.json`. If a disabled plugin has a
`[cordis.config.<entry-point>]` table, the CLI retains that table locally and
restores it when the plugin is enabled again. Edit plugin-owned configuration
in the workspace TOML; adapters do not provide a configuration channel.

The public index currently contains no Alpha15-compatible bundle. Existing
packages using the historical `liteyukibot.plugins` entry-point group are not
compatible with the current `liteyukibot.cordis_plugins` contract and must not
be installed through this command.

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
`handler_timeout_seconds` bounds one handler call, `action_timeout_seconds`
bounds one action guard or executor, and `shutdown_timeout_seconds` is the
overall application shutdown deadline shared by EventBus, Cordis cleanup,
profile workers and OneBot transport. Events still admitted when shutdown
reaches its deadline are completed as `closed`; lingering callback or transport
tasks remain observable in status until they finish.
Set `enqueue_timeout_seconds = 0` to reject immediately when the bounded event
queue is full instead of waiting for capacity.
`max_event_bytes` rejects an event before admission when its serialized JSON
payload exceeds the configured UTF-8 byte budget.
During cleanup, active features report `stopping`; if EventBus or Cordis cannot
finish before the deadline they report `cleanup_pending` until a later cleanup
attempt completes. They are reported as `stopped` only after their owned scope
and service registrations have been released.

## Security And Precedence

Keep credentials out of committed configuration and public bug reports. Use
the loader's documented environment and CLI override mechanisms for deployment
secrets. Configuration is validated before application startup; malformed or
removed sections fail `check` with a precise issue rather than being ignored.
Workspace configuration and resource files are treated as trusted local
filesystem inputs. Startup rejects ordinary symlink escapes, but no path check
can prevent an active external process from replacing a path between validation
and use; do not expose a live workspace to untrusted writers.

The generated template and `src/liteyukibot/config/models.py` are the source
of truth for field names and defaults. Update this page and the focused config
tests together when schema 7 changes.
