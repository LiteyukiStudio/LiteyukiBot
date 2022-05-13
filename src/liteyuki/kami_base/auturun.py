from typing import Union
from extraApi.base import Log
from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot.message import event_preprocessor


@event_preprocessor
async def auto_log_receive_handle(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent]):
    await Log.receive_message(bot, event)
