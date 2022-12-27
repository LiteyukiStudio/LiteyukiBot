import os
from typing import Union
from nonebot.plugin import PluginMetadata
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.utils import run_sync
from .updater import *
from .resource import resource

echo = on_command(cmd="echo", permission=SUPERUSER)
liteyuki = on_command(cmd="liteyuki", permission=SUPERUSER)
download_resource = on_command(cmd="下载资源", aliases={"更新资源"}, permission=SUPERUSER)


@echo.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    await echo.send(args)


@liteyuki.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    await liteyuki.finish("轻雪测试成功：%s" % event.user_id)


@download_resource.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    await run_sync(os.system)("git pull")


__plugin_meta__ = PluginMetadata(
    name="轻雪底层插件",
    description="以维持轻雪的正常运行，无法关闭",
    usage="·使用'liteyuki'来测试Bot\n"
          "·使用'echo'来使Bot复读\n"
          "·使用'下载资源/更新资源'来解决自动资源下载失败的问题",
    extra={
        "liteyuki_plugin": True,
        "liteyuki_resource": resource
    }
)
