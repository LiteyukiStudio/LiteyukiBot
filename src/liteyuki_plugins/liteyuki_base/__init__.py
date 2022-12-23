from typing import Union
from nonebot.plugin import PluginMetadata
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

echo = on_command(cmd="echo", permission=SUPERUSER)
liteyuki = on_command(cmd="liteyuki", permission=SUPERUSER)


@echo.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    await echo.send(args)


@liteyuki.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    await liteyuki.finish("轻雪测试成功：%s" % event.user_id)


__plugin_meta__ = PluginMetadata(
    name="轻雪底层插件",
    description="以维持轻雪的正常运行",
    usage="无"
)
