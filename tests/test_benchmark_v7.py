from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from scripts import benchmark_v7


def _sample(*, startup_ms: float = 1.0, throughput: float = 100.0) -> dict[str, Any]:
    return {
        "schema": 2,
        "platform": "test-platform",
        "python": "3.14.0",
        "event_count": 100,
        "startup_ms": startup_ms,
        "peak_rss_bytes": 1_000,
        "workloads": {
            "independent": {
                "1": {
                    "kind": "independent",
                    "event_count": 100,
                    "submission_concurrency": 1,
                    "elapsed_ms": 1.0,
                    "throughput_events_per_second": throughput,
                    "latency_ms": {"median": 0.1, "p95": 0.2},
                    "processed_events": 100,
                    "successful_actions": 0,
                }
            },
            "fifo": {
                "kind": "fifo",
                "event_count": 100,
                "submission_concurrency": 100,
                "elapsed_ms": 1.0,
                "throughput_events_per_second": throughput,
                "latency_ms": {"median": 0.1, "p95": 0.2},
                "processed_events": 100,
                "successful_actions": 0,
            },
            "action": {
                "kind": "action",
                "event_count": 100,
                "submission_concurrency": 100,
                "elapsed_ms": 1.0,
                "throughput_events_per_second": throughput,
                "latency_ms": {"median": 0.1, "p95": 0.2},
                "processed_events": 100,
                "successful_actions": 100,
            },
        },
        "functions": {"available": False, "reason": "disabled"},
    }


def test_benchmark_sample_covers_all_event_workloads() -> None:
    result = asyncio.run(
        benchmark_v7.benchmark_sample(
            100,
            function_packs=1,
            functions_per_pack=1,
            function_calls=0,
        )
    )

    assert result["schema"] == 2
    assert result["event_count"] == 100
    independent = result["workloads"]["independent"]
    assert set(independent) == {"1", "10", "100"}
    assert all(value["processed_events"] == 100 for value in independent.values())
    assert result["workloads"]["fifo"]["processed_events"] == 100
    assert result["workloads"]["fifo"]["successful_actions"] == 0
    assert result["workloads"]["action"]["successful_actions"] == 100
    assert result["functions"] == {"available": False, "reason": "disabled"}


def test_function_benchmark_reports_missing_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.benchmark_v7.FunctionDispatcher.discover_executors", lambda: {})

    assert asyncio.run(benchmark_v7._benchmark_functions(packs=1, functions_per_pack=1, calls=1)) == {
        "available": False,
        "reason": "no function executor is installed",
    }


def test_function_benchmark_resources_include_integrity_manifests(tmp_path: Path) -> None:
    benchmark_v7._write_function_resources(tmp_path, packs=2, functions_per_pack=1)

    for name in ("pack-0", "pack-1"):
        assert (tmp_path / "resources" / name / "manifest-v1.json").is_file()


def test_latency_summary_uses_ceil_rank_for_p95() -> None:
    assert benchmark_v7._latency_summary([1.0, 2.0, 3.0, 4.0, 100.0]) == {"median": 3.0, "p95": 100.0}


def test_aggregate_samples_retains_raw_samples_and_distribution() -> None:
    result = benchmark_v7.aggregate_samples(
        [
            _sample(startup_ms=1.0, throughput=100.0),
            _sample(startup_ms=2.0, throughput=200.0),
            _sample(startup_ms=3.0, throughput=300.0),
        ]
    )

    assert result["sample_count"] == 3
    assert len(result["samples"]) == 3
    assert result["schema"] == 2
    assert "schema" not in result["summary"]
    assert result["summary"]["startup_ms"] == {"mean": 2.0, "stdev": 1.0, "min": 1.0, "max": 3.0}
    assert result["summary"]["workloads"]["action"]["throughput_events_per_second"] == {
        "mean": 200.0,
        "stdev": 100.0,
        "min": 100.0,
        "max": 300.0,
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda sample: sample.__setitem__("schema", 1),
        lambda sample: sample.__setitem__("platform", "other"),
        lambda sample: sample["workloads"].pop("action"),
        lambda sample: sample.__setitem__("functions", {"available": True}),
    ],
)
def test_aggregate_samples_rejects_incompatible_samples(mutate: Any) -> None:
    first = _sample()
    second = _sample()
    mutate(second)

    with pytest.raises(ValueError, match="benchmark sample"):
        benchmark_v7.aggregate_samples([first, second])


def test_run_samples_uses_one_child_process_per_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(_sample()))

    monkeypatch.setattr("scripts.benchmark_v7.subprocess.run", fake_run)

    result = benchmark_v7.run_samples(
        samples=3,
        event_count=100,
        function_packs=1,
        functions_per_pack=1,
        function_calls=0,
    )

    assert len(calls) == 3
    assert all("--sample" in command for command in calls)
    assert result["sample_count"] == 3


def test_main_writes_aggregated_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "benchmark.json"
    monkeypatch.setattr(benchmark_v7, "run_samples", lambda **_kwargs: benchmark_v7.aggregate_samples([_sample()]))

    assert (
        benchmark_v7.main(["--events", "100", "--samples", "1", "--function-calls", "0", "--output", str(output)]) == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["startup_ms"]["mean"] == 1.0


@pytest.mark.parametrize(
    "arguments, message",
    [
        (["--events", "99"], "--events must be at least 100"),
        (["--samples", "0"], "--samples must be at least 1"),
        (["--function-calls", "-1"], "function benchmark counts"),
    ],
)
def test_main_rejects_invalid_arguments(arguments: list[str], message: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        benchmark_v7.main(arguments)

    assert message in capsys.readouterr().err


def test_windows_peak_rss_reports_api_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class Psapi:
        @staticmethod
        def GetProcessMemoryInfo(*_args: object) -> int:
            return 0

    class Kernel32:
        @staticmethod
        def GetCurrentProcess() -> int:
            return 1

    class Windows:
        psapi = Psapi()
        kernel32 = Kernel32()

    monkeypatch.setattr("scripts.benchmark_v7.ctypes.windll", Windows(), raising=False)

    with pytest.raises(OSError, match="GetProcessMemoryInfo"):
        benchmark_v7._windows_peak_rss()


@pytest.mark.parametrize(
    ("system", "raw_rss", "expected"),
    [("Linux", 5, 5 * 1024), ("Darwin", 5, 5)],
)
def test_posix_peak_rss_normalizes_platform_units(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    raw_rss: int,
    expected: int,
) -> None:
    class Resource:
        RUSAGE_SELF = object()

        @staticmethod
        def getrusage(_target: object) -> object:
            return type("Usage", (), {"ru_maxrss": raw_rss})()

    monkeypatch.setattr("scripts.benchmark_v7.os.name", "posix")
    monkeypatch.setattr("scripts.benchmark_v7.platform.system", lambda: system)
    monkeypatch.setattr("scripts.benchmark_v7.importlib.import_module", lambda _name: Resource())

    assert benchmark_v7._peak_rss_bytes() == expected
