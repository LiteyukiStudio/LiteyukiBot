"""Dependency-free LiteyukiBot v7 command line interface."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout
from tomli_w import dumps as dump_toml

from . import __version__
from .app import LiteyukiApp
from .config import (
    AppSettings,
    ConfigInspection,
    ConfigurationError,
    ConfigWorkspace,
    inspect_settings,
    load_settings,
    redact_config,
    toml_compatible_config,
)
from .config.vault import SecretVault
from .control import ControlError, request_control
from .exceptions import LiteyukiError
from .init_wizard import WizardCancelled, build_custom_initialization_plan, run_init_wizard
from .plugin_install import PluginInstallationService
from .plugin_sources import PluginSource, PluginSourceStore
from .plugin_store import RuntimeGenerationStore
from .profiles import ProfileManifest, ProfileStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="liteyuki")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--workspace", default=".", metavar="PATH", help="project workspace directory")
    parser.add_argument("--config", action="append", default=[], metavar="PATH")
    parser.add_argument("--set", action="append", default=[], dest="overrides", metavar="KEY=VALUE")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("run", help="start the application")
    subcommands.add_parser("check", help="validate configuration and plugin topology")
    subcommands.add_parser("version", help="show the installed version")
    init = subcommands.add_parser("init", help="create a project configuration")
    init.add_argument("--non-interactive", action="store_true")
    init.add_argument("--locale", choices=("auto", "zh-CN", "en-US"), default="auto")

    config = subcommands.add_parser("config", help="configuration operations")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("validate")
    upgrade = config_commands.add_parser("upgrade")
    upgrade.add_argument("--refresh", action="store_true")
    show = config_commands.add_parser("show")
    show.add_argument("--format", choices=("json", "toml"), default="json")
    explain = config_commands.add_parser("explain")
    explain.add_argument("pointer")

    vault = subcommands.add_parser("vault", help="encrypted secret vault operations")
    vault_commands = vault.add_subparsers(dest="vault_command", required=True)
    vault_set = vault_commands.add_parser("set")
    vault_set.add_argument("name")
    vault_delete = vault_commands.add_parser("delete")
    vault_delete.add_argument("name")
    vault_commands.add_parser("list")
    vault_commands.add_parser("rotate")

    plugin = subcommands.add_parser("plugin", help="plugin operations")
    plugin_commands = plugin.add_subparsers(dest="plugin_command", required=True)
    plugin_list = plugin_commands.add_parser("list")
    plugin_list.add_argument("--runtime", dest="runtime_id")
    plugin_install = plugin_commands.add_parser("install", help="install a runtime plugin bundle")
    plugin_install.add_argument("bundle_id")
    plugin_install.add_argument("--runtime", required=True, dest="runtime_id")
    plugin_install.add_argument("--source", dest="source_id")
    plugin_update = plugin_commands.add_parser("update", help="rebuild a runtime plugin generation from its source")
    plugin_update.add_argument("--runtime", required=True, dest="runtime_id")
    plugin_update.add_argument("--source", dest="source_id")
    plugin_disable = plugin_commands.add_parser("disable", help="disable one retained runtime plugin bundle root")
    plugin_disable.add_argument("bundle_id")
    plugin_disable.add_argument("--runtime", required=True, dest="runtime_id")
    plugin_enable = plugin_commands.add_parser("enable", help="re-enable one retained runtime plugin bundle root")
    plugin_enable.add_argument("bundle_id")
    plugin_enable.add_argument("--runtime", required=True, dest="runtime_id")
    plugin_uninstall = plugin_commands.add_parser("uninstall", help="remove one runtime plugin bundle root")
    plugin_uninstall.add_argument("bundle_id")
    plugin_uninstall.add_argument("--runtime", required=True, dest="runtime_id")
    plugin_gc = plugin_commands.add_parser("gc", help="remove unreferenced runtime plugin generations")
    plugin_gc.add_argument("--runtime", dest="runtime_id")
    plugin_rollback = plugin_commands.add_parser("rollback", help="restore a runtime's previous plugin generation")
    plugin_rollback.add_argument("--runtime", required=True, dest="runtime_id")
    plugin_source = plugin_commands.add_parser("source", help="plugin index source operations")
    plugin_source_commands = plugin_source.add_subparsers(dest="plugin_source_command", required=True)
    plugin_source_commands.add_parser("list")
    source_add = plugin_source_commands.add_parser("add")
    source_add.add_argument("id")
    source_add.add_argument("url")
    source_add.add_argument("--priority", type=int, default=100)
    source_remove = plugin_source_commands.add_parser("remove")
    source_remove.add_argument("id")

    inspect = subcommands.add_parser("inspect", help="read-only resolved module information")
    inspect.add_subparsers(dest="inspect_command", required=True).add_parser("topology")

    runtime = subcommands.add_parser("runtime", help="runtime operations")
    runtime_commands = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_commands.add_parser("list")
    restart = runtime_commands.add_parser("restart")
    restart.add_argument("runtime_id")
    profile = subcommands.add_parser("profile", help="isolated runtime profile operations")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    stage = profile_commands.add_parser("stage")
    stage.add_argument("--require", action="append", required=True, dest="requirements", metavar="REQUIREMENT")
    profile_commands.add_parser("list")
    show_profile = profile_commands.add_parser("show")
    show_profile.add_argument("profile_id", nargs="?")
    activate = profile_commands.add_parser("activate")
    activate.add_argument("profile_id")
    profile_commands.add_parser("rollback")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    command_line = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(command_line)
    if args.command == "version":
        print(__version__)
        return 0
    try:
        if args.command == "init":
            return _init(args.workspace, args.non_interactive, args.locale)
        if args.command == "config" and args.config_command == "upgrade":
            return _upgrade(args.workspace, args.refresh)
        if args.command == "config" and args.config_command == "show":
            return _config_show(args)
        if args.command == "config" and args.config_command == "explain":
            return _config_explain(args)
        if args.command == "vault":
            return _vault(args)
        if args.command == "profile":
            return _profile(args)
        if args.command == "plugin" and args.plugin_command == "source":
            return _plugin_source(args)
        workspace = ConfigWorkspace(args.workspace)
        if args.command in {"run", "check"}:
            delegated = _delegate_to_active_profile(workspace, command_line)
            if delegated is not None:
                return delegated
        settings = _load(workspace, args.config, args.overrides)
        if args.command == "run":
            return _run(settings, workspace)
        if args.command in {"check", "config"}:
            if args.command == "check":
                _check(settings)
            print("configuration valid")
            return 0
        if args.command == "plugin":
            if args.plugin_command == "install":
                return _plugin_install(args, settings, workspace)
            if args.plugin_command == "rollback":
                return _plugin_rollback(args, settings, workspace)
            if args.plugin_command == "update":
                return _plugin_update(args, settings, workspace)
            if args.plugin_command == "uninstall":
                return _plugin_uninstall(args, settings, workspace)
            if args.plugin_command == "disable":
                return _plugin_disable(args, settings, workspace)
            if args.plugin_command == "enable":
                return _plugin_enable(args, settings, workspace)
            if args.plugin_command == "gc":
                return _plugin_gc(args, workspace)
            if args.runtime_id is not None:
                _list_runtime_plugin_generations(workspace, args.runtime_id)
            else:
                _list_plugins(settings)
            return 0
        if args.command == "inspect":
            print(json.dumps(LiteyukiApp(settings).topology(discover_plugins=True), ensure_ascii=False, default=str))
            return 0
        if args.command == "runtime":
            return asyncio.run(_runtime_command(settings, args.runtime_command, args))
    except (ConfigurationError, ControlError, LiteyukiError, RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    return 2


def _delegate_to_active_profile(workspace: ConfigWorkspace, command_line: Sequence[str]) -> int | None:
    if os.environ.get("LITEYUKI_PROFILE_STAGE") == "1":
        return None
    store = ProfileStore(workspace.directory)
    profile_id = store.active()
    if profile_id is None:
        return None
    python = ProfileStore.python_path(store.profile_path(profile_id)).resolve()
    if python == Path(sys.executable).resolve():
        return None
    return subprocess.run(
        [str(python), "-m", "liteyukibot.cli", *command_line],
        cwd=workspace.directory,
        check=False,
    ).returncode


def _load(workspace: ConfigWorkspace, config_paths: Sequence[str], overrides: Sequence[str]) -> AppSettings:
    primary = workspace.prepare()
    return load_settings(
        primary,
        config_paths=config_paths,
        cli_overrides=overrides,
    )


def _init(directory: str, non_interactive: bool, locale: str) -> int:
    if non_interactive:
        workspace = ConfigWorkspace(directory)
        with _exclusive_workspace(workspace):
            path = workspace.initialize(locale=locale)
        print(f"created {path}")
        return 0
    try:
        selection = run_init_wizard(directory, locale)
    except WizardCancelled:
        print("initialization cancelled")
        return 130
    if selection.warning:
        print(selection.warning, file=sys.stderr)
    workspace = ConfigWorkspace(selection.workspace)
    with _exclusive_workspace(workspace):
        if selection.mode == "minimal":
            path = workspace.initialize(locale=selection.locale)
        else:
            plan, diagnostics = build_custom_initialization_plan(selection.locale)
            for diagnostic in diagnostics:
                print(diagnostic, file=sys.stderr)
            if plan.secrets:
                vault = SecretVault(workspace.management_directory)
                vault.initialize(_vault_password(workspace, create=True), plan.secrets)
            path = workspace.initialize(
                data_dir=plan.data_dir,
                cache_dir=plan.cache_dir,
                logging_level=plan.logging_level,
                payload_mode=plan.payload_mode,
                payload_exclude_runtimes=plan.payload_exclude_runtimes,
                locale=selection.locale,
                plugins=plan.plugins,
                plugin_config=plan.plugin_config,
                runtimes=plan.runtimes,
                runtime_event_routes=plan.runtime_event_routes,
            )
    print(f"created {path}")
    return 0


def _upgrade(directory: str, refresh: bool) -> int:
    result = ConfigWorkspace(directory).upgrade(refresh=refresh)
    if result is None:
        print("configuration is current")
    return 0


def _profile(args: argparse.Namespace) -> int:
    workspace = ConfigWorkspace(args.workspace)
    workspace.prepare()
    with _exclusive_workspace(workspace):
        return _profile_unlocked(args, workspace)


def _plugin_source(args: argparse.Namespace) -> int:
    workspace = ConfigWorkspace(args.workspace)
    with _exclusive_workspace(workspace):
        store = PluginSourceStore(workspace.directory)
        if args.plugin_source_command == "list":
            for source in store.list():
                digest = store.cached_digest(source.id) or "-"
                print(f"{source.id}\t{source.priority}\t{source.url}\t{digest}")
            return 0
        if args.plugin_source_command == "add":
            store.add(PluginSource(args.id, args.url, args.priority))
            print(f"added {args.id}")
            return 0
        if args.plugin_source_command == "remove":
            store.remove(args.id)
            print(f"removed {args.id}")
            return 0
    raise RuntimeError(f"unknown plugin source command: {args.plugin_source_command}")


def _plugin_install(args: argparse.Namespace, settings: AppSettings, workspace: ConfigWorkspace) -> int:
    runtime = _configured_runtime(args.runtime_id, settings)
    with _exclusive_workspace(workspace):
        result = PluginInstallationService(workspace.directory).install(
            args.bundle_id,
            runtime_id=args.runtime_id,
            runtime_kind=runtime.kind,
            source_id=args.source_id,
        )
    print(f"installed {args.bundle_id} from {result.source_id} as {result.generation.id}")
    return 0


def _plugin_rollback(args: argparse.Namespace, settings: AppSettings, workspace: ConfigWorkspace) -> int:
    if args.runtime_id not in settings.runtimes:
        raise ValueError(f"runtime {args.runtime_id!r} is not configured")
    with _exclusive_workspace(workspace):
        deployment = RuntimeGenerationStore(workspace.directory).rollback(args.runtime_id)
    print(f"activated {deployment.runtime_generations[args.runtime_id]}")
    return 0


def _plugin_update(args: argparse.Namespace, settings: AppSettings, workspace: ConfigWorkspace) -> int:
    runtime = _configured_runtime(args.runtime_id, settings)
    with _exclusive_workspace(workspace):
        result = PluginInstallationService(workspace.directory).update(
            runtime_id=args.runtime_id,
            runtime_kind=runtime.kind,
            source_id=args.source_id,
        )
    print(f"updated {args.runtime_id} from {result.source_id} as {result.generation.id}")
    return 0


def _plugin_uninstall(args: argparse.Namespace, settings: AppSettings, workspace: ConfigWorkspace) -> int:
    runtime = _configured_runtime(args.runtime_id, settings)
    with _exclusive_workspace(workspace):
        result = PluginInstallationService(workspace.directory).uninstall(
            args.bundle_id,
            runtime_id=args.runtime_id,
            runtime_kind=runtime.kind,
        )
    if result.generation is None:
        print(f"uninstalled {args.bundle_id}; deactivated {args.runtime_id}")
    else:
        print(f"uninstalled {args.bundle_id}; activated {result.generation.id}")
    return 0


def _plugin_disable(args: argparse.Namespace, settings: AppSettings, workspace: ConfigWorkspace) -> int:
    runtime = _configured_runtime(args.runtime_id, settings)
    with _exclusive_workspace(workspace):
        result = PluginInstallationService(workspace.directory).disable(
            args.bundle_id,
            runtime_id=args.runtime_id,
            runtime_kind=runtime.kind,
        )
    print(f"disabled {args.bundle_id}; activated {result.generation.id}")
    return 0


def _plugin_enable(args: argparse.Namespace, settings: AppSettings, workspace: ConfigWorkspace) -> int:
    runtime = _configured_runtime(args.runtime_id, settings)
    with _exclusive_workspace(workspace):
        result = PluginInstallationService(workspace.directory).enable(
            args.bundle_id,
            runtime_id=args.runtime_id,
            runtime_kind=runtime.kind,
        )
    print(f"enabled {args.bundle_id}; activated {result.generation.id}")
    return 0


def _plugin_gc(args: argparse.Namespace, workspace: ConfigWorkspace) -> int:
    with _exclusive_workspace(workspace):
        collected = RuntimeGenerationStore(workspace.directory).collect(args.runtime_id)
    for generation in collected:
        print(f"collected\t{generation.runtime_id}\t{generation.id}")
    print(f"collected {len(collected)} runtime plugin generation(s)")
    return 0


def _configured_runtime(runtime_id: str, settings: AppSettings) -> Any:
    try:
        runtime = settings.runtimes[runtime_id]
    except KeyError as error:
        raise ValueError(f"runtime {runtime_id!r} is not configured") from error
    if not runtime.enabled:
        raise ValueError(f"runtime {runtime_id!r} is disabled")
    return runtime


def _profile_unlocked(args: argparse.Namespace, workspace: ConfigWorkspace) -> int:
    store = ProfileStore(workspace.directory)
    if args.profile_command == "stage":
        profile_id, path = store.create(tuple(args.requirements))
        python = ProfileStore.python_path(path)
        environment = {**os.environ, "LITEYUKI_PROFILE_STAGE": "1"}
        try:
            subprocess.run(["uv", "venv", "--python", "3.14", str(path / "venv")], check=True)
            subprocess.run(["uv", "pip", "install", "--python", str(python), *args.requirements], check=True)
            subprocess.run(
                [str(python), "-m", "liteyukibot.cli", "--workspace", str(workspace.directory), "check"],
                check=True,
                env=environment,
            )
            report = subprocess.check_output(
                [
                    str(python),
                    "-c",
                    "import importlib.metadata as m, json, sys; "
                    "print(json.dumps({'python': sys.executable, 'distributions': "
                    "{d.metadata['Name'].lower(): d.version for d in m.distributions() "
                    "if d.metadata.get('Name')}, 'direct_urls': "
                    "{d.metadata['Name'].lower(): json.loads(raw) for d in m.distributions() "
                    "if d.metadata.get('Name') and (raw := d.read_text('direct_url.json'))}}, sort_keys=True))",
                ],
                text=True,
            )
        except BaseException:
            shutil.rmtree(path, ignore_errors=True)
            raise
        observed = json.loads(report)
        manifest = ProfileManifest(
            profile_id,
            datetime.now(UTC).isoformat(),
            tuple(args.requirements),
            str(observed["python"]),
            {str(name): str(version) for name, version in dict(observed["distributions"]).items()},
            ProfileManifest.sanitize_direct_urls(dict(observed.get("direct_urls", {}))),
        )
        store.write_manifest(manifest)
        print(profile_id)
        return 0
    if args.profile_command == "list":
        active = store.active()
        for item in store.list():
            print(f"{'*' if item.id == active else ' '}\t{item.id}\t{item.created_at}")
        return 0
    if args.profile_command == "show":
        selected_profile_id = args.profile_id or store.active()
        if not isinstance(selected_profile_id, str):
            raise ValueError("no active profile")
        print(json.dumps(store.read_manifest(selected_profile_id).document(), indent=2, sort_keys=True))
        return 0
    if args.profile_command == "activate":
        store.activate(args.profile_id)
        print(f"activated {args.profile_id}")
        return 0
    if args.profile_command == "rollback":
        print(f"activated {store.rollback()}")
        return 0
    raise RuntimeError(f"unknown profile command: {args.profile_command}")


def _config_show(args: argparse.Namespace) -> int:
    inspection = _inspect(args)
    document = redact_config(inspection.settings.model_dump(mode="json"))
    if args.format == "toml":
        print(dump_toml(toml_compatible_config(document)), end="")
    else:
        print(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _config_explain(args: argparse.Namespace) -> int:
    explanation = _inspect(args).explain(args.pointer)
    print(
        json.dumps(
            {
                "pointer": explanation.pointer,
                "value": redact_config(explanation.value),
                "sources": [
                    {"kind": source.kind, "source": source.source}
                    for source in explanation.sources
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _inspect(args: argparse.Namespace) -> ConfigInspection:
    primary = ConfigWorkspace(args.workspace).prepare()
    return inspect_settings(
        primary,
        config_paths=args.config,
        cli_overrides=args.overrides,
    )


def _vault(args: argparse.Namespace) -> int:
    workspace = ConfigWorkspace(args.workspace)
    workspace.prepare()
    vault = SecretVault(workspace.management_directory)
    if args.vault_command == "set":
        password = _vault_password(workspace, create=not vault.path.exists())
        vault.set(password, args.name, _prompt_secret(f"Secret value for {args.name}"))
        print(f"stored secret {args.name}")
        return 0
    if args.vault_command == "delete":
        deleted = vault.delete(_vault_password(workspace), args.name)
        if not deleted:
            raise ValueError(f"secret {args.name!r} does not exist")
        print(f"deleted secret {args.name}")
        return 0
    if args.vault_command == "list":
        for name in vault.list_names(_vault_password(workspace)):
            print(name)
        return 0
    if args.vault_command == "rotate":
        password = _vault_password(workspace)
        vault.rotate(password, _vault_password(workspace, create=True))
        print("vault password rotated")
        return 0
    raise RuntimeError(f"unknown vault command: {args.vault_command}")


def _prompt(label: str, default: str) -> str:
    try:
        value = input(f"{label} [{default}]: ").strip()
    except EOFError:
        return default
    return value or default


def _prompt_secret(label: str) -> str:
    value = getpass.getpass(f"{label}: ")
    if not value:
        raise ValueError(f"{label} must not be empty")
    return value


def _vault_password(workspace: ConfigWorkspace, *, create: bool = False) -> str:
    if workspace.is_docker():
        value = os.environ.get("LITEYUKI_VAULT_PASSWORD", "")
        if not value:
            raise ValueError("LITEYUKI_VAULT_PASSWORD is required for Docker secret vault access")
        return value
    value = _prompt_secret("Vault password" if not create else "New vault password")
    if create and value != _prompt_secret("Confirm vault password"):
        raise ValueError("vault passwords do not match")
    return value


def _runtime_secrets(settings: AppSettings, workspace: ConfigWorkspace) -> dict[str, str]:
    names = {
        secret_name
        for runtime in settings.runtimes.values()
        if runtime.enabled
        for secret_name in runtime.secret_env.values()
    }
    if not names:
        return {}
    values = SecretVault(workspace.management_directory).read(_vault_password(workspace))
    missing = sorted(names - values.keys())
    if missing:
        raise ValueError(f"secret vault is missing required secrets: {', '.join(missing)}")
    return {name: values[name] for name in names}


def _check(settings: AppSettings) -> None:
    app = LiteyukiApp(settings)
    definitions = app.plugins.discover(settings.plugins.enabled, settings.plugins.local_modules)
    app.plugins.resolve_order(definitions)


def _list_plugins(settings: AppSettings) -> None:
    app = LiteyukiApp(settings)
    definitions = app.plugins.discover(settings.plugins.enabled, settings.plugins.local_modules)
    for plugin_id in app.plugins.resolve_order(definitions):
        manifest = definitions[plugin_id].manifest
        print(f"{manifest.id}\t{manifest.version}\t{manifest.name}")


def _list_runtime_plugin_generations(workspace: ConfigWorkspace, runtime_id: str) -> None:
    store = RuntimeGenerationStore(workspace.directory)
    deployment = store.active()
    active = deployment.runtime_generations.get(runtime_id)
    previous = deployment.previous.get(runtime_id)
    for generation in store.list_generations(runtime_id):
        state = "active" if generation.id == active else "previous" if generation.id == previous else "retained"
        enabled_roots = tuple(root for root in generation.roots if root not in generation.disabled_roots)
        roots = enabled_roots or generation.bundles
        disabled = ",".join(generation.disabled_roots) or "-"
        print(f"{state}\t{generation.id}\t{generation.source_id or '-'}\t{','.join(roots)}\t{disabled}")


def _run(settings: AppSettings, workspace: ConfigWorkspace) -> int:
    try:
        with _exclusive_workspace(workspace):
            asyncio.run(_run_until_signal(settings, _runtime_secrets(settings, workspace), workspace.directory))
    except KeyboardInterrupt:
        return 130
    return 0


@contextmanager
def _exclusive_workspace(workspace: ConfigWorkspace) -> Iterator[None]:
    """Prevent init or run from replacing one workspace's live control state."""

    workspace.management_directory.mkdir(parents=True, exist_ok=True)
    lock = FileLock(workspace.management_directory / "instance.lock", timeout=0)
    try:
        with lock:
            yield
    except Timeout as error:
        raise RuntimeError(f"another LiteyukiBot command is active for {workspace.directory}") from error


