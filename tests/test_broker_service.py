from __future__ import annotations

import asyncio
import socket
import threading
from typing import Any, cast

import pytest
import zmq.asyncio
from pydantic import ValidationError

import liteyukibot.cli as cli
from liteyukibot.broker.peer import BridgeRegistrationError
from liteyukibot.broker.protocol import (
    ActionResourceDeclaration,
    BridgeAccess,
    BridgeManifest,
    BridgeRegister,
    BridgeRegistered,
    BridgeRejected,
    RuntimeApiDeclaration,
    decode_broker_message,
    encode_broker_message,
)
from liteyukibot.broker.service import (
    BridgeCatalog,
    BridgeDefinition,
    BridgeLauncher,
    BridgeSupportGrade,
    BrokerService,
    _AuthoritativePeerService,
    resolve_secret_references,
)
from liteyukibot.config import AppSettings, BrokerToolSettings
from liteyukibot.lyip import LyipLane, ZmqLyipRouter


def _settings() -> AppSettings:
    return AppSettings.model_validate(
        {
            "config_version": 6,
            "broker": {
                "bridges": {
                    "nonebot": {
                        "kind": "nonebot",
                        "token_secret": "broker.nonebot.token",
                        "access": "limited",
                        "subscriptions": ["message.created"],
                        "action_resources": [{"kind": "message.send", "resource_prefix": "bot:nonebot:"}],
                        "options": {"adapter": "onebot", "features": ["messages"], "nested": {"enabled": True}},
                    }
                }
            },
        }
    )


def test_broker_settings_are_v6_only_and_authoritative() -> None:
    settings = _settings()

    assert settings.broker.bridges["nonebot"].access == "limited"
    assert settings.broker.bridges["nonebot"].model_dump(mode="json")["options"] == {
        "adapter": "onebot",
        "features": ["messages"],
        "nested": {"enabled": True},
    }
    with pytest.raises(TypeError):
        settings.broker.bridges["nonebot"].options["nested"]["enabled"] = False  # type: ignore[index]
    with pytest.raises(ValidationError, match="config_version must be 6"):
        AppSettings(config_version=4)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AppSettings.model_validate({"config_version": 6, "runtimes": {}})
    with pytest.raises(ValidationError, match="loopback"):
        AppSettings.model_validate({"config_version": 6, "broker": {"endpoint": "tcp://0.0.0.0:20217"}})
    with pytest.raises(ValidationError, match="duplicate 'limited' ownership"):
        AppSettings.model_validate(
            {
                "config_version": 6,
                "broker": {
                    "bridges": {
                        "one": {
                            "kind": "one",
                            "token_secret": "one",
                            "action_resources": [{"kind": "message.send", "resource_prefix": "bot:"}],
                        },
                        "two": {
                            "kind": "two",
                            "token_secret": "two",
                            "action_resources": [{"kind": "message.send", "resource_prefix": "bot:"}],
                        },
                    }
                },
            }
        )
    full_and_limited = AppSettings.model_validate(
        {
            "config_version": 6,
            "broker": {
                "bridges": {
                    "owner": {
                        "kind": "owner",
                        "token_secret": "owner",
                        "access": "full",
                        "action_resources": [{"kind": "message.send", "resource_prefix": "bot:"}],
                    },
                    "fallback": {
                        "kind": "fallback",
                        "token_secret": "fallback",
                        "access": "limited",
                        "action_resources": [{"kind": "message.send", "resource_prefix": "bot:"}],
                    },
                }
            },
        }
    )
    assert full_and_limited.broker.bridges["owner"].access == "full"
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        AppSettings.model_validate(
            {
                "config_version": 6,
                "broker": {
                    "bridges": {
                        "one": {
                            "kind": "one",
                            "token_secret": "one",
                            "action_resources": [
                                {"kind": "message.send", "resource_prefix": "bot:"},
                                {"kind": "message.send", "resource_prefix": "bot:"},
                            ],
                        }
                    }
                },
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        (
            "tools",
            [{"id": "kernel.tool", "description": "Tool", "input_schema": {"type": "object"}}],
        ),
        ("controls", ["kernel.control"]),
    ),
)
def test_kernel_bridge_rejects_tool_and_control_ownership(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match="kernel bridge must not declare"):
        AppSettings.model_validate(
            {
                "config_version": 6,
                "broker": {
                    "bridges": {
                        "kernel": {
                            "kind": "kernel",
                            "token_secret": "broker.kernel.token",
                            "access": "full",
                            "subscriptions": ["message.created"],
                            field: value,
                        }
                    }
                },
            }
        )


