import os

import nonebot.plugin

from src.utils.data_manager import InstalledPlugin, plugin_db
from src.utils.resource import load_resource_from_dir

THIS_PLUGIN_NAME = os.path.basename(os.path.dirname(__file__))
RESOURCE_PATH = "src/resources"
load_resource_from_dir(RESOURCE_PATH)

nonebot.plugin.load_plugins("src/plugins")
nonebot.plugin.load_plugins("plugins")

installed_plugins = plugin_db.all(InstalledPlugin)
if installed_plugins:
    for install_plugin in plugin_db.all(InstalledPlugin):
        nonebot.load_plugin(install_plugin.module_name)