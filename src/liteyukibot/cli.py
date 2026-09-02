"""Foreground command line interface for LiteyukiBot v7."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from math import isfinite
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
from .instances import InstanceRegistry
from .plugin_manager import DEFAULT_PLUGIN_INDEX_URL, PluginManager

_DEBUG_SCHEMA_VERSION = 1
_DEBUG_ABLATIONS = frozenset({"onebot", "plugins"})
_DEBUG_ABLATION_ALIASES = {"all": _DEBUG_ABLATIONS}
_DEBUG_LOG_TAIL_BYTES = 256 * 1024


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a finite non-negative number") from error
    if not isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("expected a finite non-negative number")
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a finite positive number") from error
    if not isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("expected a finite positive number")
    return parsed


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a non-negative integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer")
    return parsed


def _add_context_options(parser: argparse.ArgumentParser, *, suppress_defaults: bool = False) -> None:
    """Add options shared by application commands."""
    default_workspace: str | None | object = argparse.SUPPRESS if suppress_defaults else None
    default_instance: str | None | object = argparse.SUPPRESS if suppress_defaults else None
    default_configs: list[str] | object = argparse.SUPPRESS if suppress_defaults else []
    default_overrides: list[str] | object = argparse.SUPPRESS if suppress_defaults else []
    workspace = parser.add_mutually_exclusive_group()
    workspace.add_argument(
        "--workspace",
        default=default_workspace,
        metavar="PATH_OR_NAME",
        help="runtime instance directory or a registered instance nickname",
    )
    workspace.add_argument(
        "--instance",
        default=default_instance,
        metavar="NAME",
        help="registered instance nickname (an alternative to --workspace)",
    )
    parser.add_argument(
        "--config",
        action="append",
        default=default_configs,
        metavar="PATH",
        help="additional TOML, JSON, or YAML configuration file; repeatable",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=default_overrides,
        dest="overrides",
        metavar="KEY=VALUE",
        help="override a configuration value; JSON values are parsed when possible; repeatable",
    )


def _normalize_help_argv(argv: Sequence[str]) -> list[str]:
    """Normalize the prefix form ``liteyuki -h COMMAND`` to the help command."""
    values = list(argv)
    if len(values) > 1 and values[0] in {"-h", "--help"}:
        return ["help", *values[1:]]
    return values


def _subparser_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """Return the registered child parsers without duplicating the command tree."""
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict) and all(
            isinstance(value, argparse.ArgumentParser) for value in choices.values()
        ):
            return cast(dict[str, argparse.ArgumentParser], choices)
    return {}


def _resolve_help_parser(
    parser: argparse.ArgumentParser,
    command_path: Sequence[str],
) -> argparse.ArgumentParser | None:
    """Resolve a command path by walking the parsers registered in argparse."""
    current = parser
    for command in command_path:
        next_parser = _subparser_choices(current).get(command)
        if next_parser is None:
            return None
        current = next_parser
    return current


def build_parser() -> argparse.ArgumentParser:
    """Build the supported foreground CLI parser."""
    parser = argparse.ArgumentParser(
        prog="liteyuki",
        description="Run and inspect a LiteyukiBot v7 application instance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  liteyuki --workspace PATH init\n"
            "  liteyuki --workspace PATH check\n"
            "  liteyuki help check\n"
            "  liteyuki instance add dev PATH\n"
            "  liteyuki --instance dev run\n"
            "  liteyuki check --instance dev --format json\n"
            "  liteyuki tests debug --instance dev --duration 0"
        ),
    )
    parser.add_argument("--version", action="version", version=__version__, help="show the installed version")
    _add_context_options(parser)

    subcommands = parser.add_subparsers(dest="command", required=True)
    help_command = subcommands.add_parser(
        "help",
        help="show help for the CLI or a command",
        description="Show the full CLI help or detailed help for a registered command path.",
    )
    help_command.add_argument(
        "command_path",
        nargs="*",
        metavar="COMMAND",
        help="command path to describe, for example config show",
    )
    _add_context_options(help_command, suppress_defaults=True)
    run = subcommands.add_parser(
        "run",
        help="run LiteyukiBot in the foreground",
        description="Start the selected instance and wait for SIGINT, SIGTERM, or Windows SIGBREAK.",
    )
    _add_context_options(run, suppress_defaults=True)
    check = subcommands.add_parser(
        "check",
        help="validate the project configuration",
        description="Validate configuration and enabled feature dependencies without starting the application.",
    )
    check.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="success output format (default: text)",
    )
    _add_context_options(check, suppress_defaults=True)
    subcommands.add_parser("version", help="show the installed version")

    init = subcommands.add_parser(
        "init",
        help="create a project configuration",
        description="Create a schema-7 configuration and resource index for the selected instance.",
    )
    init.add_argument(
        "--locale",
        choices=("auto", "zh-CN", "en-US"),
        default="auto",
        help="initial locale (default: auto)",
    )
    _add_context_options(init, suppress_defaults=True)

    config = subcommands.add_parser("config", help="inspect project configuration")
    _add_context_options(config, suppress_defaults=True)
    config_commands = config.add_subparsers(dest="config_command", required=True)
    show = config_commands.add_parser("show", help="show the resolved configuration")
    show.add_argument(
        "--format",
        choices=("json", "toml"),
        default="json",
        help="output format (default: json; secrets are redacted)",
    )
    _add_context_options(show, suppress_defaults=True)
    explain = config_commands.add_parser("explain", help="explain one resolved configuration value")
    explain.add_argument("pointer", help="JSON Pointer, for example /core/data_dir")
    _add_context_options(explain, suppress_defaults=True)

    plugin = subcommands.add_parser("plugin", help="discover and manage Cordis plugins")
    _add_context_options(plugin, suppress_defaults=True)
    plugin.add_argument(
        "--index-url",
        default=DEFAULT_PLUGIN_INDEX_URL,
        metavar="URL",
        help="plugin metadata index URL",
    )
    plugin_commands = plugin.add_subparsers(dest="plugin_command", required=True)
    plugin_list = plugin_commands.add_parser("list", help="list bundles available from the plugin index")
    plugin_list.add_argument(
        "query",
        nargs="?",
        help="filter by bundle ID, name, summary, or tag",
    )
    plugin_list.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    plugin_list.add_argument(
        "--index-url",
        dest="index_url",
        default=argparse.SUPPRESS,
        metavar="URL",
        help="plugin metadata index URL",
    )
    _add_context_options(plugin_list, suppress_defaults=True)
    plugin_show = plugin_commands.add_parser("show", help="show one bundle from the plugin index")
    plugin_show.add_argument("bundle_id", help="bundle ID")
    plugin_show.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    plugin_show.add_argument(
        "--index-url",
        dest="index_url",
        default=argparse.SUPPRESS,
        metavar="URL",
        help="plugin metadata index URL",
    )
    _add_context_options(plugin_show, suppress_defaults=True)
    plugin_installed = plugin_commands.add_parser("installed", help="list locally installed plugin bundles")
    plugin_installed.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    plugin_installed.add_argument(
        "--index-url",
        dest="index_url",
        default=argparse.SUPPRESS,
        metavar="URL",
        help="plugin metadata index URL",
    )
    _add_context_options(plugin_installed, suppress_defaults=True)
    plugin_install = plugin_commands.add_parser("install", help="install one bundle into the current uv tool")
    plugin_install.add_argument("bundle_id", help="bundle ID")
    plugin_install.add_argument(
        "--no-enable",
        action="store_true",
        help="install without activating the bundle",
    )
    plugin_install.add_argument(
        "--index-url",
        dest="index_url",
        default=argparse.SUPPRESS,
        metavar="URL",
        help="plugin metadata index URL",
    )
    _add_context_options(plugin_install, suppress_defaults=True)
    for command, help_text in (
        ("enable", "activate an installed bundle"),
        ("disable", "deactivate an installed bundle"),
    ):
        operation = plugin_commands.add_parser(command, help=help_text)
        operation.add_argument("bundle_id", help="bundle ID")
        operation.add_argument(
            "--index-url",
            dest="index_url",
            default=argparse.SUPPRESS,
            metavar="URL",
            help="plugin metadata index URL",
        )
        _add_context_options(operation, suppress_defaults=True)
    plugin_remove = plugin_commands.add_parser(
        "remove",
        aliases=("uninstall",),
        help="uninstall an installed bundle",
    )
    plugin_remove.add_argument("bundle_id", help="bundle ID")
    plugin_remove.add_argument(
        "--index-url",
        dest="index_url",
        default=argparse.SUPPRESS,
        metavar="URL",
        help="plugin metadata index URL",
    )
    _add_context_options(plugin_remove, suppress_defaults=True)
    plugin_config = plugin_commands.add_parser("config", help="manage one installed plugin's local JSON config")
    _add_context_options(plugin_config, suppress_defaults=True)
    plugin_config.add_argument(
        "--index-url",
        dest="index_url",
        default=argparse.SUPPRESS,
        metavar="URL",
        help="plugin metadata index URL",
    )
    plugin_config_commands = plugin_config.add_subparsers(dest="plugin_config_command", required=True)
    plugin_config_show = plugin_config_commands.add_parser("show", help="show local plugin configuration")
    plugin_config_show.add_argument("bundle_id", help="bundle ID")
    plugin_config_show.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    plugin_config_show.add_argument(
        "--index-url",
        dest="index_url",
        default=argparse.SUPPRESS,
        metavar="URL",
        help="plugin metadata index URL",
    )
    _add_context_options(plugin_config_show, suppress_defaults=True)
    plugin_config_set = plugin_config_commands.add_parser("set", help="set JSON-compatible plugin configuration values")
    plugin_config_set.add_argument("bundle_id", help="bundle ID")
    plugin_config_set.add_argument("assignments", nargs="+", metavar="KEY=VALUE")
    plugin_config_set.add_argument("--entry-point", metavar="ID", help="target one entry point in the bundle")
    plugin_config_set.add_argument(
        "--index-url",
        dest="index_url",
        default=argparse.SUPPRESS,
        metavar="URL",
        help="plugin metadata index URL",
    )
    _add_context_options(plugin_config_set, suppress_defaults=True)
    plugin_config_clear = plugin_config_commands.add_parser("clear", help="clear one plugin's local configuration")
    plugin_config_clear.add_argument("bundle_id", help="bundle ID")
    plugin_config_clear.add_argument("--entry-point", metavar="ID", help="target one entry point in the bundle")
    plugin_config_clear.add_argument(
        "--index-url",
        dest="index_url",
        default=argparse.SUPPRESS,
        metavar="URL",
        help="plugin metadata index URL",
    )
    _add_context_options(plugin_config_clear, suppress_defaults=True)

    instance = subcommands.add_parser(
        "instance",
        aliases=("workspace",),
        help="register and select runtime instances",
        description=(
            "Manage nickname mappings for Liteyuki runtime instance directories. "
            "Removing a mapping never deletes its directory."
        ),
    )
    instance_commands = instance.add_subparsers(dest="instance_command", required=True)
    instance_add = instance_commands.add_parser(
        "add",
        aliases=("register",),
        help="register a nickname for an instance directory",
    )
    instance_add.add_argument("name", metavar="NAME", help="nickname, using ASCII letters, numbers, '.', '_' or '-'")
    instance_add.add_argument("path", metavar="PATH", type=Path, help="instance directory; it may not exist yet")
    instance_add.add_argument(
        "--force",
        action="store_true",
        help="replace an existing nickname mapping",
    )
    instance_list = instance_commands.add_parser("list", help="list registered instance nicknames")
    instance_list.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    instance_use = instance_commands.add_parser("use", help="select the default instance nickname")
    instance_use.add_argument("name", metavar="NAME", help="registered nickname")
    instance_remove = instance_commands.add_parser(
        "remove",
        aliases=("unregister",),
        help="remove a nickname mapping without deleting its directory",
    )
    instance_remove.add_argument("name", metavar="NAME", help="registered nickname")
    instance_path = instance_commands.add_parser("path", help="print the path for a registered nickname")
    instance_path.add_argument("name", metavar="NAME", help="registered nickname")

    tests = subcommands.add_parser(
        "tests",
        help="run development validation probes",
        description="Run bounded development diagnostic probes against the selected instance.",
    )
    _add_context_options(tests, suppress_defaults=True)
    test_commands = tests.add_subparsers(dest="tests_command", required=True)
    debug = test_commands.add_parser(
        "debug",
        help="start the instance and stream runtime diagnostics",
        description=(
            "Start one local instance for a bounded diagnostic session. "
            "Status and topology are written as JSON Lines by default; application logs remain on stderr or in "
            "the configured log file."
        ),
    )
    debug.add_argument(
        "--format",
        choices=("jsonl", "text"),
        default="jsonl",
        help="diagnostic output format (default: jsonl)",
    )
    debug.add_argument(
        "--duration",
        type=_non_negative_float,
        default=5.0,
        metavar="SECONDS",
        help="maximum session duration; 0 starts and stops immediately (default: 5)",
    )
    debug.add_argument(
        "--interval",
        type=_positive_float,
        default=1.0,
        metavar="SECONDS",
        help="interval between runtime snapshots (default: 1)",
    )
    debug.add_argument(
        "--ablate",
        action="append",
        choices=("onebot", "plugins", "all"),
        default=[],
        metavar="COMPONENT",
        help="disable a component for this run; repeat for an ablation experiment",
    )
    debug.add_argument(
        "--log-tail",
        type=_non_negative_int,
        default=20,
        metavar="N",
        help="include up to N lines from logging.file in each snapshot; 0 disables it (default: 20)",
    )
    _add_context_options(debug, suppress_defaults=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one supported CLI operation and return its process status."""
    parser = build_parser()
    raw_argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(_normalize_help_argv(raw_argv))
    if args.command == "help":
        return _help(parser, args.command_path)
    if args.command == "version":
        print(__version__)
        return 0
    try:
        if args.command in {"instance", "workspace"}:
            return _instance(args)
        workspace_directory = _resolve_workspace(args, use_default=True)
        if args.command == "init":
            return _init(workspace_directory, args.locale)

        workspace = ConfigWorkspace(workspace_directory)
        workspace.prepare()
        if args.command == "config":
            if args.config_command == "show":
                return _config_show(workspace, args.config, args.overrides, args.format)
            if args.config_command == "explain":
                return _config_explain(workspace, args.config, args.overrides, args.pointer)
            raise ValueError(f"unknown configuration command: {args.config_command}")
        if args.command == "plugin":
            return _plugin(workspace, args)
        if args.command == "tests":
            if args.tests_command != "debug":
                raise ValueError(f"unknown tests command: {args.tests_command}")
            ablations = _normalize_debug_ablations(args.ablate)
            settings = _load(
                workspace,
                args.config,
                (*args.overrides, *_debug_config_overrides()),
            )
            settings = _apply_debug_ablations(settings, ablations)
            return _debug(
                settings,
                workspace.directory,
                duration=args.duration,
                interval=args.interval,
                output_format=args.format,
                ablations=ablations,
                log_tail=args.log_tail,
            )

        settings = _load(workspace, args.config, args.overrides)
        if args.command == "check":
            _check(settings, output_format=args.format)
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


