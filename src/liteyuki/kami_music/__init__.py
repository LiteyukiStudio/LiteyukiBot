from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot.typing import T_State
from nonebot.rule import startswith
from extraApi.base import Command, Balance
from extraApi.rule import plugin_enable, minimumCoin, NOT_BLOCKED, NOT_IGNORED, MODE_DETECT
from .musicApi import *

music = on_command(cmd="音乐", aliases={"点歌"}, priority=10,
                   rule=plugin_enable("kami.music") & minimumCoin(1, "无法点歌", startswith(("点歌", "音乐"))) & NOT_BLOCKED & NOT_IGNORED & MODE_DETECT
                   , block=True)


@music.handle()
async def musicHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    args, kw = Command.formatToCommand(cmd=event.raw_message)
    songName = Command.formatToString(*args[1:]).replace("%20", " ")
    plat = kw.get("plat", "163")
    songMessage = await getMusic(songName, plat)
    await music.send(Message(songMessage))
    await Balance.editCoinValue(user_id=event.user_id, delta=-1, reason="点歌")
