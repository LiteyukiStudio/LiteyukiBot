from typing import Union

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent, PrivateMessageEvent
from extraApi.rule import pluginEnable
from extraApi.base import ExtraData, Command

set_call = on_command(cmd="设置称呼", rule=pluginEnable("kami.plugin_manager"), priority=10, block=True)
set_nick = on_command(cmd="设置昵称", rule=pluginEnable("kami.plugin_manager"), priority=10, block=True)


@set_call.handle()
async def set_call_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    call = Command.formatToCommand(event.raw_message)[0][1]
    await ExtraData.set_user_data(user_id=event.user_id, key="my.bot_call_user", value=call)
    await set_call.send(message="机器人对用户的称呼设置成功：%s" % call, at_sender=True)


@set_nick.handle()
async def set_nick_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    call = Command.formatToCommand(event.raw_message)[0][1]
    await ExtraData.set_user_data(user_id=event.user_id, key="my.user_call_bot", value=call)
    await set_nick.send(message="用户对机器人的称呼设置成功：%s" % call, at_sender=True)
