from __future__ import annotations

import ast
from pathlib import Path

from liteyukibot.bridge_contracts import (
    BridgeDefinition,
    BridgeLauncher,
    BridgeSupportGrade,
    ManagedFacetInstaller,
    ManagedFacetProbe,
)
from liteyukibot.broker import (
    BridgeDefinition as BrokerBridgeDefinition,
)
from liteyukibot.broker import (
    BridgeLauncher as BrokerBridgeLauncher,
)
from liteyukibot.broker import (
    BridgeSupportGrade as BrokerBridgeSupportGrade,
)
from liteyukibot.broker.service import (
    BridgeDefinition as ServiceBridgeDefinition,
)
from liteyukibot.broker.service import (
    BridgeLauncher as ServiceBridgeLauncher,
)
from liteyukibot.broker.service import (
    BridgeSupportGrade as ServiceBridgeSupportGrade,
)
from liteyukibot.managed_plugins import ManagedFacetInstaller as CompatibleManagedFacetInstaller
from liteyukibot.managed_plugins import ManagedFacetProbe as CompatibleManagedFacetProbe

_ROOT = Path(__file__).parents[1]


def test_bridge_contract_exports_share_one_canonical_identity() -> None:
    assert BrokerBridgeDefinition is BridgeDefinition is ServiceBridgeDefinition
    assert BrokerBridgeLauncher is BridgeLauncher is ServiceBridgeLauncher
    assert BrokerBridgeSupportGrade is BridgeSupportGrade is ServiceBridgeSupportGrade
    assert CompatibleManagedFacetInstaller is ManagedFacetInstaller
    assert CompatibleManagedFacetProbe is ManagedFacetProbe


def test_broker_contract_boundary_does_not_import_plugin_manager_implementation() -> None:
    service_imports = _relative_imports(_ROOT / "src" / "liteyukibot" / "broker" / "service.py")
    compatibility_imports = _relative_imports(_ROOT / "src" / "liteyukibot" / "managed_plugins.py")
    installer_imports = _relative_imports(_ROOT / "src" / "liteyukibot" / "plugin_install.py")

    assert (2, "managed_plugins") not in service_imports
    assert (2, "plugin_store") not in service_imports
    assert (1, "plugin_store") not in compatibility_imports
    assert not any(module == "broker" or module.startswith("broker.") for _level, module in installer_imports if module)


def _relative_imports(path: Path) -> set[tuple[int, str | None]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {(node.level, node.module) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
