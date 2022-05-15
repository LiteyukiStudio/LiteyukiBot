from typing import Union

from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot.typing import T_State

from extraApi.base import Log, ExtraData
from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot.message import event_preprocessor


@event_preprocessor
async def auto_log_receive_handle(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], state: T_State):
    state2 = await ExtraData.get_global_data(key="enable_mode", default=1)
    if state2 == -1 and await to_me()(bot, event, state):
        if await SUPERUSER(bot, event):
            start = "[超级用户模式]"
        else:
            start = ""
        await bot.send(event, message="%s%s正在升级中" % (start, list(bot.config.nickname)[0]), at_sender=True)
    await Log.receive_message(bot, event)
