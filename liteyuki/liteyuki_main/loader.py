import os

import nonebot.plugin

from liteyuki.utils import init_log
from liteyuki.utils.data_manager import InstalledPlugin, plugin_db
from liteyuki.utils.resource import load_resource_from_dir
from liteyuki.utils.tools import check_for_package

THIS_PLUGIN_NAME = os.path.basename(os.path.dirname(__file__))
RESOURCE_PATH = "liteyuki/resources"
load_resource_from_dir(RESOURCE_PATH)

nonebot.plugin.load_plugins("liteyuki/plugins")
nonebot.plugin.load_plugins("plugins")

init_log()

installed_plugins = plugin_db.all(InstalledPlugin)
if installed_plugins:
    for installed_plugin in plugin_db.all(InstalledPlugin):
        if not check_for_package(installed_plugin.module_name):
            nonebot.logger.error(f"{installed_plugin.module_name} not installed, but in loading database. please run `npm fixup` in chat to reinstall it.")
        else:
            print(installed_plugin.module_name)
            nonebot.load_plugin(installed_plugin.module_name)