def _help(parser: argparse.ArgumentParser, command_path: Sequence[str]) -> int:
    """Print the root or command-specific help without starting a workspace."""
    if not command_path:
        parser.print_help()
        return 0
    target = _resolve_help_parser(parser, command_path)
    if target is None:
        print(f"unknown command path: {' '.join(command_path)}", file=sys.stderr)
        return 2
    target.print_help()
    return 0


def _resolve_workspace(args: argparse.Namespace, *, use_default: bool) -> Path:
    """Resolve a path, registered nickname, or implicit default instance."""
    workspace_value = getattr(args, "workspace", None)
    instance_name = getattr(args, "instance", None)
    if workspace_value is not None and instance_name is not None:
        raise ValueError("--workspace and --instance cannot be used together")
    registry = InstanceRegistry()
    if instance_name is not None:
        return registry.resolve(instance_name).path
    if workspace_value is not None:
        candidate = Path(workspace_value).expanduser()
        if (
            candidate.exists()
            or candidate.is_absolute()
            or candidate.parent != Path(".")
            or workspace_value in {".", ".."}
            or workspace_value.startswith("~")
        ):
            return candidate.resolve()
        record = registry.find(workspace_value)
        return record.path if record is not None else candidate.resolve()

    current = Path.cwd().resolve()
    if not use_default or (current / ConfigWorkspace.filename).is_file():
        return current
    default = registry.default()
    return current if default is None else default.path


