import json
import os
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot
from typing import List, Any, Union
import asyncio
import aiofiles

from .base import ExConfig, ExtraData


class Plugin:
    def __init__(self, fp, built_in):
        """
        :param fp: 路径
        """
        try:
            with open(os.path.join(fp, "config/manifest.json"), "r", encoding="utf-8") as file:
                data = json.load(file)
                self.pluginId = os.path.basename(fp)
                self.pluginName = data.get("name", "")
                self.defaultStats = data.get("default", True)
                self.path = fp
                self.built_in = built_in
        except BaseException:
            self.pluginId = os.path.basename(fp)
            self.pluginName = os.path.basename(fp)
            self.defaultStats = True
            self.path = fp
            self.built_in = built_in
        try:
            with open(os.path.join(fp, "config/docs.txt"), "r", encoding="utf-8") as file:
                self.pluginDocs = file.read()
        except BaseException:
            self.pluginDocs = "ErrorDocs"

    def __str__(self):
        return "<Plugin name=%s id=%s>" % (self.pluginName, self.pluginId)

    async def get_sub_docs(self, args, plugin_name: str):
        docs_path = os.path.join(self.path, "config/docs/" + "/".join(args) + ".txt")
        if os.path.exists(docs_path):
            async with aiofiles.open(docs_path, "r", encoding="utf-8") as asyncfile:
                return await asyncfile.read()
        else:
            return "未在插件 %s 中找到 %s 文档" % (plugin_name, ".".join(args))


def searchForPlugin(keyword) -> Any | None:
    """
    :param keyword:
    :return: None Plugin
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
            pluginList.append(Plugin(os.path.join(ExConfig.plugins_path, f), True))

    for e_f in os.listdir(ExConfig.nonebot_plugin_path):
        if os.path.exists(os.path.join(ExConfig.nonebot_plugin_path, e_f, "__init__.py")):
            pluginList.append(Plugin(os.path.join(ExConfig.nonebot_plugin_path, e_f), False))
    return pluginList


async def getPluginEnable(targetType, targetId, plugin: Plugin):
    enabledPlugin = await ExtraData.getData(targetType, targetId,
                                            key="enabled_plugin", default=list())
    bannedPlugin = await ExtraData.getData(targetType, targetId, key="banned_plugin", default=[])
    if plugin.defaultStats and plugin.pluginId not in bannedPlugin or not plugin.defaultStats and plugin.pluginId in enabledPlugin:
        return True
    else:
        return False
