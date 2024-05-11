import time

from nonebot import require
from nonebot.message import event_postprocessor

from liteyuki.internal.base.data import Database, LiteModel
from liteyuki.internal.base.ly_typing import v11

from .common import MessageEventModel, msg_db

require("nonebot_plugin_alconna")





@event_postprocessor
async def onebot_v11_event_monitor(bot: v11.Bot, event: v11.MessageEvent):
    if event.message_type == "group":
        event: v11.GroupMessageEvent
        group_id = str(event.group_id)
    else:
        group_id = ""

    mem = MessageEventModel(
        time=int(time.time()),
        bot_id=bot.self_id,
        adapter="onebot.v11",
        group_id=group_id,
        user_id=str(event.user_id),

        message_id=str(event.message_id),

        message=event.message,
        message_text=event.raw_message,
        message_type=event.message_type,
    )
    msg_db.save(mem)