def _instance(args: argparse.Namespace) -> int:
    """Run one instance nickname registry operation."""
    registry = InstanceRegistry()
    command = args.instance_command
    if command in {"add", "register"}:
        record = registry.register(args.name, args.path, replace=args.force)
        print(f"registered: {record.name} -> {record.path}")
        return 0
    if command == "list":
        records = registry.list()
        default = registry.default()
        default_key = None if default is None else default.name.casefold()
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "default": None if default is None else default.name,
                        "instances": [
                            record.as_document(is_default=record.name.casefold() == default_key)
                            for record in records
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        elif not records:
            print("no registered instances")
        else:
            print("NAME\tPATH\tSTATUS")
            for record in records:
                status = "default" if record.name.casefold() == default_key else "-"
                print(f"{record.name}\t{record.path}\t{status}")
        return 0
    if command == "use":
        record = registry.set_default(args.name)
        print(f"default instance: {record.name}")
        return 0
    if command in {"remove", "unregister"}:
        record = registry.remove(args.name)
        print(f"unregistered: {record.name} (directory kept)")
        return 0
    if command == "path":
        print(registry.resolve(args.name).path)
        return 0
    raise ValueError(f"unknown instance command: {command}")


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


def _check(settings: AppSettings, *, output_format: str = "text") -> None:
    """Report successful validation of one immutable settings snapshot."""
    _validate(settings)
    if output_format == "json":
        print(json.dumps({"config_version": settings.config_version, "valid": True}, sort_keys=True))
    else:
        print("configuration valid")


def _validate(settings: AppSettings) -> None:
    """Validate configuration and enabled feature dependencies without output."""
    if settings.config_version != 7:
        raise ValueError("configuration is not version 7")
    settings.cordis.validate_enabled_config()
    from liteyukibot_adapter_onebot import OneBotV11Service
    from liteyukibot_cordis import discover_plugins

    discover_plugins(settings.cordis.enabled)
    OneBotV11Service(settings.onebot.v11.accounts)


def _normalize_debug_ablations(values: Sequence[str]) -> tuple[str, ...]:
    """Normalize component names used by the development ablation probe."""
    selected: set[str] = set()
    for value in values:
        if value in _DEBUG_ABLATION_ALIASES:
            selected.update(_DEBUG_ABLATION_ALIASES[value])
        elif value in _DEBUG_ABLATIONS:
            selected.add(value)
        else:
            raise ValueError(f"unknown debug ablation: {value}")
    return tuple(sorted(selected))


def _debug_config_overrides() -> tuple[str, ...]:
    """Build non-persistent overrides for one debug session."""
    return ("logging.json_lines=false",)


def _apply_debug_ablations(settings: AppSettings, ablations: Sequence[str]) -> AppSettings:
    """Apply component removals to an immutable settings copy for one debug run."""
    updates: dict[str, object] = {}
    if "onebot" in ablations:
        updates["onebot"] = settings.onebot.model_copy(
            update={"v11": settings.onebot.v11.model_copy(update={"accounts": {}})}
        )
    if "plugins" in ablations:
        updates["cordis"] = settings.cordis.model_copy(update={"enabled": (), "config": {}})
    return settings if not updates else settings.model_copy(update=updates)


def _debug(
    settings: AppSettings,
    resource_workspace: str | Path,
    *,
    duration: float,
    interval: float,
    output_format: str,
    ablations: Sequence[str],
    log_tail: int,
) -> int:
    """Run a bounded application diagnostic session for development tooling."""
    workspace = Path(resource_workspace).resolve()
    try:
        return asyncio.run(
            _debug_session(
                settings,
                workspace=workspace,
                duration=duration,
                interval=interval,
                output_format=output_format,
                ablations=ablations,
                log_tail=log_tail,
            )
        )
    except KeyboardInterrupt:
        return 130


async def _debug_session(
    settings: AppSettings,
    *,
    workspace: Path,
    duration: float,
    interval: float,
    output_format: str,
    ablations: Sequence[str],
    log_tail: int,
) -> int:
    """Start, observe, and stop one application without attaching to another process."""
    if not isfinite(duration) or duration < 0:
        raise ValueError("debug duration must be finite and non-negative")
    if not isfinite(interval) or interval <= 0:
        raise ValueError("debug interval must be finite and positive")
    if log_tail < 0:
        raise ValueError("debug log tail must be non-negative")

    app = LiteyukiApp(settings, resource_workspace=workspace)
    _emit_debug(
        output_format,
        "started",
        workspace=workspace,
        ablations=ablations,
        duration_seconds=duration,
        interval_seconds=interval,
        log_file=None if settings.logging.file is None else str(settings.logging.file),
    )

    session_error: BaseException | None = None
    cleanup_error: BaseException | None = None
    try:
        _validate(settings)
        await app.start()
        _emit_debug(
            output_format,
            "ready",
            workspace=workspace,
            ablations=ablations,
            **_debug_snapshot(app, settings, log_tail=log_tail),
        )
        deadline = monotonic() + duration
        while duration > 0:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(interval, remaining))
            _emit_debug(
                output_format,
                "snapshot",
                workspace=workspace,
                ablations=ablations,
                **_debug_snapshot(app, settings, log_tail=log_tail),
            )
    except (asyncio.CancelledError, KeyboardInterrupt):
        raise
    except BaseException as error:
        session_error = error
        _emit_debug(
            output_format,
            "failed",
            workspace=workspace,
            ablations=ablations,
            error=_debug_error(error),
            **_debug_snapshot(app, settings, log_tail=log_tail),
        )
    finally:
        try:
            await app.stop()
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except BaseException as error:
            cleanup_error = error
            _emit_debug(
                output_format,
                "cleanup_error",
                workspace=workspace,
                ablations=ablations,
                error=_debug_error(error),
                **_debug_snapshot(app, settings, log_tail=log_tail),
            )
        _emit_debug(
            output_format,
            "stopped",
            workspace=workspace,
            ablations=ablations,
            **_debug_snapshot(app, settings, log_tail=log_tail),
        )
    return 2 if session_error is not None or cleanup_error is not None else 0


