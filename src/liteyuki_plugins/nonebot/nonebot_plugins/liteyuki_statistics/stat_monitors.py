import time

from nonebot import require
from nonebot.message import event_postprocessor

from src.utils.base.data import Database, LiteModel
from src.utils.base.ly_typing import v11, v12, satori

from src.utils.base.ly_typing import T_Bot, T_MessageEvent

from .common import MessageEventModel, msg_db
from src.utils import event as event_utils

require("nonebot_plugin_alconna")


async def general_event_monitor(bot: T_Bot, event: T_MessageEvent):
    pass
    # if isinstance(bot, satori.Bot):
    #     print("POST PROCESS SATORI EVENT")
    #     return await satori_event_monitor(bot, event)
    # elif isinstance(bot, v11.Bot):
    #     print("POST PROCESS V11 EVENT")
    #     return await onebot_v11_event_monitor(bot, event)


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

        message=[ms.__dict__ for ms in event.message],
        message_text=event.raw_message,
        message_type=event.message_type,
    )
    msg_db.save(mem)


@event_postprocessor
async def onebot_v12_event_monitor(bot: v12.Bot, event: v12.MessageEvent):
    if event.message_type == "group":
        event: v12.GroupMessageEvent
        group_id = str(event.group_id)
    else:
        group_id = ""
    mem = MessageEventModel(
        time=int(time.time()),
        bot_id=bot.self_id,
        adapter="onebot.v12",
        group_id=group_id,
        user_id=str(event.user_id),

        message_id=[ms.__dict__ for ms in event.message],

        message=event.message,
        message_text=event.raw_message,
        message_type=event.message_type,
    )
    msg_db.save(mem)


@event_postprocessor
async def satori_event_monitor(bot: satori.Bot, event: satori.MessageEvent):
    if event.guild is not None:
        event: satori.MessageEvent
        group_id = str(event.guild.id)
    else:
        group_id = ""

    mem = MessageEventModel(
        time=int(time.time()),
        bot_id=bot.self_id,
        adapter="satori",
        group_id=group_id,
        user_id=str(event.user.id),
        message_id=[ms.__str__() for ms in event.message],
        message=event.message,
        message_text=event.message.content,
        message_type=event_utils.get_message_type(event),
    )
    msg_db.save(mem)
