"""Dependency-free LiteyukiBot v7 command line interface."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import signal
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from . import __version__
from .app import LiteyukiApp
from .config import AppSettings, ConfigurationError, ConfigWorkspace, load_settings
from .config.initializer import build_initialization_plan
from .config.vault import SecretVault
from .control import ControlError, request_control
from .exceptions import LiteyukiError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="liteyuki")
    parser.add_argument("--config", action="append", default=[], metavar="PATH")
    parser.add_argument("--set", action="append", default=[], dest="overrides", metavar="KEY=VALUE")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("run", help="start the application")
    subcommands.add_parser("check", help="validate configuration and plugin topology")
    subcommands.add_parser("version", help="show the installed version")
    init = subcommands.add_parser("init", help="create a project configuration")
    init.add_argument("--non-interactive", action="store_true")

    config = subcommands.add_parser("config", help="configuration operations")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("validate")
    upgrade = config_commands.add_parser("upgrade")
    upgrade.add_argument("--refresh", action="store_true")

    vault = subcommands.add_parser("vault", help="encrypted secret vault operations")
    vault_commands = vault.add_subparsers(dest="vault_command", required=True)
    vault_set = vault_commands.add_parser("set")
    vault_set.add_argument("name")
    vault_delete = vault_commands.add_parser("delete")
    vault_delete.add_argument("name")
    vault_commands.add_parser("list")
    vault_commands.add_parser("rotate")

    plugin = subcommands.add_parser("plugin", help="plugin operations")
    plugin.add_subparsers(dest="plugin_command", required=True).add_parser("list")

    runtime = subcommands.add_parser("runtime", help="runtime operations")
    runtime_commands = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_commands.add_parser("list")
    restart = runtime_commands.add_parser("restart")
    restart.add_argument("runtime_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    try:
        if args.command == "init":
            return _init(args.non_interactive)
        if args.command == "config" and args.config_command == "upgrade":
            return _upgrade(args.refresh)
        if args.command == "vault":
            return _vault(args)
        settings = _load(args.config, args.overrides)
        if args.command == "run":
            return _run(settings, _runtime_secrets(settings))
        if args.command in {"check", "config"}:
            if args.command == "check":
                _check(settings)
            print("configuration valid")
            return 0
        if args.command == "plugin":
            _list_plugins(settings)
            return 0
        if args.command == "runtime":
            return asyncio.run(_runtime_command(settings, args.runtime_command, args))
    except (ConfigurationError, ControlError, LiteyukiError, RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    return 2


def _load(config_paths: Sequence[str], overrides: Sequence[str]) -> AppSettings:
    primary = ConfigWorkspace().prepare()
    return load_settings(
        primary,
        config_paths=config_paths,
        cli_overrides=overrides,
    )


def _init(non_interactive: bool) -> int:
    workspace = ConfigWorkspace()
    if non_interactive:
        path = workspace.initialize()
    else:
        plan = build_initialization_plan(
            prompt=_prompt,
            output=lambda message: print(message, file=sys.stderr),
            secret_prompt=_prompt_secret,
        )
        if plan.secrets:
            vault = SecretVault(workspace.management_directory)
            vault.initialize(_vault_password(workspace, create=True), plan.secrets)
        path = workspace.initialize(
            data_dir=plan.data_dir,
            cache_dir=plan.cache_dir,
            logging_level=plan.logging_level,
            payload_mode=plan.payload_mode,
            payload_exclude_runtimes=plan.payload_exclude_runtimes,
            plugins=plan.plugins,
            plugin_config=plan.plugin_config,
            runtimes=plan.runtimes,
            runtime_event_routes=plan.runtime_event_routes,
        )
    print(f"created {path}")
    return 0


def _upgrade(refresh: bool) -> int:
    result = ConfigWorkspace().upgrade(refresh=refresh)
    if result is None:
        print("configuration is current")
    return 0


def _vault(args: argparse.Namespace) -> int:
    workspace = ConfigWorkspace()
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


def _runtime_secrets(settings: AppSettings) -> dict[str, str]:
    names = {
        secret_name
        for runtime in settings.runtimes.values()
        if runtime.enabled
        for secret_name in runtime.secret_env.values()
    }
    if not names:
        return {}
    workspace = ConfigWorkspace()
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


def _run(settings: AppSettings, runtime_secrets: Mapping[str, str]) -> int:
    try:
        asyncio.run(_run_until_signal(settings, runtime_secrets))
    except KeyboardInterrupt:
        return 130
    return 0


async def _run_until_signal(settings: AppSettings, runtime_secrets: Mapping[str, str] | None = None) -> None:
    """Run the app until SIGINT/SIGTERM and always perform graceful cleanup."""

    app = LiteyukiApp(settings) if runtime_secrets is None else LiteyukiApp(settings, runtime_secrets=runtime_secrets)
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
            runtimes = status.get("runtimes", {}) if isinstance(status, dict) else {}
            for runtime_id, state in runtimes.items():
                print(f"{runtime_id}\t{state}")
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
