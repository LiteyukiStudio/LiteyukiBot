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
from pathlib import Path
from typing import Any, cast

from liteyukibot.app import LiteyukiApp
from liteyukibot.config import AppSettings, CoreSettings, LoggingSettings
from liteyukibot.events import ConversationRef, EventBus, EventEnvelope


async def benchmark(event_count: int) -> dict[str, Any]:
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
    return {
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
    parser.add_argument("--output", type=Path, default=Path("benchmark.json"))
    args = parser.parse_args()
    if args.events < 100:
        parser.error("--events must be at least 100")
    result = asyncio.run(benchmark(args.events))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
