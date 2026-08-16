from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from liteyukibot.app import LiteyukiApp
from liteyukibot.config import AppSettings, CoreSettings, RuntimeSettings
from liteyukibot.logging import Logger
from liteyukibot.plugin_store import PlatformTarget, RuntimeGeneration, RuntimeGenerationStore
from liteyukibot.runtime import RuntimeCatalog, RuntimePlugin


class _Logger:
    def bind(self, **_fields: object) -> _Logger:
        return self


@pytest.mark.skip(reason="legacy child-supervisor runtime generation is not selected by config v5")
def test_app_launches_managed_runtime_from_its_generation_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RuntimeGenerationStore(tmp_path)
    generation = RuntimeGeneration(
        "generation-one",
        "legacy",
        "v6",
        "2026-08-11T00:00:00+00:00",
        PlatformTarget("windows", "amd64", "3.14"),
        ("example.echo",),
        ("a" * 64,),
        {"modules": [], "directories": []},
    )
    path = store.write(generation)
    python = store.python_path(path)
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    store.activate("legacy", generation.id)
    plugin = RuntimePlugin(kind="v6", command=("current-python", "-m", "liteyukibot_runtime_v6"))
    monkeypatch.setattr(RuntimeCatalog, "discover", lambda _self: {"v6": plugin})
    settings = AppSettings(  # type: ignore[call-arg]  # historical child-supervisor configuration
        core=CoreSettings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"),
        runtimes={"legacy": RuntimeSettings(kind="v6")},
    )

    app = LiteyukiApp(settings, logger=cast(Logger, _Logger()), resource_workspace=str(tmp_path))
    spec = app.runtimes.records["legacy"].spec

    assert spec.command == (str(python), "-m", "liteyukibot_runtime_v6")
    assert spec.env["LITEYUKI_RUNTIME_GENERATION_DIR"] == str(path)
