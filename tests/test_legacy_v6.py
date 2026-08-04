from __future__ import annotations

from pathlib import Path

import pytest

from liteyuki import LiteyukiBot, get_bot, get_config
from liteyuki.bot import _emit_lifecycle, _install_runtime, _reset_runtime
from liteyukibot.exceptions import LegacyUnsupportedError
from liteyukibot.runtime import RuntimeSpec, RuntimeSupervisor

from .test_runtime_v7 import FakeLogger


def test_legacy_context_and_unsupported_nested_host() -> None:
    calls: list[str] = []
    _install_runtime({"name": "legacy"}, lambda name: calls.append(name or "all"))
    try:
        bot = get_bot()

        @bot.on_before_start
        async def before_start() -> None:
            calls.append("before")

        assert get_config("name") == "legacy"
        bot.restart_process("worker")
        import asyncio

        asyncio.run(_emit_lifecycle("before_start"))
        assert calls == ["worker", "before"]
        with pytest.raises(LegacyUnsupportedError, match="nested"):
            LiteyukiBot()
    finally:
        _reset_runtime()


def test_unsupported_v6_modules_raise_migration_error() -> None:
    with pytest.raises(LegacyUnsupportedError, match="session.Session"):
        from liteyuki.session import Session  # noqa: F401

    with pytest.raises(LegacyUnsupportedError, match="comm.channel.get_channel"):
        from liteyuki.comm.channel import get_channel  # noqa: F401


@pytest.mark.asyncio
async def test_v6_runtime_loads_plugin_and_runs_lifecycle(tmp_path: Path) -> None:
    plugin = tmp_path / "legacy_fixture.py"
    plugin.write_text(
        """
from pathlib import Path
from liteyuki import PluginMetadata, get_bot

__plugin_meta__ = PluginMetadata(name="Legacy Fixture")
bot = get_bot()

@bot.on_before_start
async def before_start():
    Path("started.txt").write_text("started", encoding="utf-8")

@bot.on_after_shutdown
async def after_shutdown():
    Path("stopped.txt").write_text("stopped", encoding="utf-8")
""".lstrip(),
        encoding="utf-8",
    )
    supervisor = RuntimeSupervisor(logger=FakeLogger())
    supervisor.add(
        RuntimeSpec(
            id="legacy",
            kind="v6",
            options={"config": {"answer": 42}, "plugins": ["legacy_fixture"]},
            working_directory=tmp_path,
            ready_timeout=5,
            heartbeat_interval=0.05,
            stale_after=1,
        )
    )

    await supervisor.start()
    assert (tmp_path / "started.txt").read_text(encoding="utf-8") == "started"
    await supervisor.stop()
    assert (tmp_path / "stopped.txt").read_text(encoding="utf-8") == "stopped"