def test_secret_references_resolve_recursively_without_accepting_ambiguous_objects() -> None:
    resolved = resolve_secret_references(
        {"token": {"secret_ref": "adapter-token"}, "nested": ({"secret_ref": "other"},)},
        {"adapter-token": "secret-value", "other": "other-value"},
    )

    assert resolved == {"token": "secret-value", "nested": ("other-value",)}
    with pytest.raises(BridgeRegistrationError, match="absent from the vault"):
        resolve_secret_references({"token": {"secret_ref": "missing"}}, {})
    with pytest.raises(BridgeRegistrationError, match="cannot contain other fields"):
        resolve_secret_references({"token": {"secret_ref": "adapter-token", "format": "raw"}}, {})


def test_authoritative_service_rejects_token_matched_manifest_mismatch() -> None:
    configured = BridgeManifest(
        bridge_id="nonebot",
        access=BridgeAccess.LIMITED,
        subscriptions=("message.created",),
        action_resources=(ActionResourceDeclaration(kind="message.send", resource_prefix="bot:nonebot:"),),
    )
    service = _AuthoritativePeerService(
        manifests={"nonebot": configured},
        instance_tokens={"nonebot": "secret"},
        generation=1,
        active_capacity=1024,
        terminal_capacity=16384,
        terminal_ttl_seconds=3600,
        delivery_timeout_seconds=30,
    )
    request = BridgeRegister(
        bridge_id="nonebot",
        instance_token="secret",
        manifest=BridgeManifest(bridge_id="nonebot", access=BridgeAccess.LIMITED),
    )
    frame = encode_broker_message(
        request,
        generation=1,
        stream_id="bridge:nonebot:control",
        sequence=0,
        lease_id="registration",
    )

    reply = decode_broker_message(service.handle_control(b"nonebot-peer", frame))

    assert isinstance(reply, BridgeRejected)
    assert reply.code == "manifest_mismatch"


