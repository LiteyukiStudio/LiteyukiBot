"""Kernel-owned capability identifiers for privileged cross-package surfaces."""

from __future__ import annotations

from dataclasses import dataclass

ADAPTER_CALL_API = "liteyukibot.adapter.call_api"
AGENT_HISTORY_CLEAR = "liteyukibot.agent.history.clear"
AGENT_PROMPT_SELECT = "liteyukibot.agent.prompt.select"
PERMISSION_SERVICE_NAME = "liteyukibot.permissions"
PERMISSION_SERVICE_MAJOR = 2


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """Stable metadata for a kernel-owned privileged capability."""

    id: str
    owner: str
    summary: str


KERNEL_CAPABILITIES = (
    CapabilityDefinition(
        id=ADAPTER_CALL_API,
        owner="kernel",
        summary="Allows a source-bound adapter API action.",
    ),
    CapabilityDefinition(
        id=AGENT_HISTORY_CLEAR,
        owner="kernel",
        summary="Allows clearing the caller's native agent conversation history.",
    ),
    CapabilityDefinition(
        id=AGENT_PROMPT_SELECT,
        owner="kernel",
        summary="Allows an LYF Tool to select a verified Agent prompt preset.",
    ),
)

_BY_ID = {capability.id: capability for capability in KERNEL_CAPABILITIES}


def capability_definition(capability: str) -> CapabilityDefinition | None:
    """Return metadata for a kernel-owned capability without rejecting extension tokens.

    Args:
        capability: The capability value used by the operation.

    Returns:
        The `CapabilityDefinition | None` result produced by the operation.
    """

    return _BY_ID.get(capability)


__all__ = [
    "ADAPTER_CALL_API",
    "AGENT_HISTORY_CLEAR",
    "AGENT_PROMPT_SELECT",
    "CapabilityDefinition",
    "KERNEL_CAPABILITIES",
    "PERMISSION_SERVICE_MAJOR",
    "PERMISSION_SERVICE_NAME",
    "capability_definition",
]
