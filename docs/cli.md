# Liteyuki CLI

liteyuki manages one LiteyukiBot runtime instance at a time. The command line
--workspace option names the instance directory; it is separate from the
Python dependency workspace declared in pyproject.toml.

## Source Checkout

After the one-time environment setup:

~~~bash
uv sync --locked --all-packages
uv run --project . --locked liteyuki --workspace tmp/dev-instance init
uv run --project . --locked liteyuki --workspace tmp/dev-instance check
uv run --project . --locked liteyuki tests debug --workspace tmp/dev-instance --duration 0
uv run --project . --locked python -m scripts.run_source_smoke
~~~

The source smoke uses a disposable instance and runs the editable checkout
through uv. It does not build wheels or install a uv tool.

## Help

Use `help` without a target for the complete CLI syntax, or pass a command
path for its focused help:

~~~bash
liteyuki help
liteyuki help check
liteyuki help config show
liteyuki check --help
liteyuki -h check
~~~

Command paths are resolved from the parser's registered subcommands, including
aliases. The help command does not prepare or load a workspace. A CLI extension
that registers another parser automatically participates in the same help
lookup; it does not need a second command-to-help mapping.

## Development Debug Probe

`tests debug` starts the selected instance in the current process for a bounded
session. For a positive `--duration`, validation, startup, and runtime
observation must fit within the active diagnostic deadline. Cleanup is then
bounded by the configured shutdown timeout. A zero duration skips runtime
observation but still starts and stops the instance. It does not attach to,
inspect, or control a separate `liteyuki run` process, and it never changes the
instance configuration.

The default output is JSON Lines on stdout so an LLM or another tool can read
one `started`, `ready`, `snapshot`, `failed`, or `stopped` record at a time.
Each ready/snapshot/stopped record contains the JSON-safe application status
and topology. Application console logs remain on stderr. When `logging.file`
is configured, the most recent 20 lines are also included in each record; use
`--log-tail 0` to omit them or `--log-tail N` to change the bound.

~~~bash
liteyuki tests debug --instance dev --duration 10 --interval 1
liteyuki tests debug --instance dev --duration 0 --format text
liteyuki tests debug --instance dev --duration 5 --log-tail 50
~~~

Use ablations to isolate a failing boundary without editing the instance:

~~~bash
liteyuki tests debug --instance dev --ablate onebot --duration 0
liteyuki tests debug --instance dev --ablate plugins --duration 0
liteyuki tests debug --instance dev --ablate all --duration 0
~~~

`onebot` removes configured OneBot accounts for this session, and `plugins`
removes enabled external Cordis plugins. These overrides are applied only to
the debug process. The probe does not capture message bodies, credentials, or
full configuration values.

## Instance Nicknames

Register a directory once, then use its nickname instead of repeating the
absolute path:

~~~bash
liteyuki instance add dev C:\bots\dev
liteyuki instance add staging C:\bots\staging
liteyuki instance list
liteyuki instance use dev

liteyuki init
liteyuki check
liteyuki run
liteyuki --instance staging check
liteyuki check --workspace dev
~~~

instance is also available as workspace. add is also available as register;
remove is also available as unregister. Registration does not create a
directory. init creates the configuration and resource index, and remove only
removes the nickname mapping; it never deletes the instance directory.

The registry is stored at ~/.liteyuki/instances.json. Set
LITEYUKI_INSTANCE_REGISTRY to use another registry file, which is useful for
tests and isolated development environments.

Instance selection precedence is:

1. --instance NAME.
2. --workspace PATH_OR_NAME; an existing or path-like value is treated as a
   path, otherwise a registered nickname is tried.
3. The current directory when it contains liteyuki.toml.
4. The selected default from instance use.
5. The current directory.

Pass --workspace . when the current directory must be used even if a default
instance has been selected. Shared options may be placed before the command or
after the selected command.

## Commands

~~~text
liteyuki [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS]

Commands:
  help                        show help for the CLI or a command
  init                         create a schema-7 instance configuration
  check                        validate configuration without starting
  run                          start the selected instance in the foreground
  config show                  print resolved redacted configuration
  config explain POINTER       show a value and its source chain
  plugin ...                   manage Cordis plugin bundles
  instance add NAME PATH       register an instance nickname
  instance list                list registered nicknames
  instance use NAME            select the default nickname
  instance path NAME           print a registered path
  instance remove NAME         remove a nickname mapping
  tests debug                  run a bounded runtime diagnostic probe
~~~

Useful global options:

~~~text
--workspace PATH_OR_NAME       instance directory or registered nickname
--instance NAME                registered nickname
--config PATH                  additional configuration file; repeatable
--set KEY=VALUE                command-line override; repeatable
~~~

check --format json emits a machine-readable success result. Configuration
errors return exit code 2; an interactive interruption of run or debug returns
130. `tests debug` returns 2 when startup or cleanup fails.
