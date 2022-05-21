from typing import Union

from nonebot import on_message
from nonebot.adapters.onebot.v11 import PrivateMessageEvent, GroupMessageEvent, Bot
from nonebot.typing import T_State

from extraApi.rule import plugin_enable, NOT_IGNORED, NOT_BLOCKED, MODE_DETECT

ai = on_message(rule=plugin_enable("xiaoqi.thinking_matrix") & NOT_BLOCKED & NOT_IGNORED & MODE_DETECT, block=False)


@ai.handle()
async def ai_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    pass
