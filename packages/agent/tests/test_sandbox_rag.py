from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from liteyukibot_agent.catalog import SandboxToolDefinition
from liteyukibot_agent.rag import RagIndex, RagSettings, RetrievedChunk
from liteyukibot_agent.sandbox import (
    SANDBOX_COMMAND_EXEC,
    SANDBOX_FILE_READ,
    SANDBOX_FILE_WRITE,
    SandboxPolicy,
    builtin_command_exec,
    builtin_file_read,
    builtin_http_fetch,
    builtin_sandbox_tools,
    execute_in_fresh_worker,
)


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        values = tuple(texts)
        self.calls.append(values)
        return tuple((1.0, 0.0) if "alpha" in text.casefold() else (0.0, 1.0) for text in values)


def _settings(tmp_path: Path, *, citations: bool = False, **overrides: object) -> RagSettings:
    documents = tmp_path / "documents"
    documents.mkdir(exist_ok=True)
    options: dict[str, object] = {
        "rag_paths": [str(documents)],
        "rag_index_path": str(tmp_path / "rag.sqlite3"),
        "rag_embedding_api_key": "test-key",
        "rag_chunk_size": 64,
        "rag_chunk_overlap": 0,
        "rag_top_k": 2,
        "rag_context_chars": 256,
        "rag_citations": citations,
    }
    options.update(overrides)
    settings = RagSettings.from_options(options, default_directory=tmp_path)
    assert settings is not None
    return settings


