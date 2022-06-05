from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot.params import CommandArg
from nonebot.typing import T_State
from nonebot.rule import startswith
from ...extraApi.base import Command, Balance
from ...extraApi.rule import minimumCoin
from .musicApi import *

music = on_command(cmd="音乐", aliases={"点歌"}, priority=10,
                   rule=minimumCoin(1, "无法点歌", startswith(("点歌", "音乐"))),
                   block=True)


@music.handle()
async def musicHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State, args: Message = CommandArg()):
    args, kw = Command.formatToCommand(str(args))
    songName = str(" ".join(args))
    plat = kw.get("plat", "163")
    songMessage = await getMusic(songName, plat)
    await music.send(Message(songMessage))
    await Balance.editCoinValue(user_id=event.user_id, delta=-1, reason="点歌")
