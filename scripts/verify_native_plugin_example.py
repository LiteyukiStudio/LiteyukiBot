"""Verify the installable Native/Cordis runtime facade example."""

from __future__ import annotations

from liteyukibot_example_plugin import observe_provider_event, runtime_facade_plugin

from liteyukibot import runtime_bindings


def main() -> int:
    requirements = runtime_facade_plugin.manifest.runtime_requirements
    bindings = runtime_bindings(observe_provider_event)
    if len(requirements) != 1 or len(bindings) != 1:
        raise RuntimeError("native plugin example did not declare one runtime facade")
    requirement = requirements[0]
    binding = bindings[0]
    if (requirement.runtime, requirement.api, requirement.version, requirement.optional) != (
        binding.runtime,
        binding.api,
        binding.version,
        binding.optional,
    ):
        raise RuntimeError("native plugin runtime declaration and manifest requirement do not match")
    if requirement.operations != ("snapshot",):
        raise RuntimeError(f"unexpected native plugin runtime operations: {requirement.operations!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
