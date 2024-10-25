import os.path
from pathlib import Path


from croterline.utils import IsMainProcess

from liteyuki.core import sub_process_manager
from liteyuki.plugin import PluginMetadata, PluginType

__plugin_meta__ = PluginMetadata(
    name="MeloBot3",
    type=PluginType.APPLICATION,
)


def mb_run(*args, **kwargs):
    pass


if IsMainProcess:
    from liteyuki import get_bot

    bot = get_bot()
    sub_process_manager.add(
        name="melobot", func=mb_run, **bot.config.get("melobot", {})
    )
