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
    await liteyuki.finish("轻雪测试成功：%s" % bot.self_id)


@download_resource.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    pass


__plugin_meta__ = PluginMetadata(
    name="轻雪底层基础",
    description="以维持轻雪的正常运行，无法关闭",
    usage='•「liteyuki」测试Bot\n\n'
          '•「echo 消息」Bot复读\n\n'
          '•「下载资源/更新资源」解决自动资源下载失败的问题\n\n'
          '•「检查更新」检查当前版本是否为最新\n\n'
          '•「启用/停用自动更新」管理自动更新\n\n'
          '•「update BotQQ号」手动更新',
    extra={
        "liteyuki_plugin": True,
        "liteyuki_resource": resource
    }
)
