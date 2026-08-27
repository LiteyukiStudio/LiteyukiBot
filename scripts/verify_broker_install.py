"""Verify the standalone Broker distribution without the root composition package."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
from pathlib import Path

from liteyukibot_broker import BridgeAccess, BridgeManifest, EventIngress
from liteyukibot_broker.lyip import LyipFrame, LyipLane
from liteyukibot_broker.protocol import BridgeRegister, decode_broker_message, encode_broker_message

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    distribution = importlib.metadata.distribution("liteyukibot-v7-broker")
    if distribution.version != "7.0.0a14":
        raise RuntimeError(f"unexpected Broker distribution version: {distribution.version}")
    module = importlib.import_module("liteyukibot_broker")
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str) or Path(module_file).resolve().is_relative_to(SOURCE_ROOT):
        raise RuntimeError(f"workspace source import detected: {module_file}")
    if getattr(module, "__version__", None) != distribution.version:
        raise RuntimeError("Broker module version does not match its distribution")
    if importlib.util.find_spec("liteyukibot") is not None:
        raise RuntimeError("standalone Broker installation unexpectedly provides root composition")

    manifest = BridgeManifest(
        bridge_id="verifier",
        access=BridgeAccess.LIMITED,
        subscriptions=("message.created",),
    )
    frame = encode_broker_message(
        BridgeRegister(bridge_id=manifest.bridge_id, instance_token="token", manifest=manifest),
        generation=1,
        stream_id="control",
        sequence=0,
        lease_id="lease",
    )
    decoded = decode_broker_message(frame)
    if not isinstance(decoded, BridgeRegister) or decoded.manifest != manifest:
        raise RuntimeError("Broker control round-trip failed")
    ingress = EventIngress(topic="message.created", source_event_id="event-1", ordering_key="default", payload={})
    if LyipFrame(1, 1, LyipLane.BUSINESS, 610, "business", 0, "lease", b"{}").lane is not LyipLane.BUSINESS:
        raise RuntimeError("LYIP lane contract failed")
    if ingress.topic != "message.created":
        raise RuntimeError("Broker routing contract failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
