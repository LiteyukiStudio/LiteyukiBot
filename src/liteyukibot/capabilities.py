"""Compatibility exports for kernel capability contracts."""

from liteyukibot_kernel.capabilities import (
    ADAPTER_CALL_API,
    AGENT_HISTORY_CLEAR,
    AGENT_PROMPT_SELECT,
    KERNEL_CAPABILITIES,
    PERMISSION_SERVICE_MAJOR,
    PERMISSION_SERVICE_NAME,
    CapabilityDefinition,
    capability_definition,
)

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