@pytest.mark.asyncio
async def test_rag_incrementally_updates_and_removes_documents(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    first = documents / "first.txt"
    second = documents / "second.txt"
    first.write_text("alpha document", encoding="utf-8")
    second.write_text("beta document", encoding="utf-8")
    provider = FakeEmbeddings()
    index = RagIndex(_settings(tmp_path), provider)
    try:
        assert await index.sync() == ()
        initial_calls = len(provider.calls)
        assert await index.sync() == ()
        assert len(provider.calls) == initial_calls
        first.write_text("alpha document changed", encoding="utf-8")
        assert await index.sync() == ()
        assert len(provider.calls) == initial_calls + 1
        second.unlink()
        await index.sync()
        context = await index.retrieve("alpha")
        assert "root-0/first.txt" in context.text
        assert "root-0/second.txt" not in context.text
        assert context.citations == ()
    finally:
        index.close()


@pytest.mark.asyncio
async def test_rag_supports_rerank_context_cap_and_citations(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "first.txt").write_text("alpha " * 80, encoding="utf-8")
    (documents / "second.txt").write_text("alpha second", encoding="utf-8")
    provider = FakeEmbeddings()
    index = RagIndex(_settings(tmp_path, citations=True, rag_context_chars=256), provider)

    class ReverseReranker:
        def rerank(self, _query: str, candidates: Sequence[RetrievedChunk]) -> Sequence[RetrievedChunk]:
            return tuple(reversed(candidates)) + tuple(reversed(candidates))

    reranked = RagIndex(index.settings, provider, reranker=ReverseReranker())
    try:
        await index.sync()
        context = await reranked.retrieve("alpha")
        assert len(context.citations) <= 2
        assert all("root-0/" in citation and str(tmp_path) not in citation for citation in context.citations)
        assert len(context.text) <= index.settings.context_chars
    finally:
        reranked.close()
        index.close()


@pytest.mark.asyncio
async def test_rag_does_not_duplicate_overlapping_roots(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "one.txt").write_text("alpha", encoding="utf-8")
    provider = FakeEmbeddings()
    settings = _settings(
        tmp_path,
        rag_paths=[str(documents), str(documents)],
        rag_index_path=str(tmp_path / "duplicate.sqlite3"),
    )
    index = RagIndex(settings, provider)
    try:
        await index.sync()
        assert len(provider.calls) == 1
        context = await index.retrieve("alpha")
        assert context.text.count("one.txt") == 1
    finally:
        index.close()


def test_sandbox_builtin_policy_rejects_escape_and_command_not_on_allowlist(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "inside.txt").write_text("ok", encoding="utf-8")
    policy = SandboxPolicy.from_options(
        {
            "file_roots": [str(root)],
            "command_allowlist": [sys.executable],
            "max_file_bytes": 32,
        },
        default_root=root,
    )
    result, error = builtin_file_read({"path": "../outside.txt"}, policy.wire())
    assert result is None
    assert error == "SANDBOX_PATH_DENIED"
    result, error = builtin_command_exec({"command": ["not-allowlisted"]}, policy.wire())
    assert result is None
    assert error == "SANDBOX_COMMAND_DENIED"
    result, error = builtin_http_fetch({"url": "http://example.com"}, policy.wire())
    assert result is None
    assert error == "SANDBOX_NETWORK_DENIED"
    result, error = builtin_http_fetch({"url": "https://127.0.0.1/"}, policy.wire())
    assert result is None
    assert error == "SANDBOX_NETWORK_DENIED"
    output, error = builtin_command_exec(
        {"command": [sys.executable, "-c", "print('x' * 100)"]},
        {**policy.wire(), "max_output_bytes": 16},
    )
    assert error is None
    assert isinstance(output, dict)
    assert output["truncated"] is True

    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = root / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pass
    else:
        result, error = builtin_file_read({"path": "link.txt"}, policy.wire())
        assert result is None
        assert error == "SANDBOX_PATH_DENIED"


@pytest.mark.asyncio
async def test_sandbox_uses_fresh_worker_and_maps_timeout_and_crash(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    policy = SandboxPolicy.from_options(
        {
            "file_roots": [str(root)],
            "work_directory": str(tmp_path / "work"),
            "command_allowlist": [sys.executable],
            "wall_timeout_seconds": 2.0,
        },
        default_root=root,
    )
    file_tool = next(tool for tool in builtin_sandbox_tools() if tool.descriptor.id == SANDBOX_FILE_READ)
    write_result = await execute_in_fresh_worker(
        next(tool for tool in builtin_sandbox_tools() if tool.descriptor.id == SANDBOX_FILE_WRITE),
        {"path": "worker.txt", "content": "worker"},
        policy,
    )
    assert write_result.success is True
    read_result = await execute_in_fresh_worker(file_tool, {"path": "worker.txt"}, policy)
    assert read_result.success is True
    assert isinstance(read_result.result, dict)
    assert read_result.result["content"] == "worker"

    command_tool = next(tool for tool in builtin_sandbox_tools() if tool.descriptor.id == SANDBOX_COMMAND_EXEC)
    timeout = await execute_in_fresh_worker(
        command_tool,
        {"command": (sys.executable, "-c", "import time; time.sleep(5)")},
        policy,
    )
    assert timeout.success is False
    assert timeout.error_code == "SANDBOX_TIMEOUT"
    crashed = await execute_in_fresh_worker(
        SandboxToolDefinition(command_tool.descriptor, "operator:itemgetter"),
        {},
        policy,
    )
    assert crashed.success is False
    assert crashed.error_code == "SANDBOX_PROTOCOL_INVALID"

    cancelled_task = asyncio.create_task(
        execute_in_fresh_worker(
            command_tool,
            {"command": (sys.executable, "-c", "import time; time.sleep(5)")},
            policy,
        )
    )
    await asyncio.sleep(0.1)
    cancelled_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_task


@pytest.mark.asyncio
async def test_sandbox_maps_worker_nonzero_exit_to_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CrashedProcess:
        returncode = 17

        async def communicate(self, _request: bytes) -> tuple[bytes, bytes]:
            return b"", b""

        async def wait(self) -> None:
            return None

        def kill(self) -> None:
            return None

    async def fake_create_process(*_args: object, **_kwargs: object) -> CrashedProcess:
        return CrashedProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_process)
    policy = SandboxPolicy.from_options({"file_roots": [str(tmp_path)]}, default_root=tmp_path)
    tool = next(tool for tool in builtin_sandbox_tools() if tool.descriptor.id == SANDBOX_FILE_READ)
    result = await execute_in_fresh_worker(tool, {"path": "missing.txt"}, policy)
    assert result.success is False
    assert result.error_code == "SANDBOX_CRASH"
