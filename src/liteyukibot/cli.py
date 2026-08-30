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
from typing import Any, cast

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
from .plugin_manager import DEFAULT_PLUGIN_INDEX_URL, PluginManager


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

    plugin = subcommands.add_parser("plugin", help="discover and manage Cordis plugins")
    plugin.add_argument("--index-url", default=DEFAULT_PLUGIN_INDEX_URL, metavar="URL")
    plugin_commands = plugin.add_subparsers(dest="plugin_command", required=True)
    plugin_list = plugin_commands.add_parser("list", help="list bundles available from the plugin index")
    plugin_list.add_argument("query", nargs="?", help="filter by bundle ID, name, summary, or tag")
    plugin_list.add_argument("--format", choices=("text", "json"), default="text")
    plugin_list.add_argument("--index-url", dest="index_url", default=argparse.SUPPRESS, metavar="URL")
    plugin_show = plugin_commands.add_parser("show", help="show one bundle from the plugin index")
    plugin_show.add_argument("bundle_id")
    plugin_show.add_argument("--format", choices=("text", "json"), default="text")
    plugin_show.add_argument("--index-url", dest="index_url", default=argparse.SUPPRESS, metavar="URL")
    plugin_installed = plugin_commands.add_parser("installed", help="list locally installed plugin bundles")
    plugin_installed.add_argument("--format", choices=("text", "json"), default="text")
    plugin_installed.add_argument("--index-url", dest="index_url", default=argparse.SUPPRESS, metavar="URL")
    plugin_install = plugin_commands.add_parser("install", help="install one bundle into the current uv tool")
    plugin_install.add_argument("bundle_id")
    plugin_install.add_argument("--no-enable", action="store_true", help="install without activating the bundle")
    plugin_install.add_argument("--index-url", dest="index_url", default=argparse.SUPPRESS, metavar="URL")
    for command, help_text in (
        ("enable", "activate an installed bundle"),
        ("disable", "deactivate an installed bundle"),
    ):
        operation = plugin_commands.add_parser(command, help=help_text)
        operation.add_argument("bundle_id")
        operation.add_argument("--index-url", dest="index_url", default=argparse.SUPPRESS, metavar="URL")
    plugin_remove = plugin_commands.add_parser("remove", aliases=("uninstall",), help="uninstall an installed bundle")
    plugin_remove.add_argument("bundle_id")
    plugin_remove.add_argument("--index-url", dest="index_url", default=argparse.SUPPRESS, metavar="URL")
    plugin_config = plugin_commands.add_parser("config", help="manage one installed plugin's local JSON config")
    plugin_config_commands = plugin_config.add_subparsers(dest="plugin_config_command", required=True)
    plugin_config_show = plugin_config_commands.add_parser("show", help="show local plugin configuration")
    plugin_config_show.add_argument("bundle_id")
    plugin_config_show.add_argument("--format", choices=("text", "json"), default="text")
    plugin_config_show.add_argument("--index-url", dest="index_url", default=argparse.SUPPRESS, metavar="URL")
    plugin_config_set = plugin_config_commands.add_parser("set", help="set JSON-compatible plugin configuration values")
    plugin_config_set.add_argument("bundle_id")
    plugin_config_set.add_argument("assignments", nargs="+", metavar="KEY=VALUE")
    plugin_config_set.add_argument("--entry-point", metavar="ID")
    plugin_config_set.add_argument("--index-url", dest="index_url", default=argparse.SUPPRESS, metavar="URL")
    plugin_config_clear = plugin_config_commands.add_parser("clear", help="clear one plugin's local configuration")
    plugin_config_clear.add_argument("bundle_id")
    plugin_config_clear.add_argument("--entry-point", metavar="ID")
    plugin_config_clear.add_argument("--index-url", dest="index_url", default=argparse.SUPPRESS, metavar="URL")
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
        if args.command == "plugin":
            return _plugin(workspace, args)

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


def _plugin(workspace: ConfigWorkspace, args: argparse.Namespace) -> int:
    """Run one local-only plugin index or activation operation."""
    if args.config or args.overrides:
        raise ValueError("plugin commands do not support --config or --set; use plugin config instead")
    manager = PluginManager(workspace, index_url=args.index_url)
    command = args.plugin_command
    if command == "list":
        index = manager.fetch_index()
        query = args.query.casefold() if args.query else None
        bundles = tuple(
            bundle
            for bundle in index.bundles
            if query is None
            or query in bundle.id.casefold()
            or query in bundle.display_name.casefold()
            or query in bundle.summary.casefold()
            or any(query in tag.casefold() for tag in cast(tuple[str, ...], bundle.optional.get("tags", ())))
        )
        if args.format == "json":
            print(
                json.dumps([bundle.as_document() for bundle in bundles], ensure_ascii=False, indent=2, sort_keys=True)
            )
        elif not bundles:
            print("no plugin bundles available")
        else:
            print("ID\tVERSION\tNAME\tPROJECT")
            for bundle in bundles:
                print(f"{bundle.id}\t{bundle.version}\t{bundle.display_name}\t{bundle.project_id or '-'}")
        return 0
    if command == "show":
        bundle = manager.fetch_index().require(args.bundle_id)
        if args.format == "json":
            print(json.dumps(bundle.as_document(), ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"{bundle.id} {bundle.version}")
            print(bundle.display_name)
            print(bundle.summary)
            print(f"project: {bundle.project_id or '-'}")
            print(f"status: {bundle.status}")
            print(f"dependencies: {', '.join(bundle.dependencies) or '-'}")
            for facet in bundle.facets:
                capabilities = ",".join(facet.capabilities) or "-"
                print(f"facet: {facet.runtime_kind}, wheels={len(facet.wheels)}, capabilities={capabilities}")
        return 0
    if command == "installed":
        installed = manager.installed()
        if args.format == "json":
            print(
                json.dumps([record.as_document() for record in installed], ensure_ascii=False, indent=2, sort_keys=True)
            )
        elif not installed:
            print("no installed plugin bundles")
        else:
            print("ID\tVERSION\tSTATUS\tPROJECT")
            for record in installed:
                status = "enabled" if record.enabled else "disabled"
                print(f"{record.id}\t{record.version}\t{status}\t{record.project_id}")
        return 0
    if command == "install":
        records = manager.install(args.bundle_id, enable=not args.no_enable)
        state = "enabled" if not args.no_enable else "disabled"
        print(f"installed ({state}): {', '.join(record.id for record in records)}")
        return 0
    if command == "enable":
        record = manager.enable(args.bundle_id)
        print(f"enabled: {record.id}")
        return 0
    if command == "disable":
        record = manager.disable(args.bundle_id)
        print(f"disabled: {record.id}")
        return 0
    if command == "config":
        if args.plugin_config_command == "show":
            value = manager.config(args.bundle_id)
            if args.format == "json":
                print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                for entry_point, config in value.items():
                    print(f"[{entry_point}]")
                    print(json.dumps(config, ensure_ascii=False, sort_keys=True))
            return 0
        if args.plugin_config_command == "set":
            value = manager.set_config(args.bundle_id, args.assignments, entry_point=args.entry_point)
            print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.plugin_config_command == "clear":
            manager.clear_config(args.bundle_id, entry_point=args.entry_point)
            print(f"cleared: {args.bundle_id}")
            return 0
        raise ValueError(f"unknown plugin configuration command: {args.plugin_config_command}")
    if command in {"remove", "uninstall"}:
        manager.remove(args.bundle_id)
        print(f"removed: {args.bundle_id}")
        return 0
    raise ValueError(f"unknown plugin command: {command}")


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
