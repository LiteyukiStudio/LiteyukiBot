# Configuration Operations

## Project Configuration

Outside Docker, every configuration-consuming command requires a project-root
liteyuki.toml. Create it with:

~~~bash
uv run liteyuki init
~~~

The interactive initializer is a responsive full-screen terminal wizard. It
starts with language, workspace, and a minimal-versus-custom choice; Back and
Cancel never write configuration. Selection pages support arrows, Space,
Enter, mouse input, and unique green mnemonic keys. Minimal setup creates safe
defaults without optional plugins or runtimes. Custom setup first collects
structured logging choices (level, console/JSON sinks, payload mode, and
runtime exclusions), then discovers installed native plugins and runtime
packages, resolves required native service providers, writes only package-owned
safe options, and can add message routes to an agent runtime. A broken,
unrelated entry point is reported as a diagnostic instead of preventing other
choices. The wizard does not paint a terminal background; transparency remains
the terminal emulator's setting.

liteyuki init --non-interactive and a missing Docker configuration both create
a minimal configuration with no enabled plugins, runtimes, or secrets.

`init --locale auto|zh-CN|en-US` selects the wizard and stored CLI language.
`auto` follows the system locale, but falls back to English when terminal CJK
font support cannot be detected. An explicit Chinese choice remains in effect
and emits a warning instead. Interactive setup requires a TTY; automation must
use `--non-interactive`.

## Local Run Console

Outside Docker, `ly run` runs a local daemon and opens a local administrator console in its worker when stdin and
stdout are TTYs. It coexists with normal logs and supports `help`, `status`,
`runtime list`, `runtime restart <id>`, and runtime-plugin lifecycle commands.
`plugin uninstall`, `plugin gc`, and `stop` require a `y/N` confirmation.
Docker and non-interactive hosts retain signal-only service mode. Successful
startup logs elapsed `run`-to-READY time in milliseconds with two decimals.

`ly run --detach` starts the same daemon in the background and writes its
standard output to `.liteyuki/instances/<name>/logs/daemon.log`. The worker owns
`data/instance.lock`; the daemon owns a separate instance lock and authenticated
loopback descriptor. Use `ly --instance NAME instance status|stop|restart|logs`
for lifecycle operations. With `daemon.auto_restart = true`, abnormal worker
exits retry with finite exponential backoff; clean exits never restart.

## Development Controls

Set `[development] dev_mode = true` to enable the local daemon development
commands. They authenticate to the instance descriptor and forward only to its
current worker; they are never exposed through HTTP. `watch_auto_restart =
true` watches project Python, resource, and configuration files with the
configured debounce period. A changed configuration is validated before a
restart, so an invalid edit leaves the healthy worker running.

~~~bash
liteyuki --instance dev dev status
liteyuki --instance dev dev topology
liteyuki --instance dev dev inject --file event.json
liteyuki --instance dev dev command "runtime restart example"
liteyuki --instance dev dev command --yes "stop"
~~~

`dev inject` accepts one JSON `EventEnvelope` from `--file` or standard input.
`dev command` runs an existing management command as the local administrator;
commands marked dangerous require `--yes`.

The optional Permissions package can grant management capabilities to named
plugin or runtime callers through `management_grants`; ungranted callers fail
closed. Runtime IPC can invoke only an existing, capability-authorized kernel
management command. It cannot execute a shell command or install a remote
handler.

## Native Adapter Runtimes

Install `liteyukibot-v7-runtime-adapter` with the required protocol package.
`onebot-v11` and `onebot-v12` support `transport = "http_post"` (the default),
`forward_websocket` with `ws_url`, and `reverse_websocket` with `ws_host`,
`ws_port`, and `ws_path`. Non-loopback OneBot listeners require `access_token`.

The `satori` adapter is an external Satori v1 gateway client, not a Node or
embedded gateway server. Configure an absolute `gateway_url`, `api_root`, and
an optional vault-backed `access_token`. Each account must be configured under
only one ingress adapter, including when an AstrBot or MoFox runtime is enabled.

## Resource Packs

The kernel loads read-only resource packs for language catalogs, functions, and
future static assets. Built-in packs are lowest priority, enabled plugin package
packs are next, and workspace packs listed in `resources/index.json` override
them. Workspace packs may be directories or ZIP files containing `metadata.yml`.
Their contents use paths such as `lang/zh-CN.lang`, `functions/`, and
`templates/`; packs are indexed directly and are never extracted into a merged
temporary directory.

The existing `liteyukibot-v7-resources` distribution is a separate user-resource
and permission-aware command plugin. It is not the resource-pack loader.

## Workspace Selection

The current directory is the default workspace. Use `--workspace PATH` before
the subcommand to operate on another project without changing the shell's
current directory:

