"""Dependency-free LiteyukiBot v7 command line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__
from .app import LiteyukiApp
from .config import AppSettings, ConfigurationError, ConfigWorkspace, load_settings
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
    config.add_subparsers(dest="config_command", required=True).add_parser("validate")

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
        settings = _load(args.config, args.overrides)
        if args.command == "run":
            return _run(settings)
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
        path = workspace.initialize(
            data_dir=_prompt("Data directory", "data"),
            cache_dir=_prompt("Cache directory", "cache"),
            logging_level=_prompt("Logging level", "INFO").upper(),
            payload_mode=_prompt("Payload logging mode (metadata/full)", "metadata").lower(),
            payload_exclude_runtimes=tuple(
                item.strip()
                for item in _prompt("Payload exclusion runtime IDs (comma-separated)", "").split(",")
                if item.strip()
            ),
        )
    print(f"created {path}")
    return 0


def _prompt(label: str, default: str) -> str:
    try:
        value = input(f"{label} [{default}]: ").strip()
    except EOFError:
        return default
    return value or default


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


def _run(settings: AppSettings) -> int:
    try:
        asyncio.run(_run_until_signal(settings))
    except KeyboardInterrupt:
        return 130
    return 0


async def _run_until_signal(settings: AppSettings) -> None:
    """Run the app until SIGINT/SIGTERM and always perform graceful cleanup."""

    app = LiteyukiApp(settings)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    async_handlers: list[signal.Signals] = []
    fallback_handlers: dict[signal.Signals, Any] = {}

    def request_stop() -> None:
        loop.call_soon_threadsafe(stop_event.set)

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, request_stop)
        except (NotImplementedError, RuntimeError, ValueError):
            try:
                previous = signal.getsignal(signum)
                signal.signal(signum, lambda _signum, _frame: request_stop())
            except (OSError, RuntimeError, ValueError):
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