def _debug_snapshot(app: LiteyukiApp, settings: AppSettings, *, log_tail: int) -> dict[str, object]:
    """Collect bounded, JSON-safe runtime data for one diagnostic record."""
    snapshot: dict[str, object] = {
        "status": app.status(),
        "topology": app.topology(),
    }
    if log_tail:
        lines, error = _read_log_tail(settings.logging.file, log_tail)
        snapshot["logs"] = lines
        snapshot["log_file"] = None if settings.logging.file is None else str(settings.logging.file)
        if error is not None:
            snapshot["log_error"] = error
    return snapshot


def _read_log_tail(path: Path | None, limit: int) -> tuple[list[str], str | None]:
    """Read a bounded tail from the configured application log without changing it."""
    if path is None or limit == 0 or not path.exists():
        return [], None
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - _DEBUG_LOG_TAIL_BYTES))
            content = stream.read(_DEBUG_LOG_TAIL_BYTES)
    except OSError as error:
        return [], f"{type(error).__name__}: {error}"
    return content.decode("utf-8", errors="replace").splitlines()[-limit:], None


def _debug_error(error: BaseException) -> dict[str, str]:
    """Render an exception without exposing a traceback or arbitrary object state."""
    return {"type": type(error).__name__, "message": str(error)}


def _emit_debug(
    output_format: str,
    kind: str,
    *,
    workspace: Path,
    ablations: Sequence[str],
    **fields: object,
) -> None:
    """Emit one stable diagnostic record for humans or an LLM-facing caller."""
    document: dict[str, object] = {
        "schema_version": _DEBUG_SCHEMA_VERSION,
        "kind": kind,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "workspace": str(workspace),
        "ablations": list(ablations),
        **fields,
    }
    if output_format == "jsonl":
        print(json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True), flush=True)
        return
    _print_debug_text(document)


