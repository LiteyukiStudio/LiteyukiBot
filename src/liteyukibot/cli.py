"""Foreground command line interface for LiteyukiBot v7."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from time import monotonic
from typing import Any

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
from .exceptions import LiteyukiError


def build_parser() -> argparse.ArgumentParser:
    """Build the supported foreground CLI parser."""
    parser = argparse.ArgumentParser(prog="liteyuki")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--workspace", default=".", metavar="PATH", help="project workspace directory")
    parser.add_argument("--config", action="append", default=[], metavar="PATH")
    parser.add_argument("--set", action="append", default=[], dest="overrides", metavar="KEY=VALUE")

    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("run", help="run LiteyukiBot in the foreground")
    subcommands.add_parser("check", help="validate the project configuration")
    subcommands.add_parser("version", help="show the installed version")

    init = subcommands.add_parser("init", help="create a project configuration")
    init.add_argument("--locale", choices=("auto", "zh-CN", "en-US"), default="auto")

    config = subcommands.add_parser("config", help="inspect project configuration")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    show = config_commands.add_parser("show", help="show the resolved configuration")
    show.add_argument("--format", choices=("json", "toml"), default="json")
    explain = config_commands.add_parser("explain", help="explain one resolved configuration value")
    explain.add_argument("pointer", help="JSON Pointer, for example /core/data_dir")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one supported CLI operation and return its process status."""
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "init":
        try:
            return _init(args.workspace, args.locale)
        except (ConfigurationError, LiteyukiError, OSError, RuntimeError, ValueError) as error:
            _print_error(error)
            return 2

    workspace = ConfigWorkspace(args.workspace)
    try:
        workspace.prepare()
        if args.command == "config":
            if args.config_command == "show":
                return _config_show(workspace, args.config, args.overrides, args.format)
            if args.config_command == "explain":
                return _config_explain(workspace, args.config, args.overrides, args.pointer)
            raise ValueError(f"unknown configuration command: {args.config_command}")

        settings = _load(workspace, args.config, args.overrides)
        if args.command == "check":
            _check(settings)
            return 0
        if args.command == "run":
            return _run(settings, workspace.directory)
        raise ValueError(f"unknown command: {args.command}")
    except (ConfigurationError, LiteyukiError, OSError, RuntimeError, ValueError) as error:
        _print_error(error)
        return 2


def _print_error(error: BaseException) -> None:
    """Print one concise CLI error without a traceback."""
    print(str(error), file=sys.stderr)


def _load(
    workspace: ConfigWorkspace,
    config_paths: Sequence[str | Path] = (),
    overrides: Sequence[str] = (),
) -> AppSettings:
    """Prepare and load the workspace's merged configuration."""
    primary = workspace.prepare()
    return load_settings(primary, config_paths=config_paths, cli_overrides=overrides)


def _init(directory: str | Path, locale: str = "auto") -> int:
    """Create the minimal v7 workspace configuration."""
    path = ConfigWorkspace(directory).initialize(locale=locale)
    print(path)
    return 0


def _check(settings: AppSettings) -> None:
    """Report successful validation of one immutable settings snapshot."""
    if settings.config_version != 7:
        raise ValueError("configuration is not version 7")
    settings.cordis.validate_enabled_config()
    from liteyukibot_adapter_onebot import OneBotV11Service
    from liteyukibot_cordis import discover_plugins

    discover_plugins(settings.cordis.enabled)
    OneBotV11Service(settings.onebot.v11.accounts)
    print("configuration valid")


def _config_show(
    workspace: ConfigWorkspace,
    config_paths: Sequence[str | Path],
    overrides: Sequence[str],
    output_format: str,
) -> int:
    """Render the resolved configuration in a safe machine-readable form."""
    inspection = _inspect(workspace, config_paths, overrides)
    value = redact_config(inspection.settings.model_dump(mode="json"))
    if output_format == "toml":
        print(dump_toml(toml_compatible_config(value)), end="")
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _config_explain(
    workspace: ConfigWorkspace,
    config_paths: Sequence[str | Path],
    overrides: Sequence[str],
    pointer: str,
) -> int:
    """Render one resolved value and its configuration source chain."""
    explanation = _inspect(workspace, config_paths, overrides).explain(pointer)
    value = redact_config(explanation.value)
    document = {
        "pointer": explanation.pointer,
        "value": value,
        "sources": [{"kind": source.kind, "source": source.source} for source in explanation.sources],
    }
    print(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _inspect(
    workspace: ConfigWorkspace,
    config_paths: Sequence[str | Path],
    overrides: Sequence[str],
) -> ConfigInspection:
    """Prepare and inspect one merged configuration snapshot."""
    primary = workspace.prepare()
    return inspect_settings(primary, config_paths=config_paths, cli_overrides=overrides)


def _run(settings: AppSettings, resource_workspace: str | Path) -> int:
    """Run the local application in the foreground."""
    try:
        asyncio.run(_run_until_signal(settings, resource_workspace=resource_workspace))
    except KeyboardInterrupt:
        return 130
    return 0


async def _run_until_signal(
    settings: AppSettings,
    *,
    resource_workspace: str | Path = ".",
    app_factory: Callable[..., LiteyukiApp] | None = None,
) -> None:
    """Run an app until SIGINT/SIGTERM, with a Windows-compatible fallback."""
    app = LiteyukiApp(settings, resource_workspace=resource_workspace) if app_factory is None else app_factory(settings)
    stop_event = asyncio.Event()

    def request_stop(*_args: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    fallback: dict[signal.Signals, Any] = {}
    signals = tuple(signum for signum in (signal.SIGINT, signal.SIGTERM) if signum is not None)
    try:
        for signum in signals:
            try:
                loop.add_signal_handler(signum, request_stop)
            except (NotImplementedError, RuntimeError, ValueError):
                try:
                    fallback[signum] = signal.getsignal(signum)
                    signal.signal(signum, lambda received, frame: loop.call_soon_threadsafe(request_stop))
                except (NotImplementedError, RuntimeError, ValueError):
                    fallback.pop(signum, None)
            else:
                installed.append(signum)

        started = monotonic()
        await app.start()
        app.logger.info("LiteyukiBot startup completed in {:.2f} ms", (monotonic() - started) * 1000)
        await stop_event.wait()
    finally:
        for signum in installed:
            try:
                loop.remove_signal_handler(signum)
            except (NotImplementedError, RuntimeError, ValueError):
                pass
        for signum, previous in fallback.items():
            try:
                signal.signal(signum, previous)
            except (NotImplementedError, RuntimeError, ValueError):
                pass
        await app.stop()


if __name__ == "__main__":
    raise SystemExit(main())
