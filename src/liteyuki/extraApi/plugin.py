import json
import os
from typing import List, Any

from extraApi.base import ExConfig, ExtraData


class Plugin:
    def __init__(self, fp):
        """
        :param fp: 路径
        """
        try:
            with open(os.path.join(fp, "config/manifest.json"), "r", encoding="utf-8") as file:
                data = json.load(file)
                self.pluginId = data.get("id", "")
                self.pluginName = data.get("name", "")
                self.defaultStats = data.get("default", True)
        except BaseException:
            self.pluginId = "获取出错"
            self.pluginName = "获取出错"
            self.defaultStats = True
        try:
            with open(os.path.join(fp, "config/docs.txt"), "r", encoding="utf-8") as file:
                self.pluginDocs = file.read()
        except BaseException:
            self.pluginDocs = "文档文件不存在"

    def __str__(self):
        return "<Plugin name=%s id=%s>" % (self.pluginName, self.pluginId)


def searchForPlugin(keyword) -> Any | None:
    """
    :param keyword:
    :return: None PLugin
    """
    pluginList = getPluginList()
    for p in pluginList:
        if keyword == p.pluginName or keyword == p.pluginId:
            return p
    for p in pluginList:
        if keyword in p.pluginName:
            return p
    return None


def getPluginList() -> List[Plugin]:
    pluginList = []
    for f in os.listdir(ExConfig.plugins_path):
        if os.path.exists(os.path.join(ExConfig.plugins_path, f, "__init__.py")):
            pluginList.append(Plugin(os.path.join(ExConfig.plugins_path, f)))
    return pluginList


async def getPluginEnable(targetType, targetId, plugin: Plugin):
    enabledPlugin = await ExtraData.getData(targetType, targetId,
                                            key="enabled_plugin", default=list())
    bannedPlugin = await ExtraData.getData(targetType, targetId, key="banned_plugin", default=[])
    if plugin.defaultStats and plugin.pluginId not in bannedPlugin or not plugin.defaultStats and plugin.pluginId in enabledPlugin:
        return True
    else:
        return False
