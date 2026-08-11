"""Small repeatable baseline for v7 architecture decisions."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import importlib
import json
import os
import platform
import statistics
import tempfile
import time
import tracemalloc
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from liteyukibot.app import LiteyukiApp
from liteyukibot.config import AppSettings, CoreSettings, LoggingSettings
from liteyukibot.events import ConversationRef, EventBus, EventEnvelope
from liteyukibot.functions import FunctionCall, FunctionDispatcher
from liteyukibot.resource_packs import ResourceCatalog


async def benchmark(
    event_count: int,
    *,
    function_packs: int,
    functions_per_pack: int,
    function_calls: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        app = LiteyukiApp(
            AppSettings(
                core=CoreSettings(data_dir=root / "data", cache_dir=root / "cache"),
                logging=LoggingSettings(console=False),
            )
        )
        await app.start()
        startup_seconds = time.perf_counter() - started

        latencies: list[float] = []

        async def handle(_event: EventEnvelope) -> None:
            return None

        async def timed_publish(bus: EventBus, event: EventEnvelope) -> float:
            event_started = time.perf_counter()
            await bus.publish(event)
            return time.perf_counter() - event_started

        async with EventBus(max_concurrent_events=100) as bus:
            bus.subscribe(handle)
            dispatch_started = time.perf_counter()
            for offset in range(0, event_count, 100):
                batch_size = min(100, event_count - offset)
                latencies.extend(
                    await asyncio.gather(
                        *(
                            timed_publish(
                                bus,
                                EventEnvelope(
                                    runtime_id="benchmark",
                                    adapter="benchmark",
                                    bot_id="bot",
                                    type="benchmark",
                                    conversation=ConversationRef(
                                        id=f"conversation-{offset + index}"
                                    ),
                                ),
                            )
                            for index in range(batch_size)
                        )
                    )
                )
            dispatch_seconds = time.perf_counter() - dispatch_started

        await app.stop()

    sorted_latencies = sorted(latencies)
    result: dict[str, Any] = {
        "schema": 1,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "event_count": event_count,
        "startup_ms": startup_seconds * 1000,
        "throughput_events_per_second": event_count / dispatch_seconds,
        "event_latency_ms": {
            "median": statistics.median(sorted_latencies) * 1000,
            "p95": sorted_latencies[int(len(sorted_latencies) * 0.95) - 1] * 1000,
        },
        "peak_rss_bytes": _peak_rss_bytes(),
    }
    result["functions"] = await _benchmark_functions(
        packs=function_packs,
        functions_per_pack=functions_per_pack,
        calls=function_calls,
    )
    return result


async def _benchmark_functions(*, packs: int, functions_per_pack: int, calls: int) -> dict[str, Any]:
    if calls == 0:
        return {"available": False, "reason": "disabled"}
    if not FunctionDispatcher.discover_executors():
        return {"available": False, "reason": "no function executor is installed"}

    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        _write_function_resources(workspace, packs, functions_per_pack)
        started = time.perf_counter()
        catalog = ResourceCatalog.load(workspace)
        dispatcher = FunctionDispatcher(catalog)
        cold_setup_ms = (time.perf_counter() - started) * 1000

        call = FunctionCall("benchmark-0-0", {})
        started = time.perf_counter()
        await dispatcher.dispatch(call)
        first_call_ms = (time.perf_counter() - started) * 1000

        hot_latencies: list[float] = []
        for _ in range(calls):
            started = time.perf_counter()
            await dispatcher.dispatch(call)
            hot_latencies.append((time.perf_counter() - started) * 1000)

        cold_setup_peak = await _tracemalloc_peak(lambda: _create_dispatcher(workspace))
        first_call_peak = await _tracemalloc_peak(lambda: _dispatch_once(workspace, call))
        hot_peak = await _tracemalloc_peak(lambda: _dispatch_many(workspace, call, calls))

    sorted_hot = sorted(hot_latencies)
    return {
        "available": True,
        "packs": packs,
        "functions_per_pack": functions_per_pack,
        "calls": calls,
        "catalog_setup_ms": cold_setup_ms,
        "catalog_setup_tracemalloc_peak_bytes": cold_setup_peak,
        "first_call_ms": first_call_ms,
        "first_call_tracemalloc_peak_bytes": first_call_peak,
        "hot_call_ms": {
            "median": statistics.median(sorted_hot),
            "p95": sorted_hot[int(len(sorted_hot) * 0.95) - 1],
            "tracemalloc_peak_bytes": hot_peak,
        },
    }


async def _create_dispatcher(workspace: Path) -> None:
    FunctionDispatcher(ResourceCatalog.load(workspace))


async def _dispatch_once(workspace: Path, call: FunctionCall) -> None:
    await FunctionDispatcher(ResourceCatalog.load(workspace)).dispatch(call)


async def _dispatch_many(workspace: Path, call: FunctionCall, calls: int) -> None:
    dispatcher = FunctionDispatcher(ResourceCatalog.load(workspace))
    for _ in range(calls):
        await dispatcher.dispatch(call)


async def _tracemalloc_peak(operation: Callable[[], Awaitable[None]]) -> int:
    tracemalloc.start()
    try:
        await operation()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _write_function_resources(workspace: Path, packs: int, functions_per_pack: int) -> None:
    root = workspace / "resources"
    index: list[str] = []
    for pack_index in range(packs):
        name = f"pack-{pack_index}"
        index.append(name)
        pack = root / name
        functions = pack / "functions"
        functions.mkdir(parents=True)
        (pack / "metadata.yml").write_text(
            f'id: {name}\nname: {name}\nversion: "1"\n',
            encoding="utf-8",
        )
        for function_index in range(functions_per_pack):
            (functions / f"benchmark-{pack_index}-{function_index}.lyf").write_text(
                "var value=1\nvar rendered=${value}\n",
                encoding="utf-8",
            )
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")


def _peak_rss_bytes() -> int:
    if os.name == "nt":
        return _windows_peak_rss()
    resource = cast(Any, importlib.import_module("resource"))
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if platform.system() == "Darwin" else value * 1024


def _windows_peak_rss() -> int:
    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("page_fault_count", ctypes.c_ulong),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    windows = cast(Any, ctypes).windll
    windows.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    windows.psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    windows.psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = windows.kernel32.GetCurrentProcess()
    if not windows.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return int(counters.peak_working_set_size)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=5000)
    parser.add_argument("--function-packs", type=int, default=8)
    parser.add_argument("--functions-per-pack", type=int, default=16)
    parser.add_argument("--function-calls", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=Path("benchmark.json"))
    args = parser.parse_args()
    if args.events < 100:
        parser.error("--events must be at least 100")
    if args.function_packs < 1 or args.functions_per_pack < 1 or args.function_calls < 0:
        parser.error("function benchmark counts must be positive, except --function-calls may be zero")
    result = asyncio.run(
        benchmark(
            args.events,
            function_packs=args.function_packs,
            functions_per_pack=args.functions_per_pack,
            function_calls=args.function_calls,
        )
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
