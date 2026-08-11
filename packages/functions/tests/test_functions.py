from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from liteyukibot_functions import V6FunctionCapabilityError, V6FunctionExecutor, V6FunctionSyntaxError

from liteyukibot.functions import FunctionCall, FunctionDispatcher, FunctionError, FunctionRecursionError
from liteyukibot.resource_packs import ResourceCatalog


def _resources(tmp_path: Path, functions: Mapping[str, str]) -> ResourceCatalog:
    pack = tmp_path / "resources" / "legacy"
    function_directory = pack / "functions"
    function_directory.mkdir(parents=True, exist_ok=True)
    (pack / "metadata.yml").write_text('id: legacy\nname: Legacy\nversion: "6"\n', encoding="utf-8")
    for name, source in functions.items():
        path = function_directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    (tmp_path / "resources" / "index.json").write_text('["legacy"]', encoding="utf-8")
    return ResourceCatalog.load(tmp_path)


def _dispatcher(tmp_path: Path, functions: Mapping[str, str]) -> FunctionDispatcher:
    return FunctionDispatcher(
        _resources(tmp_path, functions),
        executors={extension: V6FunctionExecutor() for extension in V6FunctionExecutor.extensions},
    )


class Capabilities:
    def __init__(self) -> None:
        self.apis: list[tuple[str, Mapping[str, Any]]] = []
        self.commands: list[str] = []

    async def call_api(self, api: str, params: Mapping[str, Any]) -> None:
        self.apis.append((api, params))

    async def run_command(self, command: str) -> None:
        self.commands.append(command)


@pytest.mark.asyncio
async def test_v6_executor_supports_variables_interpolation_and_api_calls(tmp_path: Path) -> None:
    dispatcher = _dispatcher(
        tmp_path,
        {"hello.lyf": "var target=friend\napi poke user_id=${target}\napi send message={0}\n"},
    )
    capabilities = Capabilities()

    await dispatcher.dispatch(FunctionCall("hello", {}, positional=("hello",), capabilities=capabilities))

    assert capabilities.apis == [
        ("poke", {"user_id": "friend"}),
        ("send", {"message": "hello"}),
    ]


@pytest.mark.asyncio
async def test_v6_executor_is_discovered_from_the_installed_entry_point(tmp_path: Path) -> None:
    dispatcher = FunctionDispatcher(_resources(tmp_path, {"installed.lyf": "api verify value=1\n"}))
    capabilities = Capabilities()

    await dispatcher.dispatch(FunctionCall("installed", {}, capabilities=capabilities))

    assert capabilities.apis == [("verify", {"value": 1})]


@pytest.mark.asyncio
async def test_v6_executor_supports_nested_nohup_and_await(tmp_path: Path) -> None:
    dispatcher = _dispatcher(
        tmp_path,
        {
            "main.lyfunction": "function child value=1\n",
            "child.mcfunction": "nohup api record value=value\nawait\n",
        },
    )
    capabilities = Capabilities()

    await dispatcher.dispatch(FunctionCall("main", {}, capabilities=capabilities))

    assert capabilities.apis == [("record", {"value": 1})]


@pytest.mark.asyncio
async def test_v6_executor_requires_explicit_capabilities(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path, {"unsafe.lyf": "api poke\n"})

    with pytest.raises(V6FunctionCapabilityError, match="call_api"):
        await dispatcher.dispatch(FunctionCall("unsafe", {}))


@pytest.mark.asyncio
async def test_v6_executor_delegates_command_without_spawning_a_shell(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path, {"command.lyf": "cmd echo hello\n"})
    capabilities = Capabilities()

    await dispatcher.dispatch(FunctionCall("command", {}, capabilities=capabilities))

    assert capabilities.commands == ["echo hello"]


@pytest.mark.asyncio
async def test_v6_executor_rejects_unknown_instructions_and_recursive_functions(tmp_path: Path) -> None:
    unknown = _dispatcher(tmp_path, {"unknown.lyf": "unknown value\n"})
    with pytest.raises(V6FunctionSyntaxError, match="unsupported"):
        await unknown.dispatch(FunctionCall("unknown", {}))

    recursive = _dispatcher(tmp_path, {"loop.lyf": "function loop\n"})
    with pytest.raises(FunctionRecursionError, match="loop -> loop"):
        await recursive.dispatch(FunctionCall("loop", {}))


@pytest.mark.asyncio
async def test_v6_executor_end_cancels_pending_background_work(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path, {"end.lyf": "nohup sleep 60\nend\n"})

    await asyncio.wait_for(dispatcher.dispatch(FunctionCall("end", {})), timeout=1)


@pytest.mark.asyncio
async def test_v6_executor_reloads_function_source_with_a_new_dispatcher(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path, {"cached.lyf": "api record value=1\n"})
    capabilities = Capabilities()

    await dispatcher.dispatch(FunctionCall("cached", {}, capabilities=capabilities))
    (tmp_path / "resources" / "legacy" / "functions" / "cached.lyf").write_text(
        "api record value=2\n",
        encoding="utf-8",
    )
    await dispatcher.dispatch(FunctionCall("cached", {}, capabilities=capabilities))
    reloaded = _dispatcher(tmp_path, {"cached.lyf": "api record value=2\n"})
    await reloaded.dispatch(FunctionCall("cached", {}, capabilities=capabilities))

    assert capabilities.apis == [
        ("record", {"value": 1}),
        ("record", {"value": 1}),
        ("record", {"value": 2}),
    ]


@pytest.mark.asyncio
async def test_v6_executor_shutdown_cancels_unawaited_background_work(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path, {"background.lyf": "nohup sleep 60\n"})

    await dispatcher.dispatch(FunctionCall("background", {}))
    await asyncio.sleep(0)

    assert dispatcher.background_task_count == 1
    await dispatcher.aclose()
    assert dispatcher.background_task_count == 0
    with pytest.raises(FunctionError, match="closed"):
        await dispatcher.dispatch(FunctionCall("background", {}))
