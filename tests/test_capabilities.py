from liteyukibot.capabilities import ADAPTER_CALL_API, KERNEL_CAPABILITIES, capability_definition


def test_kernel_capability_registry_exposes_stable_adapter_action_metadata() -> None:
    definition = capability_definition(ADAPTER_CALL_API)

    assert definition is not None
    assert definition.id == ADAPTER_CALL_API
    assert definition.owner == "kernel"
    assert definition in KERNEL_CAPABILITIES
    assert capability_definition("example.extension.capability") is None
