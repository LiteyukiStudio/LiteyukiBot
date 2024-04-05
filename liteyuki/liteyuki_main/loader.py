import os.path

import nonebot.plugin

from liteyuki.utils import init_log
from liteyuki.utils.data_manager import InstalledPlugin, plugin_db
from liteyuki.utils.resource import load_resource_from_dir
from liteyuki.utils.tools import check_for_package

# 加载默认资源和语言
RESOURCE_PATH = "liteyuki/resources"
load_resource_from_dir(RESOURCE_PATH)
init_log()
# 加载其他资源包
if os.path.exists("resources"):
    for resource in os.listdir("resources"):
        load_resource_from_dir(os.path.join("resources", resource))

nonebot.plugin.load_plugins("liteyuki/plugins")
nonebot.plugin.load_plugins("plugins")

# 从数据库读取已安装的插件
installed_plugins: list[InstalledPlugin] = plugin_db.all(InstalledPlugin())
if installed_plugins:
    for installed_plugin in installed_plugins:
        if not check_for_package(installed_plugin.module_name):
            nonebot.logger.error(f"{installed_plugin.module_name} not installed, but in loading database. please run `npm fixup` in chat to reinstall it.")
        else:
            nonebot.load_plugin(installed_plugin.module_name)
