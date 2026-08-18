from liteyukibot_cordis import CordisPluginDefinition, Scope

from . import plugin


async def _activate(scope: Scope) -> None:
    adapter = await scope.use("liteyukibot.native_adapter")
    await adapter.activate(scope, plugin.manifest.id)  # type: ignore[attr-defined]


cordis_plugin = CordisPluginDefinition(plugin.manifest.id, _activate, manifest=plugin.manifest)

__all__ = ["cordis_plugin"]