def test_authoritative_service_preserves_dynamic_runtime_catalog_fingerprint() -> None:
    configured = BridgeManifest(
        bridge_id="provider",
        access=BridgeAccess.LIMITED,
    )
    declaration = RuntimeApiDeclaration(
        runtime_kind="example",
        namespace="experimental",
        operation="echo",
        version="1.0",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    service = _AuthoritativePeerService(
        manifests={"provider": configured},
        instance_tokens={"provider": "secret"},
        generation=1,
        active_capacity=1024,
        terminal_capacity=16384,
        terminal_ttl_seconds=3600,
        delivery_timeout_seconds=30,
        dynamic_runtime_api_bridge_ids=frozenset({"provider"}),
        runtime_kinds={"provider": "example"},
    )
    manifest = BridgeManifest(
        bridge_id="provider",
        access=BridgeAccess.LIMITED,
        runtime_apis=(declaration,),
    )
    frame = encode_broker_message(
        BridgeRegister(bridge_id="provider", instance_token="secret", manifest=manifest),
        generation=1,
        stream_id="bridge:provider:control",
        sequence=0,
        lease_id="registration",
    )

    reply = decode_broker_message(service.handle_control(b"provider-peer", frame))

    assert isinstance(reply, BridgeRegistered)
    assert service.sessions[0].manifest.runtime_api_fingerprint == manifest.runtime_api_fingerprint


def test_authoritative_service_allows_only_dynamic_kernel_tool_and_control_fields() -> None:
    configured = BridgeManifest(
        bridge_id="kernel",
        access=BridgeAccess.FULL,
        subscriptions=("message.created",),
    )
    service = _AuthoritativePeerService(
        manifests={"kernel": configured},
        instance_tokens={"kernel": "secret"},
        generation=1,
        active_capacity=1024,
        terminal_capacity=16384,
        terminal_ttl_seconds=3600,
        delivery_timeout_seconds=30,
        dynamic_manifest_bridge_ids=frozenset({"kernel"}),
    )
    request = BridgeRegister(
        bridge_id="kernel",
        instance_token="secret",
        manifest=configured.model_copy(update={"controls": ("agent.function.catalog",)}),
    )
    frame = encode_broker_message(
        request,
        generation=1,
        stream_id="bridge:kernel:control",
        sequence=0,
        lease_id="registration",
    )

    reply = decode_broker_message(service.handle_control(b"kernel-peer", frame))

    assert isinstance(reply, BridgeRegistered)


def test_broker_service_projects_configured_tool_declarations_into_authoritative_manifest() -> None:
    tool = {
        "id": "agent.sandbox.file.read",
        "description": "Read a file",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        "capabilities": ["fs.read"],
    }
    settings = AppSettings.model_validate(
        {
            "config_version": 6,
            "broker": {
                "bridges": {
                    "sandbox": {
                        "kind": "agent-sandbox",
                        "token_secret": "broker.sandbox.token",
                        "tools": [tool],
                    }
                }
            },
        }
    )
    assert settings.broker.bridges["sandbox"].tools == (
        BrokerToolSettings.model_validate(tool),
    )
    service = BrokerService(settings, {"sandbox": "secret"})
    try:
        authoritative = cast(_AuthoritativePeerService, service.server.service)
        manifest = authoritative._manifests["sandbox"]
        assert manifest.tools[0].id == tool["id"]
        assert manifest.tools[0].capabilities == ("fs.read",)
        assert manifest.tools[0].input_schema == tool["input_schema"]
    finally:
        service.server.close()


def test_broker_service_resolves_every_configured_vault_token() -> None:
    settings = _settings()

    with pytest.raises(ValueError, match="every configured bridge"):
        BrokerService(settings, {})


def test_tcp_router_uses_adjacent_control_and_business_ports() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    context = zmq.asyncio.Context()
    router = ZmqLyipRouter(
        context=context,
        endpoint=f"tcp://127.0.0.1:{port}",
        generation=1,
        business_hwm=10,
        control_hwm=10,
    )
    try:
        assert router.endpoints[LyipLane.CONTROL] == f"tcp://127.0.0.1:{port}"
        assert router.endpoints[LyipLane.BUSINESS] == f"tcp://127.0.0.1:{port + 1}"
    finally:
        router.close()
        context.term()


def test_cli_exposes_standalone_broker_and_bridge_commands() -> None:
    assert cli.build_parser().parse_args(["broker", "run"]).broker_command == "run"
    args = cli.build_parser().parse_args(["bridge", "run", "nonebot"])
    assert (args.bridge_command, args.bridge_id) == ("run", "nonebot")


@pytest.mark.asyncio
async def test_business_pump_survives_registration_rejection() -> None:
    class Server:
        calls = 0

        async def serve_business_once(self) -> None:
            self.calls += 1
            if self.calls == 1:
                raise BridgeRegistrationError("unregistered")
            raise asyncio.CancelledError

    service = object.__new__(BrokerService)
    server = Server()
    service.server = cast(Any, server)

    with pytest.raises(asyncio.CancelledError):
        await service._serve_business()

    assert server.calls == 2


@pytest.mark.asyncio
async def test_sync_bridge_launcher_runs_off_the_asyncio_thread() -> None:
    catalog = BridgeCatalog()
    caller_thread = threading.get_ident()
    launch_thread: list[int] = []

    def launch(_settings: AppSettings, _bridge_id: str, _token: str) -> None:
        launch_thread.append(threading.get_ident())

    catalog.discover = lambda: {  # type: ignore[method-assign]
        "nonebot": BridgeDefinition(
            kind="nonebot",
            grade=BridgeSupportGrade.STABLE,
            distribution="liteyukibot-v7-runtime-nonebot",
            launch=cast(BridgeLauncher, launch),
        )
    }

    await catalog.launch(_settings(), "nonebot", "secret")

    assert launch_thread
    assert launch_thread[0] != caller_thread


@pytest.mark.asyncio
async def test_catalog_rejects_the_in_process_kernel_bridge() -> None:
    settings = AppSettings.model_validate(
        {
            "config_version": 6,
            "broker": {
                "bridges": {
                    "kernel": {
                        "kind": "kernel",
                        "token_secret": "broker.kernel.token",
                        "access": "full",
                        "subscriptions": ["message.created"],
                    }
                }
            },
        }
    )

    with pytest.raises(RuntimeError, match="reserved kernel bridge"):
        await BridgeCatalog().launch(settings, "kernel", "secret")


def test_catalog_rejects_invalid_bridge_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    class EntryPoint:
        name = "nonebot"

        @staticmethod
        def load() -> object:
            return lambda: BridgeDefinition(
                kind="astrbot",
                grade=BridgeSupportGrade.EXPERIMENTAL,
                distribution="liteyukibot-v7-runtime-nonebot",
                launch=cast(BridgeLauncher, lambda _settings, _bridge_id, _token: None),
            )

    monkeypatch.setattr("liteyukibot.broker.service.metadata.entry_points", lambda *, group: (EntryPoint(),))

    with pytest.raises(RuntimeError, match="mismatched bridge kind"):
        BridgeCatalog().discover()


def test_catalog_rejects_definition_claiming_another_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    class Distribution:
        metadata = {"Name": "liteyukibot-v7-runtime-nonebot"}

    class EntryPoint:
        name = "nonebot"
        dist = Distribution()

        @staticmethod
        def load() -> object:
            return lambda: BridgeDefinition(
                kind="nonebot",
                grade=BridgeSupportGrade.STABLE,
                distribution="example-bridge",
                launch=cast(BridgeLauncher, lambda _settings, _bridge_id, _token: None),
            )

    monkeypatch.setattr("liteyukibot.broker.service.metadata.entry_points", lambda *, group: (EntryPoint(),))

    with pytest.raises(RuntimeError, match="declares distribution"):
        BridgeCatalog().discover()
