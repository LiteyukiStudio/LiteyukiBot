from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from liteyukibot.features.permissions import Principal
from liteyukibot.features.profile_service import SQLiteProfileService
from liteyukibot.features.resources_models import ResourceField


@pytest.mark.asyncio
async def test_profile_close_waits_for_a_cancelled_database_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SQLiteProfileService(tmp_path / "profile.sqlite3")
    await service.start()
    started = threading.Event()
    release = threading.Event()
    original = service._set_locked

    def blocked(principal: Principal, field_name: str, value: str) -> None:
        started.set()
        if not release.wait(timeout=2):
            raise TimeoutError("test database worker was not released")
        original(principal, field_name, value)

    monkeypatch.setattr(service, "_set_locked", blocked)
    operation = asyncio.create_task(
        service.set(
            Principal("runtime", "bot", "actor"),
            ResourceField("nickname", str),
            "Alice",
        )
    )
    assert await asyncio.to_thread(started.wait, 1)
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation

    closing = asyncio.create_task(service.close())
    await asyncio.sleep(0.05)
    assert not closing.done()
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert service._database_tasks
    release.set()
    await asyncio.sleep(0.05)
    assert not service._database_tasks
    await service.close()