async def _run_until_signal(
    settings: AppSettings,
    runtime_secrets: Mapping[str, str] | None = None,
    resource_workspace: str | os.PathLike[str] = ".",
) -> None:
    """Run the app until SIGINT/SIGTERM and always perform graceful cleanup."""

    if resource_workspace == ".":
        if runtime_secrets is None:
            app = LiteyukiApp(settings)
        else:
            app = LiteyukiApp(settings, runtime_secrets=runtime_secrets)
    elif runtime_secrets is None:
        app = LiteyukiApp(settings, resource_workspace=str(resource_workspace))
    else:
        app = LiteyukiApp(
            settings,
            resource_workspace=str(resource_workspace),
            runtime_secrets=runtime_secrets,
        )
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    async_handlers: list[signal.Signals] = []
    fallback_handlers: dict[signal.Signals, Any] = {}

    def request_stop() -> None:
        loop.call_soon_threadsafe(stop_event.set)

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, request_stop)
        except NotImplementedError, RuntimeError, ValueError:
            try:
                previous = signal.getsignal(signum)
                signal.signal(signum, lambda _signum, _frame: request_stop())
            except OSError, RuntimeError, ValueError:
                continue
            fallback_handlers[signum] = previous
        else:
            async_handlers.append(signum)

    started = False
    try:
        await app.start()
        started = True
        await stop_event.wait()
    finally:
        try:
            if started:
                await app.stop()
        finally:
            for signum in async_handlers:
                loop.remove_signal_handler(signum)
            for signum, previous in fallback_handlers.items():
                signal.signal(signum, previous)


async def _runtime_command(settings: AppSettings, command: str, args: argparse.Namespace) -> int:
    descriptor = settings.core.data_dir / "control.json"
    if command == "list":
        if descriptor.is_file():
            status = await request_control(descriptor, "status")
            health = status.get("runtime_health", {}) if isinstance(status, dict) else {}
            if isinstance(health, dict):
                for runtime_id, snapshot in health.items():
                    if isinstance(snapshot, dict):
                        protocol = snapshot.get("protocol")
                        fields = [str(runtime_id), str(snapshot.get("state")), str(snapshot.get("kind"))]
                        if protocol is not None:
                            fields.append(f"v{protocol}")
                        print("\t".join(fields))
        else:
            for runtime_id, runtime in settings.runtimes.items():
                state = "disabled" if not runtime.enabled else "configured"
                print(f"{runtime_id}\t{state}")
        return 0
    if command == "restart":
        result: Any = await request_control(
            descriptor,
            "runtime.restart",
            runtime_id=args.runtime_id,
        )
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0
    raise RuntimeError(f"unknown runtime command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