def _print_debug_text(document: dict[str, object]) -> None:
    """Render one diagnostic record as concise text."""
    kind = str(document["kind"])
    if kind == "started":
        print(f"debug started: {document['workspace']}")
        if document["ablations"]:
            print(f"ablations: {', '.join(cast(list[str], document['ablations']))}")
        return
    if kind in {"failed", "cleanup_error"}:
        print(f"debug {kind}: {json.dumps(document.get('error', {}), ensure_ascii=False, sort_keys=True)}")
        return
    status = document.get("status")
    state = status.get("state", "unknown") if isinstance(status, dict) else "unknown"
    uptime = status.get("uptime_seconds", 0) if isinstance(status, dict) else 0
    print(f"debug {kind}: state={state} uptime={uptime}")
    for line in cast(list[str], document.get("logs", [])):
        print(f"  {line}")


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
    """Run an app until SIGINT/SIGTERM/SIGBREAK, with a Windows-compatible fallback."""
    app = LiteyukiApp(settings, resource_workspace=resource_workspace) if app_factory is None else app_factory(settings)
    stop_event = asyncio.Event()

    def request_stop(*_args: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    fallback: dict[signal.Signals, Any] = {}
    signals = _shutdown_signals()
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


def _shutdown_signals() -> tuple[signal.Signals, ...]:
    """Return portable termination signals, including Windows Ctrl+Break when available."""
    signals: list[signal.Signals] = [signal.SIGINT, signal.SIGTERM]
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        signals.append(cast(signal.Signals, sigbreak))
    return tuple(signals)


if __name__ == "__main__":
    raise SystemExit(main())
