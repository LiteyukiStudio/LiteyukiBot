from typing import Union

from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot.internal.rule import Rule
from nonebot.typing import T_State

from src.liteyuki_api.utils import Command


def args_end_with(text: str) -> Rule:
    async def _rule(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
        args, kws = Command.formatToCommand(event.raw_message)
        args_text = Command.formatToString(*args)
        if text in args_text:
            if args_text.endswith(text):
                return True
            else:
                return False
        else:
            return False
    return Rule(_rule)