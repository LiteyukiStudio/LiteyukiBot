"""Repeatable v7 benchmark workloads with independently sampled aggregation."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import gc
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

import psutil

from liteyukibot.app import LiteyukiApp
from liteyukibot.broker import BridgeAccess, BridgeManifest, BridgeSession, BrokerLedger, EventIngress
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
DEFAULT_RESIDENT_EVENTS = 20_000
DEFAULT_RESIDENT_PAYLOAD_BYTES = 1_024
RESIDENT_TERMINAL_CAPACITY = 4_096

type WorkloadKind = Literal["independent", "fifo", "action"]
type BenchmarkProfile = Literal["bare", "installed-first-party"]

_NATIVE_PLUGIN_ENTRY_POINT_GROUP = "liteyukibot.plugins"
_CORDIS_PLUGIN_ENTRY_POINT_GROUP = "liteyukibot.cordis_plugins"
_CORDIS_HOST_ENTRY_POINT_GROUP = "liteyukibot.cordis_hosts"
_BENCHMARK_PROFILES: tuple[BenchmarkProfile, ...] = ("bare", "installed-first-party")


def discover_installed_first_party_manifest() -> tuple[dict[str, Any], ...]:
    """Return a deterministic, import-free extension snapshot for installed packages.

    Returns:
        The `tuple[dict[str, Any], ...]` result produced by the operation.
    """

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
        extension_entries = [
            entry_point
            for entry_point in distribution.entry_points
            if entry_point.group in {_NATIVE_PLUGIN_ENTRY_POINT_GROUP, _CORDIS_PLUGIN_ENTRY_POINT_GROUP}
        ]
        cordis_ids = {
            entry_point.name
            for entry_point in extension_entries
            if entry_point.group == _CORDIS_PLUGIN_ENTRY_POINT_GROUP and cordis_plugins_enabled
        }
        extensions = [
            {
                "host": "native" if entry_point.group == _NATIVE_PLUGIN_ENTRY_POINT_GROUP else "cordis",
                "id": entry_point.name,
                "enabled": (
                    entry_point.name not in cordis_ids
                    if entry_point.group == _NATIVE_PLUGIN_ENTRY_POINT_GROUP
                    else cordis_plugins_enabled
                ),
            }
            for entry_point in extension_entries
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
    """Implement the is first party distribution operation for the component.

    Args:
        name: Stable name used to identify the value.

    Returns:
        Whether the requested condition is satisfied.

    Notes:
        Internal implementation detail for `_is_first_party_distribution`. It delegates to `join`,
        `lower`, `startswith` while keeping intermediate state local to the owning operation.
    """
    normalized = "".join("-" if character in "_." else character.lower() for character in name)
    return normalized == "liteyukibot-v7" or normalized.startswith("liteyukibot-v7-")


def _validate_profile(profile: str) -> BenchmarkProfile:
    """Validate profile.

    Args:
        profile: Named runtime or benchmark profile.

    Returns:
        The `BenchmarkProfile` result produced by the operation.

    Notes:
        Internal implementation detail for `_validate_profile`. It performs the local state transition
        directly and is not a stable extension boundary.
    """
    if profile not in _BENCHMARK_PROFILES:
        raise ValueError(f"unsupported benchmark profile {profile!r}")
    return profile


def _serialize_extension_manifest(manifest: Sequence[Mapping[str, Any]]) -> str:
    """Implement the serialize extension manifest operation for the component.

    Args:
        manifest: Validated manifest describing the component contract.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_serialize_extension_manifest`. It delegates to `dumps`
        while keeping intermediate state local to the owning operation.
    """
    return json.dumps(manifest, separators=(",", ":"), sort_keys=True)


def _parse_extension_manifest(value: str) -> tuple[dict[str, Any], ...]:
    """Parse extension manifest.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `tuple[dict[str, Any], ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_parse_extension_manifest`. It delegates to `loads`,
        `sorted`, `get`, `append` while keeping intermediate state local to the owning operation.
    """
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
    """Implement the manifest sort key operation for the component.

    Args:
        item: The item value used by the operation.

    Returns:
        The `tuple[str, str, str]` result produced by the operation.

    Notes:
        Internal implementation detail for `_manifest_sort_key`. It delegates to `get`, `lower` while
        keeping intermediate state local to the owning operation.
    """
    if not isinstance(item, Mapping):
        return ("", "", "")
    distribution = str(item.get("distribution", ""))
    return (distribution.lower(), str(item.get("version", "")), distribution)


def _resolve_profile_manifest(profile: BenchmarkProfile) -> tuple[dict[str, Any], ...]:
    """Resolve profile manifest.

    Args:
        profile: Named runtime or benchmark profile.

    Returns:
        The `tuple[dict[str, Any], ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_resolve_profile_manifest`. It delegates to
        `discover_installed_first_party_manifest` while keeping intermediate state local to the owning
        operation.
    """
    return () if profile == "bare" else discover_installed_first_party_manifest()


def _settings_for_profile(root: Path, profile: BenchmarkProfile, manifest: Sequence[Mapping[str, Any]]) -> AppSettings:
    """Implement the settings for profile operation for the component.

    Args:
        root: The root value used by the operation.
        profile: Named runtime or benchmark profile.
        manifest: Validated manifest describing the component contract.

    Returns:
        The `AppSettings` result produced by the operation.

    Notes:
        Internal implementation detail for `_settings_for_profile`. It delegates to `get`, `append`,
        `sorted` while keeping intermediate state local to the owning operation.
    """
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
    resident_events: int = DEFAULT_RESIDENT_EVENTS,
    resident_payload_bytes: int = DEFAULT_RESIDENT_PAYLOAD_BYTES,
    profile: BenchmarkProfile = "bare",
    extension_manifest: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Collect one isolated-process sample without spawning a child process.

    Args:
        event_count: The event count value used by the operation.
        function_packs: The function packs value used by the operation.
        functions_per_pack: The functions per pack value used by the operation.
        function_calls: The function calls value used by the operation.
        resident_events: The resident events value used by the operation.
        resident_payload_bytes: Configured resident payload size, in bytes.
        profile: Named runtime or benchmark profile.
        extension_manifest: The extension manifest value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.
    """

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
        "resident_event_count": resident_events,
        "resident_payload_bytes": resident_payload_bytes,
        "startup_ms": startup_ms,
        "peak_rss_bytes": _peak_rss_bytes(),
        "workloads": workloads,
        "functions": await _benchmark_functions(
            packs=function_packs,
            functions_per_pack=functions_per_pack,
            calls=function_calls,
        ),
        "resident": await _benchmark_resident_workloads(
            event_count=resident_events,
            payload_bytes=resident_payload_bytes,
        ),
    }


async def _benchmark_event_workload(
    event_count: int,
    *,
    kind: WorkloadKind,
    submission_concurrency: int,
) -> dict[str, Any]:
    """Implement the benchmark event workload operation for the component.

    Args:
        event_count: The event count value used by the operation.
        kind: The kind value used by the operation.
        submission_concurrency: The submission concurrency value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_benchmark_event_workload`. It delegates to `perf_counter`,
        `subscribe`, `range`, `gather` while keeping intermediate state local to the owning operation.
    """
    latencies: list[float] = []
    processed = 0
    fifo_order: list[int] = []
    actions_succeeded = 0

    async def handle(event: EventEnvelope) -> HandlerResult | None:
        """Handle one request through the benchmark event workload.

        Args:
            event: Event associated with the operation.

        Returns:
            The `HandlerResult | None` result produced by the operation.

        Notes:
            Internal implementation detail for `_benchmark_event_workload.handle`. It delegates to `append`,
            `int` while keeping intermediate state local to the owning operation.
        """
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
        """Execute one request through the benchmark event workload.

        Args:
            _event: The event value used by the operation.
            action: Action request being processed.

        Returns:
            The `ActionResult` result produced by the operation.

        Notes:
            Internal implementation detail for `_benchmark_event_workload.execute`. It performs the local
            state transition directly and is not a stable extension boundary.
        """
        nonlocal actions_succeeded
        actions_succeeded += 1
        return ActionResult(action_id=action.action_id, success=True)

    async def publish(bus: EventBus, index: int) -> None:
        """Publish one event and wait for its dispatch result.

        Args:
            bus: The bus value used by the operation.
            index: The index value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_benchmark_event_workload.publish`. It delegates to
            `perf_counter`, `publish`, `append` while keeping intermediate state local to the owning
            operation.
        """
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


async def _measure_resident_state(
    operation: Callable[[], Awaitable[tuple[dict[str, Any], object]]],
) -> dict[str, Any]:
    """Measure state retained after a workload and a full Python collection.

    Args:
        operation: The operation value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_measure_resident_state`. It delegates to `collect`,
        `memory_info`, `start`, `perf_counter` while keeping intermediate state local to the owning
        operation.
    """

    gc.collect()
    process = psutil.Process()
    rss_before = process.memory_info().rss
    tracemalloc.start()
    started = time.perf_counter()
    try:
        state, owner = await operation()
        elapsed_seconds = time.perf_counter() - started
        gc.collect()
        retained_bytes, peak_bytes = tracemalloc.get_traced_memory()
        rss_after = process.memory_info().rss
        del owner
    finally:
        tracemalloc.stop()
    return {
        "elapsed_ms": elapsed_seconds * 1000,
        "throughput_events_per_second": state["processed_events"] / elapsed_seconds,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "rss_delta_bytes": rss_after - rss_before,
        "tracemalloc_retained_bytes": retained_bytes,
        "tracemalloc_peak_bytes": peak_bytes,
        **state,
    }


async def _event_bus_resident_workload(event_count: int, payload: str) -> tuple[dict[str, Any], object]:
    """Implement the event bus resident workload operation for the component.

    Args:
        event_count: The event count value used by the operation.
        payload: JSON-safe payload carried by the operation.

    Returns:
        The `tuple[dict[str, Any], object]` result produced by the operation.

    Notes:
        Internal implementation detail for `_event_bus_resident_workload`. It delegates to `subscribe`,
        `range`, `gather`, `publish` while keeping intermediate state local to the owning operation.
    """
    processed = 0

    async def handle(_event: EventEnvelope) -> None:
        """Handle one request through the event bus resident workload.

        Args:
            _event: The event value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_event_bus_resident_workload.handle`. It performs the local
            state transition directly and is not a stable extension boundary.
        """
        nonlocal processed
        processed += 1

    bus = EventBus(queue_capacity=1_024, max_concurrent_events=100)
    async with bus:
        bus.subscribe(handle, name="resident-benchmark")
        for offset in range(0, event_count, 100):
            await asyncio.gather(
                *(
                    bus.publish(
                        EventEnvelope(
                            id=f"resident-{index}",
                            runtime_id="benchmark",
                            adapter="benchmark",
                            bot_id="bot",
                            type="benchmark.resident",
                            conversation=ConversationRef(id=f"conversation-{index}"),
                            raw={"content": payload},
                        )
                    )
                    for index in range(offset, min(offset + 100, event_count))
                )
            )
    internal = cast(Any, bus)
    return (
        {
            "processed_events": processed,
            "outstanding_events": bus.outstanding,
            "retained_key_queues": len(internal._key_queues),
            "retained_key_workers": len(internal._key_workers),
            "retained_ingress_events": internal._ingress.qsize(),
        },
        bus,
    )


def _benchmark_bridge_session(
    bridge_id: str,
    *,
    subscriptions: tuple[str, ...],
) -> BridgeSession:
    """Implement the benchmark bridge session operation for the component.

    Args:
        bridge_id: Stable identifier for the bridge.
        subscriptions: The subscriptions value used by the operation.

    Returns:
        The `BridgeSession` result produced by the operation.

    Notes:
        Internal implementation detail for `_benchmark_bridge_session`. It delegates to `encode` while
        keeping intermediate state local to the owning operation.
    """
    return BridgeSession(
        bridge_id=bridge_id,
        session_id=f"session-{bridge_id}",
        manifest=BridgeManifest(
            bridge_id=bridge_id,
            access=BridgeAccess.LIMITED,
            subscriptions=subscriptions,
        ),
        peer_identity=f"peer-{bridge_id}".encode(),
    )


async def _broker_resident_workload(event_count: int, payload: str) -> tuple[dict[str, Any], object]:
    """Implement the broker resident workload operation for the component.

    Args:
        event_count: The event count value used by the operation.
        payload: JSON-safe payload carried by the operation.

    Returns:
        The `tuple[dict[str, Any], object]` result produced by the operation.

    Notes:
        Internal implementation detail for `_broker_resident_workload`. It delegates to
        `_benchmark_bridge_session`, `range`, `admit_event`, `offered_deliveries` while keeping
        intermediate state local to the owning operation.
    """
    ledger = BrokerLedger(terminal_capacity=RESIDENT_TERMINAL_CAPACITY)
    source = _benchmark_bridge_session("source", subscriptions=())
    target = _benchmark_bridge_session("target", subscriptions=("benchmark.resident",))
    sessions = (source, target)
    for index in range(event_count):
        event = ledger.admit_event(
            source,
            EventIngress(
                source_event_id=f"source-{index}",
                topic="benchmark.resident",
                ordering_key=f"conversation-{index}",
                payload={"content": f"{index:08d}:{payload}"},
            ),
            sessions,
        )
        delivery = ledger.offered_deliveries(event.kernel_event_id)[0]
        ledger.accept_delivery(target, delivery.delivery_id, delivery.lease_id)
        ledger.activate_delivery(target, delivery.delivery_id, delivery.lease_id)
        ledger.complete_delivery(target, delivery.delivery_id, delivery.lease_id, success=True)
    delivery_indexes, lanes = ledger.index_counts()
    return (
        {
            "processed_events": event_count,
            "active_events": ledger.active_count,
            "terminal_events": ledger.terminal_count,
            "terminal_capacity": RESIDENT_TERMINAL_CAPACITY,
            "terminal_content_bytes": ledger.terminal_content_bytes,
            "terminal_content_bytes_capacity": ledger.terminal_content_bytes_capacity,
            "delivery_indexes": delivery_indexes,
            "retained_lanes": lanes,
        },
        ledger,
    )


async def _benchmark_resident_workloads(*, event_count: int, payload_bytes: int) -> dict[str, Any]:
    """Implement the benchmark resident workloads operation for the component.

    Args:
        event_count: The event count value used by the operation.
        payload_bytes: Configured payload size, in bytes.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_benchmark_resident_workloads`. It delegates to
        `_measure_resident_state`, `_event_bus_resident_workload`, `_broker_resident_workload` while
        keeping intermediate state local to the owning operation.
    """
    payload = "x" * payload_bytes
    return {
        "event_bus": await _measure_resident_state(lambda: _event_bus_resident_workload(event_count, payload)),
        "broker": await _measure_resident_state(lambda: _broker_resident_workload(event_count, payload)),
    }


def _latency_summary(latencies: Sequence[float]) -> dict[str, float]:
    """Implement the latency summary operation for the component.

    Args:
        latencies: The latencies value used by the operation.

    Returns:
        The `dict[str, float]` result produced by the operation.

    Notes:
        Internal implementation detail for `_latency_summary`. It delegates to `sorted`, `median`,
        `ceil` while keeping intermediate state local to the owning operation.
    """
    if not latencies:
        raise ValueError("latency samples must not be empty")
    ordered = sorted(latencies)
    return {
        "median": statistics.median(ordered),
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
    }


async def _benchmark_functions(*, packs: int, functions_per_pack: int, calls: int) -> dict[str, Any]:
    """Implement the benchmark functions operation for the component.

    Args:
        packs: The packs value used by the operation.
        functions_per_pack: The functions per pack value used by the operation.
        calls: The calls value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_benchmark_functions`. It delegates to `discover_executors`,
        `_write_function_resources`, `perf_counter`, `load` while keeping intermediate state local to
        the owning operation.
    """
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
    """Create dispatcher.

    Args:
        workspace: The workspace value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_create_dispatcher`. It delegates to `load` while keeping
        intermediate state local to the owning operation.
    """
    FunctionDispatcher(ResourceCatalog.load(workspace))


async def _dispatch_once(workspace: Path, call: FunctionCall) -> None:
    """Dispatch once.

    Args:
        workspace: The workspace value used by the operation.
        call: The call value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_dispatch_once`. It delegates to `dispatch`, `load` while
        keeping intermediate state local to the owning operation.
    """
    await FunctionDispatcher(ResourceCatalog.load(workspace)).dispatch(call)


async def _dispatch_many(workspace: Path, call: FunctionCall, calls: int) -> None:
    """Dispatch many.

    Args:
        workspace: The workspace value used by the operation.
        call: The call value used by the operation.
        calls: The calls value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_dispatch_many`. It delegates to `load`, `range`, `dispatch`
        while keeping intermediate state local to the owning operation.
    """
    dispatcher = FunctionDispatcher(ResourceCatalog.load(workspace))
    for _ in range(calls):
        await dispatcher.dispatch(call)


async def _tracemalloc_peak(operation: Callable[[], Awaitable[None]]) -> int:
    """Implement the tracemalloc peak operation for the component.

    Args:
        operation: The operation value used by the operation.

    Returns:
        The `int` result produced by the operation.

    Notes:
        Internal implementation detail for `_tracemalloc_peak`. It delegates to `start`, `operation`,
        `get_traced_memory`, `stop` while keeping intermediate state local to the owning operation.
    """
    tracemalloc.start()
    try:
        await operation()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _write_function_resources(workspace: Path, packs: int, functions_per_pack: int) -> None:
    """Write function resources.

    Args:
        workspace: The workspace value used by the operation.
        packs: The packs value used by the operation.
        functions_per_pack: The functions per pack value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_write_function_resources`. It delegates to `range`,
        `append`, `mkdir`, `write_text` while keeping intermediate state local to the owning operation.
    """
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
    """Implement the aggregate samples operation for the component.

    Args:
        samples: The samples value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.
    """
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
        "resident_event_count": samples[0]["resident_event_count"],
        "resident_payload_bytes": samples[0]["resident_payload_bytes"],
        "samples": list(samples),
        "summary": _aggregate_value(
            [
                {
                    "startup_ms": sample["startup_ms"],
                    "peak_rss_bytes": sample["peak_rss_bytes"],
                    "workloads": sample["workloads"],
                    "functions": sample["functions"],
                    "resident": sample["resident"],
                }
                for sample in samples
            ]
        ),
    }


def _validate_samples(samples: Sequence[Mapping[str, Any]]) -> None:
    """Validate samples.

    Args:
        samples: The samples value used by the operation.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_validate_samples`. It delegates to `get`, `keys` while
        keeping intermediate state local to the owning operation.
    """
    expected = samples[0]
    if expected.get("profile") not in _BENCHMARK_PROFILES or "extension_manifest" not in expected:
        raise ValueError("benchmark samples are missing a valid profile manifest")
    for sample in samples:
        if sample.get("schema") != SCHEMA_VERSION:
            raise ValueError("benchmark sample has an unsupported schema")
        for key in (
            "platform",
            "python",
            "event_count",
            "resident_event_count",
            "resident_payload_bytes",
            "profile",
            "extension_manifest",
        ):
            if sample.get(key) != expected.get(key):
                raise ValueError(f"benchmark samples disagree on {key}")
        if sample.get("workloads", {}).keys() != expected.get("workloads", {}).keys():
            raise ValueError("benchmark samples disagree on workload groups")
        if sample.get("functions", {}).get("available") != expected.get("functions", {}).get("available"):
            raise ValueError("benchmark samples disagree on function executor availability")


def _aggregate_value(values: Sequence[Any]) -> Any:
    """Implement the aggregate value operation for the component.

    Args:
        values: The values value used by the operation.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_aggregate_value`. It delegates to `any`, `float`, `fmean`,
        `stdev` while keeping intermediate state local to the owning operation.
    """
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
    resident_events: int = DEFAULT_RESIDENT_EVENTS,
    resident_payload_bytes: int = DEFAULT_RESIDENT_PAYLOAD_BYTES,
    profile: BenchmarkProfile = "bare",
) -> dict[str, Any]:
    """Run samples.

    Args:
        samples: The samples value used by the operation.
        event_count: The event count value used by the operation.
        function_packs: The function packs value used by the operation.
        functions_per_pack: The functions per pack value used by the operation.
        function_calls: The function calls value used by the operation.
        resident_events: The resident events value used by the operation.
        resident_payload_bytes: Configured resident payload size, in bytes.
        profile: Named runtime or benchmark profile.

    Returns:
        The `dict[str, Any]` result produced by the operation.
    """
    profile = _validate_profile(profile)
    extension_manifest = _resolve_profile_manifest(profile)
    measurements = [
        _run_child_sample(
            event_count=event_count,
            function_packs=function_packs,
            functions_per_pack=functions_per_pack,
            function_calls=function_calls,
            resident_events=resident_events,
            resident_payload_bytes=resident_payload_bytes,
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
    resident_events: int = DEFAULT_RESIDENT_EVENTS,
    resident_payload_bytes: int = DEFAULT_RESIDENT_PAYLOAD_BYTES,
    profile: BenchmarkProfile = "bare",
    extension_manifest: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Run child sample.

    Args:
        event_count: The event count value used by the operation.
        function_packs: The function packs value used by the operation.
        functions_per_pack: The functions per pack value used by the operation.
        function_calls: The function calls value used by the operation.
        resident_events: The resident events value used by the operation.
        resident_payload_bytes: Configured resident payload size, in bytes.
        profile: Named runtime or benchmark profile.
        extension_manifest: The extension manifest value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_run_child_sample`. It delegates to `_validate_profile`,
        `_parse_extension_manifest`, `_serialize_extension_manifest`, `resolve` while keeping
        intermediate state local to the owning operation.
    """
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
        "--resident-events",
        str(resident_events),
        "--resident-payload-bytes",
        str(resident_payload_bytes),
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
    """Implement the peak rss bytes operation for the component.

    Returns:
        The `int` result produced by the operation.

    Notes:
        Internal implementation detail for `_peak_rss_bytes`. It delegates to `_windows_peak_rss`,
        `cast`, `import_module`, `int` while keeping intermediate state local to the owning operation.
    """
    if os.name == "nt":
        return _windows_peak_rss()
    resource = cast(Any, importlib.import_module("resource"))
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if platform.system() == "Darwin" else value * 1024


def _windows_peak_rss() -> int:
    """Implement the windows peak rss operation for the component.

    Returns:
        The `int` result produced by the operation.

    Notes:
        Internal implementation detail for `_windows_peak_rss`. It delegates to `sizeof`, `cast`,
        `byref`, `int` while keeping intermediate state local to the owning operation.
    """
    class ProcessMemoryCounters(ctypes.Structure):
        """Represent the process memory counters contract."""
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
    """Implement the parser operation for the component.

    Returns:
        The `argparse.ArgumentParser` result produced by the operation.

    Notes:
        Internal implementation detail for `_parser`. It delegates to `add_argument` while keeping
        intermediate state local to the owning operation.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=DEFAULT_EVENT_COUNT)
    parser.add_argument("--function-packs", type=int, default=DEFAULT_FUNCTION_PACKS)
    parser.add_argument("--functions-per-pack", type=int, default=DEFAULT_FUNCTIONS_PER_PACK)
    parser.add_argument("--function-calls", type=int, default=DEFAULT_FUNCTION_CALLS)
    parser.add_argument("--resident-events", type=int, default=DEFAULT_RESIDENT_EVENTS)
    parser.add_argument("--resident-payload-bytes", type=int, default=DEFAULT_RESIDENT_PAYLOAD_BYTES)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--profile", choices=_BENCHMARK_PROFILES, default="bare")
    parser.add_argument("--extension-manifest", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--sample", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, default=Path("benchmark.json"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line entry point.

    Args:
        argv: The argv value used by the operation.

    Returns:
        The `int` result produced by the operation.
    """
    args = _parser().parse_args(argv)
    if args.events < 100:
        _parser().error("--events must be at least 100")
    if args.function_packs < 1 or args.functions_per_pack < 1 or args.function_calls < 0:
        _parser().error("function benchmark counts must be positive, except --function-calls may be zero")
    if args.resident_events < 100 or args.resident_payload_bytes < 1:
        _parser().error("resident benchmark requires at least 100 events and one payload byte")
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
                resident_events=args.resident_events,
                resident_payload_bytes=args.resident_payload_bytes,
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
        resident_events=args.resident_events,
        resident_payload_bytes=args.resident_payload_bytes,
        profile=_validate_profile(args.profile),
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