~~~bash
liteyuki --workspace /srv/liteyuki init --non-interactive
liteyuki --workspace /srv/liteyuki run
~~~

Workspace-changing commands, including `init`, hold
`.liteyuki/instance.lock` for the duration of the operation. A running kernel
also holds `core.data_dir/instance.lock` for its full lifecycle. One resolved
data directory can therefore belong to only one live kernel; concurrent bots
must use distinct `core.data_dir` values. `liteyuki --version` is equivalent to
`liteyuki version`.

## Named Instances

Use `--instance NAME` before the subcommand to run a separate named bot from
the same workspace. Names use lower-case ASCII letters, digits, and hyphens.
The default instance preserves `core.data_dir`, `core.cache_dir`, and any
configured log file. A named instance derives all of those paths below
`.liteyuki/instances/<name>/`, so its kernel lock, cache, daemon descriptor,
logs, and future history cannot collide with another instance.

~~~bash
liteyuki --workspace /srv/liteyuki --instance staging check
liteyuki --instance staging config show
~~~

An optional `.liteyuki/instances/<name>.toml` overrides the base file and any
explicit `--config` files, but is still overridden by `LITEYUKI__...` and
`--set`. It may configure runtimes, plugins, HTTP ports, and daemon policy. It
cannot set `config_version`, `core.data_dir`, `core.cache_dir`, or
`logging.file`; named-instance storage is intentionally derived by the kernel.

## Instance Profiles

`liteyuki profile stage` creates an isolated uv environment below the workspace,
installs explicit requirements, and validates its configuration before it may be
activated. `activate` changes the profile pointer atomically; `run` and `check`
then use the selected profile Python. The previous verified profile remains
available for one-command rollback.

~~~bash
liteyuki profile stage --require "liteyukibot-v7==PUBLISHED_VERSION"
liteyuki profile list
liteyuki profile activate PROFILE_ID
liteyuki profile rollback
~~~

`liteyuki.lock` records the active/previous profile and its exact installed
distribution versions. Profiles never copy or migrate package-owned data.
Replace `PUBLISHED_VERSION` with a version that has already been uploaded; use
the release notes rather than a source-tree version that may not exist on PyPI.

## Precedence And Inspection

The effective order is:

1. Kernel defaults.
2. Included files, in declared order.
3. The including or primary file.
4. Repeated --config files, in command-line order.
5. The selected named-instance overlay, when present.
6. LITEYUKI__SECTION__FIELD environment variables.
7. Repeated --set section.field=JSON_VALUE options.

Use global CLI options before the subcommand:

~~~bash
uv run liteyuki --config local.toml --set logging.level=DEBUG config show
uv run liteyuki config show --format toml
uv run liteyuki config explain /plugins/config/example.plugin/value
~~~

config show emits redacted JSON by default. It recursively replaces values
whose keys indicate credentials, API keys, secrets, passwords, or tokens.
config explain uses RFC 6901 JSON Pointer paths and returns the final value
plus every source that overwrote it. JSON Pointer keeps dotted plugin IDs
unambiguous.

TOML has no null literal. config show --format toml omits optional null object
fields, which reload as their model defaults, and rejects null array values
instead of changing their meaning.

## Secret Vault

Runtime secret bindings use normalized IDs in liteyuki.toml; plaintext is
stored only in .liteyuki/secrets.v1.json. The vault derives its encryption key
with scrypt and encrypts the complete mapping with AES-256-GCM.

~~~bash
uv run liteyuki vault set runtime.agent.api_key_secret
uv run liteyuki vault list
uv run liteyuki vault delete runtime.agent.api_key_secret
uv run liteyuki vault rotate
~~~

Local commands use hidden password prompts. Docker requires
LITEYUKI_VAULT_PASSWORD; it is removed from every child runtime environment.
The kernel decrypts only the IDs required by enabled runtimes and injects each
value only into the environment variable declared by that runtime's InitSpec.
Secrets never enter runtime IPC, control APIs, or configuration diagnostics.

The native agent runtime uses LITEYUKI_AGENT_API_KEY by default. Existing
api_key_env configuration remains an explicit compatibility override.

## Upgrade Material

config_version = 3 is the current v7 pre-release schema. Configurations
schema. A root configuration with a missing or older version is preserved and
blocks startup after generating:

- a backup under .liteyuki/config-backups/;
- a current template under .liteyuki/config-upgrades/;
- recovery instructions in that upgrade directory.

Generation is idempotent. After reviewing and merging the template manually,
use this command only when a fresh backup/template is required:

~~~bash
uv run liteyuki config upgrade --refresh
~~~

Configurations from a newer schema are rejected without creating backups.
