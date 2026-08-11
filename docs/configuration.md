# Configuration Operations

## Project Configuration

Outside Docker, every configuration-consuming command requires a project-root
liteyuki.toml. Create it with:

~~~bash
uv run liteyuki init
~~~

The interactive initializer is a full-screen terminal wizard. It starts with
language, workspace, and a minimal-versus-custom choice; Back and Cancel never
write configuration. Minimal setup creates safe defaults without optional
plugins or runtimes. Custom setup discovers installed native plugins and runtime
packages, resolves required native service providers, writes only package-owned
safe options, and can add message routes to an agent runtime. A broken,
unrelated entry point is reported as a diagnostic instead of preventing other
choices.

liteyuki init --non-interactive and a missing Docker configuration both create
a minimal configuration with no enabled plugins, runtimes, or secrets.

`init --locale auto|zh-CN|en-US` selects the wizard and stored CLI language.
`auto` follows the system locale, but falls back to English when terminal CJK
font support cannot be detected. An explicit Chinese choice remains in effect
and emits a warning instead. Interactive setup requires a TTY; automation must
use `--non-interactive`.

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

`init` and `run` hold `.liteyuki/instance.lock` for the duration of the
operation. A second process for the same workspace exits rather than replacing
the active control descriptor. `liteyuki --version` is equivalent to
`liteyuki version`.

## Precedence And Inspection

The effective order is:

1. Kernel defaults.
2. Included files, in declared order.
3. The including or primary file.
4. Repeated --config files, in command-line order.
5. LITEYUKI__SECTION__FIELD environment variables.
6. Repeated --set section.field=JSON_VALUE options.

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

config_version = 1 is the current v7 alpha schema. A root configuration with a
missing or older version is preserved and blocks startup after generating:

- a backup under .liteyuki/config-backups/;
- a current template under .liteyuki/config-upgrades/;
- recovery instructions in that upgrade directory.

Generation is idempotent. After reviewing and merging the template manually,
use this command only when a fresh backup/template is required:

~~~bash
uv run liteyuki config upgrade --refresh
~~~

Configurations from a newer schema are rejected without creating backups.
