from __future__ import annotations

import ast
from pathlib import Path

import liteyukibot_broker


def test_broker_package_is_root_independent() -> None:
    package_root = Path(liteyukibot_broker.__file__).resolve().parent
    source_files = tuple(package_root.glob("*.py"))
    imports: set[str] = set()
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module)
    assert all(name != "liteyukibot" and not name.startswith("liteyukibot.") for name in imports)


def test_broker_package_exposes_authenticated_peer_contract() -> None:
    from liteyukibot_broker import BridgeAccess, BridgeManifest

    manifest = BridgeManifest(bridge_id="test", access=BridgeAccess.LIMITED, subscriptions=("message.created",))
    assert manifest.bridge_id == "test"
