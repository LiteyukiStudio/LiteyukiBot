"""Repeatable v7 benchmark workloads with independently sampled aggregation."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import importlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Awaitable, Callable, Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any, Literal, cast

from liteyukibot.app import LiteyukiApp
from liteyukibot.config import AppSettings, CordisSettings, CoreSettings, LoggingSettings, PluginSettings
from liteyukibot.events import (
    ActionEnvelope,
    ActionResult,
    CallApi,
    ConversationRef,
    EventBus,
    EventEnvelope,
    HandlerResult,
)
from liteyukibot.functions import FunctionCall, FunctionDispatcher
from liteyukibot.resource_packs import ResourceCatalog, write_resource_manifest

SCHEMA_VERSION = 2
DEFAULT_EVENT_COUNT = 5_000
DEFAULT_FUNCTION_PACKS = 8
DEFAULT_FUNCTIONS_PER_PACK = 16
DEFAULT_FUNCTION_CALLS = 1_000
DEFAULT_SAMPLES = 3

type WorkloadKind = Literal["independent", "fifo", "action"]
type BenchmarkProfile = Literal["bare", "installed-first-party"]

_NATIVE_PLUGIN_ENTRY_POINT_GROUP = "liteyukibot.plugins"
_CORDIS_PLUGIN_ENTRY_POINT_GROUP = "liteyukibot.cordis_plugins"
_CORDIS_HOST_ENTRY_POINT_GROUP = "liteyukibot.cordis_hosts"
_BENCHMARK_PROFILES: tuple[BenchmarkProfile, ...] = ("bare", "installed-first-party")


def discover_installed_first_party_manifest() -> tuple[dict[str, Any], ...]:
    """Return a deterministic, import-free extension snapshot for installed packages."""

    installed = tuple(metadata.distributions())
    cordis_host_count = sum(
        1
        for distribution in installed
        if _is_first_party_distribution(str(distribution.metadata.get("Name", "")))
        for entry_point in distribution.entry_points
        if entry_point.group == _CORDIS_HOST_ENTRY_POINT_GROUP
    )
    cordis_plugins_enabled = cordis_host_count == 1
    distributions: list[dict[str, Any]] = []
    for distribution in installed:
        name = distribution.metadata.get("Name")
        if not isinstance(name, str) or not _is_first_party_distribution(name):
            continue
        extensions = [
            {
                "host": "native" if entry_point.group == _NATIVE_PLUGIN_ENTRY_POINT_GROUP else "cordis",
                "id": entry_point.name,
                "enabled": entry_point.group == _NATIVE_PLUGIN_ENTRY_POINT_GROUP or cordis_plugins_enabled,
            }
            for entry_point in distribution.entry_points
            if entry_point.group in {_NATIVE_PLUGIN_ENTRY_POINT_GROUP, _CORDIS_PLUGIN_ENTRY_POINT_GROUP}
        ]
        extensions.sort(key=lambda item: (str(item["host"]), str(item["id"])))
        distributions.append(
            {
                "distribution": name,
                "version": distribution.version,
                "extensions": extensions,
            }
        )
    distributions.sort(key=_manifest_sort_key)
    return tuple(distributions)


def _is_first_party_distribution(name: str) -> bool:
    normalized = "".join("-" if character in "_." else character.lower() for character in name)
    return normalized == "liteyukibot-v7" or normalized.startswith("liteyukibot-v7-")


def _validate_profile(profile: str) -> BenchmarkProfile:
    if profile not in _BENCHMARK_PROFILES:
        raise ValueError(f"unsupported benchmark profile {profile!r}")
    return profile


def _serialize_extension_manifest(manifest: Sequence[Mapping[str, Any]]) -> str:
    return json.dumps(manifest, separators=(",", ":"), sort_keys=True)


def _parse_extension_manifest(value: str) -> tuple[dict[str, Any], ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("--extension-manifest must be valid JSON") from error
    if not isinstance(parsed, list):
        raise ValueError("--extension-manifest must be a JSON array")
    if parsed != sorted(parsed, key=_manifest_sort_key):
        raise ValueError("--extension-manifest must use stable distribution ordering")

    manifest: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("--extension-manifest entries must be objects")
        distribution = item.get("distribution")
        version = item.get("version")
        extensions = item.get("extensions")
        if not isinstance(distribution, str) or not isinstance(version, str) or not isinstance(extensions, list):
            raise ValueError("--extension-manifest entries require distribution, version, and extensions")
        normalized_extensions: list[dict[str, Any]] = []
        for extension in extensions:
            if not isinstance(extension, dict):
                raise ValueError("--extension-manifest extensions must be objects")
            host = extension.get("host")
            extension_id = extension.get("id")
            enabled = extension.get("enabled")
            if host not in {"native", "cordis"} or not isinstance(extension_id, str) or not isinstance(enabled, bool):
                raise ValueError("--extension-manifest extensions require host, id, and enabled")
            normalized_extensions.append({"host": host, "id": extension_id, "enabled": enabled})
        ordered_extensions = sorted(
            extensions,
            key=lambda extension: (str(extension.get("host")), str(extension.get("id"))),
        )
        if extensions != ordered_extensions:
            raise ValueError("--extension-manifest extensions must use stable ordering")
        manifest.append({"distribution": distribution, "version": version, "extensions": normalized_extensions})
    return tuple(manifest)


def _manifest_sort_key(item: object) -> tuple[str, str, str]:
    if not isinstance(item, Mapping):
        return ("", "", "")
    distribution = str(item.get("distribution", ""))
    return (distribution.lower(), str(item.get("version", "")), distribution)


def _resolve_profile_manifest(profile: BenchmarkProfile) -> tuple[dict[str, Any], ...]:
    return () if profile == "bare" else discover_installed_first_party_manifest()


def _settings_for_profile(root: Path, profile: BenchmarkProfile, manifest: Sequence[Mapping[str, Any]]) -> AppSettings:
    native_plugins: list[str] = []
    cordis_plugins: list[str] = []
    if profile == "installed-first-party":
        for distribution in manifest:
            extensions = distribution.get("extensions", [])
            if not isinstance(extensions, list):
                continue
            for extension in extensions:
                if not isinstance(extension, Mapping) or extension.get("enabled") is not True:
                    continue
                extension_id = extension.get("id")
                if not isinstance(extension_id, str):
                    continue
                if extension.get("host") == "native":
                    native_plugins.append(extension_id)
                elif extension.get("host") == "cordis":
                    cordis_plugins.append(extension_id)
    return AppSettings(
        core=CoreSettings(data_dir=root / "data", cache_dir=root / "cache"),
        logging=LoggingSettings(console=False),
        plugins=PluginSettings(enabled=tuple(sorted(set(native_plugins)))),
        cordis=CordisSettings(enabled=tuple(sorted(set(cordis_plugins)))),
    )


async def benchmark_sample(
    event_count: int,
    *,
    function_packs: int,
    functions_per_pack: int,
    function_calls: int,
    profile: BenchmarkProfile = "bare",
    extension_manifest: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Collect one isolated-process sample without spawning a child process."""

    profile = _validate_profile(profile)
    manifest = tuple(extension_manifest)
    if profile == "bare" and manifest:
        raise ValueError("bare benchmark profile must not have an extension manifest")
    if manifest:
        manifest = _parse_extension_manifest(_serialize_extension_manifest(manifest))
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        app = LiteyukiApp(_settings_for_profile(root, profile, manifest))
        await app.start()
        startup_ms = (time.perf_counter() - started) * 1000
        try:
            workloads = {
                "independent": {
                    str(concurrency): await _benchmark_event_workload(
                        event_count,
                        kind="independent",
                        submission_concurrency=concurrency,
                    )
                    for concurrency in (1, 10, 100)
                },
                "fifo": await _benchmark_event_workload(
                    event_count,
                    kind="fifo",
                    submission_concurrency=100,
                ),
                "action": await _benchmark_event_workload(
                    event_count,
                    kind="action",
                    submission_concurrency=100,
                ),
            }
        finally:
            await app.stop()

    return {
        "schema": SCHEMA_VERSION,
        "profile": profile,
        "extension_manifest": list(manifest),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "event_count": event_count,
        "startup_ms": startup_ms,
        "peak_rss_bytes": _peak_rss_bytes(),
        "workloads": workloads,
        "functions": await _benchmark_functions(
            packs=function_packs,
            functions_per_pack=functions_per_pack,
            calls=function_calls,
        ),
    }


