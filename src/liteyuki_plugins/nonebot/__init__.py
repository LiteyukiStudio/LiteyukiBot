import os.path
from pathlib import Path

import nonebot
from croterline.utils import IsMainProcess

from liteyuki.core import sub_process_manager
from liteyuki.plugin import PluginMetadata, PluginType

__plugin_meta__ = PluginMetadata(
    name="NoneBot2启动器",
    type=PluginType.APPLICATION,
)


def nb_run(*args, **kwargs):
    nonebot.init(**kwargs)

    from .nb_utils import driver_manager, adapter_manager
    driver_manager.init(config=kwargs)
    adapter_manager.init(kwargs)
    adapter_manager.register()
    nonebot.load_plugin(Path(os.path.dirname(__file__)) / "np_main")
    nonebot.run()


if IsMainProcess:
    from .dev_reloader import *
    bot = get_bot()

    sub_process_manager.add(
        name="nonebot", func=nb_run, **bot.config.get("nonebot", {})
    )
