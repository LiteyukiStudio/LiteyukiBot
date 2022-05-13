from extraApi.base import Command, ExtraData, Balance
from extraApi.rule import pluginEnable, minimumCoin
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot, Message, MessageSegment
from nonebot.typing import T_State
from typing import Union
from .musicApi import *

music = on_command(cmd="音乐", aliases={"点歌"}, priority=10, rule=pluginEnable("kami.music") & minimumCoin(1), block=True)


@music.handle()
async def musicHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    args, kw = Command.formatToCommand(cmd=event.raw_message)
    songName = Command.formatToString(*args[1:]).replace("%20", " ")
    plat = kw.get("plat", await ExtraData.getData(targetType=ExtraData.User, targetId=event.user_id, key="kami.music.plat", default="163"))
    songMessage = await getMusic(songName, plat)
    await ExtraData.setData(targetType=ExtraData.User, targetId=event.user_id, key="kami.music.plat", value=plat)
    await music.send(Message(songMessage))
    await Balance.editCoinValue(user_id=event.user_id, delta=-1, reason="点歌")