async def _benchmark_event_workload(
    event_count: int,
    *,
    kind: WorkloadKind,
    submission_concurrency: int,
) -> dict[str, Any]:
    latencies: list[float] = []
    processed = 0
    fifo_order: list[int] = []
    actions_succeeded = 0

    async def handle(event: EventEnvelope) -> HandlerResult | None:
        nonlocal processed
        processed += 1
        if kind == "fifo":
            fifo_order.append(int(event.id))
        if kind == "action":
            return HandlerResult(
                actions=(
                    ActionEnvelope(
                        action_id=f"action-{event.id}",
                        event_id=event.id,
                        runtime_id=event.runtime_id,
                        bot_id=event.bot_id,
                        action=CallApi(api="benchmark"),
                    ),
                )
            )
        return None

    async def execute(_event: EventEnvelope, action: ActionEnvelope) -> ActionResult:
        nonlocal actions_succeeded
        actions_succeeded += 1
        return ActionResult(action_id=action.action_id, success=True)

    async def publish(bus: EventBus, index: int) -> None:
        started = time.perf_counter()
        conversation_id = "fifo" if kind == "fifo" else f"conversation-{index}"
        result = await bus.publish(
            EventEnvelope(
                id=str(index),
                runtime_id="benchmark",
                adapter="benchmark",
                bot_id="bot",
                type="benchmark",
                conversation=ConversationRef(id=conversation_id),
            )
        )
        if result.status != "processed":
            raise RuntimeError(f"benchmark event {index} was not processed: {result.status}")
        if kind == "action" and len(result.action_results) != 1:
            raise RuntimeError(f"benchmark action {index} was not executed")
        latencies.append((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    async with EventBus(max_concurrent_events=100, action_executor=execute if kind == "action" else None) as bus:
        bus.subscribe(handle)
        for offset in range(0, event_count, submission_concurrency):
            await asyncio.gather(
                *(publish(bus, index) for index in range(offset, min(offset + submission_concurrency, event_count)))
            )
    elapsed_seconds = time.perf_counter() - started
    if kind == "fifo" and fifo_order != list(range(event_count)):
        raise RuntimeError("FIFO benchmark did not preserve event order")
    if processed != event_count:
        raise RuntimeError(f"benchmark handled {processed} events, expected {event_count}")
    if kind == "action" and actions_succeeded != event_count:
        raise RuntimeError(f"benchmark executed {actions_succeeded} actions, expected {event_count}")
    return {
        "kind": kind,
        "event_count": event_count,
        "submission_concurrency": submission_concurrency,
        "elapsed_ms": elapsed_seconds * 1000,
        "throughput_events_per_second": event_count / elapsed_seconds,
        "latency_ms": _latency_summary(latencies),
        "processed_events": processed,
        "successful_actions": actions_succeeded,
    }


def _latency_summary(latencies: Sequence[float]) -> dict[str, float]:
    if not latencies:
        raise ValueError("latency samples must not be empty")
    ordered = sorted(latencies)
    return {
        "median": statistics.median(ordered),
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
    }


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

    return {
        "available": True,
        "packs": packs,
        "functions_per_pack": functions_per_pack,
        "calls": calls,
        "catalog_setup_ms": cold_setup_ms,
        "catalog_setup_tracemalloc_peak_bytes": cold_setup_peak,
        "first_call_ms": first_call_ms,
        "first_call_tracemalloc_peak_bytes": first_call_peak,
        "hot_call_ms": {**_latency_summary(hot_latencies), "tracemalloc_peak_bytes": hot_peak},
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
        write_resource_manifest(pack)
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")


def aggregate_samples(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ValueError("benchmark samples must not be empty")
    _validate_samples(samples)
    return {
        "schema": SCHEMA_VERSION,
        "sample_count": len(samples),
        "profile": samples[0]["profile"],
        "extension_manifest": samples[0]["extension_manifest"],
        "platform": samples[0]["platform"],
        "python": samples[0]["python"],
        "event_count": samples[0]["event_count"],
        "samples": list(samples),
        "summary": _aggregate_value(
            [
                {
                    "startup_ms": sample["startup_ms"],
                    "peak_rss_bytes": sample["peak_rss_bytes"],
                    "workloads": sample["workloads"],
                    "functions": sample["functions"],
                }
                for sample in samples
            ]
        ),
    }


def _validate_samples(samples: Sequence[Mapping[str, Any]]) -> None:
    expected = samples[0]
    if expected.get("profile") not in _BENCHMARK_PROFILES or "extension_manifest" not in expected:
        raise ValueError("benchmark samples are missing a valid profile manifest")
    for sample in samples:
        if sample.get("schema") != SCHEMA_VERSION:
            raise ValueError("benchmark sample has an unsupported schema")
        for key in ("platform", "python", "event_count", "profile", "extension_manifest"):
            if sample.get(key) != expected.get(key):
                raise ValueError(f"benchmark samples disagree on {key}")
        if sample.get("workloads", {}).keys() != expected.get("workloads", {}).keys():
            raise ValueError("benchmark samples disagree on workload groups")
        if sample.get("functions", {}).get("available") != expected.get("functions", {}).get("available"):
            raise ValueError("benchmark samples disagree on function executor availability")


def _aggregate_value(values: Sequence[Any]) -> Any:
    first = values[0]
    if isinstance(first, bool) or first is None or isinstance(first, str):
        if any(value != first for value in values[1:]):
            raise ValueError("benchmark samples disagree on a non-numeric value")
        return first
    if isinstance(first, (int, float)):
        numbers = [float(value) for value in values]
        return {
            "mean": statistics.fmean(numbers),
            "stdev": statistics.stdev(numbers) if len(numbers) > 1 else 0.0,
            "min": min(numbers),
            "max": max(numbers),
        }
    if isinstance(first, Mapping):
        keys = first.keys()
        if any(not isinstance(value, Mapping) or value.keys() != keys for value in values[1:]):
            raise ValueError("benchmark samples disagree on object keys")
        return {key: _aggregate_value([value[key] for value in values]) for key in keys}
    raise ValueError(f"benchmark samples contain unsupported value {type(first).__name__}")


def run_samples(
    *,
    samples: int,
    event_count: int,
    function_packs: int,
    functions_per_pack: int,
    function_calls: int,
    profile: BenchmarkProfile = "bare",
) -> dict[str, Any]:
    profile = _validate_profile(profile)
    extension_manifest = _resolve_profile_manifest(profile)
    measurements = [
        _run_child_sample(
            event_count=event_count,
            function_packs=function_packs,
            functions_per_pack=functions_per_pack,
            function_calls=function_calls,
            profile=profile,
            extension_manifest=extension_manifest,
        )
        for _ in range(samples)
    ]
    return aggregate_samples(measurements)


def _run_child_sample(
    *,
    event_count: int,
    function_packs: int,
    functions_per_pack: int,
    function_calls: int,
    profile: BenchmarkProfile = "bare",
    extension_manifest: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    profile = _validate_profile(profile)
    manifest = _parse_extension_manifest(_serialize_extension_manifest(extension_manifest))
    if profile == "bare" and manifest:
        raise ValueError("bare benchmark profile must not have an extension manifest")
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--sample",
        "--events",
        str(event_count),
        "--function-packs",
        str(function_packs),
        "--functions-per-pack",
        str(functions_per_pack),
        "--function-calls",
        str(function_calls),
        "--profile",
        profile,
        "--extension-manifest",
        _serialize_extension_manifest(manifest),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise ValueError("benchmark child did not produce a JSON object")
    return cast(dict[str, Any], parsed)


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=DEFAULT_EVENT_COUNT)
    parser.add_argument("--function-packs", type=int, default=DEFAULT_FUNCTION_PACKS)
    parser.add_argument("--functions-per-pack", type=int, default=DEFAULT_FUNCTIONS_PER_PACK)
    parser.add_argument("--function-calls", type=int, default=DEFAULT_FUNCTION_CALLS)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--profile", choices=_BENCHMARK_PROFILES, default="bare")
    parser.add_argument("--extension-manifest", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--sample", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, default=Path("benchmark.json"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.events < 100:
        _parser().error("--events must be at least 100")
    if args.function_packs < 1 or args.functions_per_pack < 1 or args.function_calls < 0:
        _parser().error("function benchmark counts must be positive, except --function-calls may be zero")
    if args.samples < 1:
        _parser().error("--samples must be at least 1")
    if args.sample:
        profile = _validate_profile(args.profile)
        extension_manifest = (
            _resolve_profile_manifest(profile)
            if args.extension_manifest is None
            else _parse_extension_manifest(args.extension_manifest)
        )
        if profile == "bare" and extension_manifest:
            _parser().error("bare benchmark profile must not have an extension manifest")
        result = asyncio.run(
            benchmark_sample(
                args.events,
                function_packs=args.function_packs,
                functions_per_pack=args.functions_per_pack,
                function_calls=args.function_calls,
                profile=profile,
                extension_manifest=extension_manifest,
            )
        )
        print(json.dumps(result, separators=(",", ":")))
        return 0
    result = run_samples(
        samples=args.samples,
        event_count=args.events,
        function_packs=args.function_packs,
        functions_per_pack=args.functions_per_pack,
        function_calls=args.function_calls,
        profile=_validate_profile(args.profile),
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
