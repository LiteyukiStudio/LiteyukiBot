from __future__ import annotations

import asyncio
import importlib.metadata

import liteyuki
import pytest
from liteyuki import LiteyukiBot, get_bot, get_config
from liteyuki.bot import _emit_lifecycle, _install_runtime, _reset_runtime
from liteyukibot_runtime_v6 import bridge_definition
from liteyukibot_runtime_v6.host import _reject_legacy_options

from liteyukibot.exceptions import LegacyUnsupportedError


def test_v6_compatibility_namespace_uses_kernel_version() -> None:
    assert importlib.metadata.version("liteyukibot-v7") == liteyuki.__version__


def test_v6_bridge_is_experimental_and_not_a_legacy_runtime() -> None:
    definition = bridge_definition()
    assert definition.kind == "v6"
    assert definition.grade.value == "experimental"


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
        asyncio.run(_emit_lifecycle("before_start"))
        assert calls == ["worker", "before"]
        with pytest.raises(LegacyUnsupportedError, match="nested"):
            LiteyukiBot()
    finally:
        _reset_runtime()


def test_unsupported_v6_channel_raises_migration_error() -> None:
    with pytest.raises(LegacyUnsupportedError, match="comm.channel.get_channel"):
        from liteyuki.comm.channel import get_channel  # noqa: F401


def test_v6_bridge_rejects_legacy_runtime_options() -> None:
    with pytest.raises(RuntimeError, match="migration_required"):
        _reject_legacy_options({"plugins": ["legacy.module"]})
    with pytest.raises(RuntimeError, match="migration_required"):
        _reject_legacy_options({"plugin_dirs": ["plugins"]})
