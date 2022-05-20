from typing import Union, Optional, Dict, Any

from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.internal.rule import Rule
from nonebot.message import event_preprocessor
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot.typing import T_State

from extraApi.base import Log, ExtraData

# 日志记录和模式回复
from extraApi.rule import NOT_IGNORED, NOT_BLOCKED


@event_preprocessor
async def auto_log_receive_handle(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], state: T_State):
    state2 = await ExtraData.get_global_data(key="enable_mode", default=1)

    if state2 == -1 and await (NOT_IGNORED & NOT_BLOCKED & to_me())(bot, event, state):
        if await SUPERUSER(bot, event):
            start = "[超级用户模式]"
        else:
            start = ""
        await bot.send(event, message="%s%s正在升级中" % (start, list(bot.config.nickname)[0]), at_sender=True)
    await Log.receive_message(bot, event)


# api记录
@Bot.on_called_api
async def record_api_calling(bot: Bot, exception: Optional[Exception], api: str, data: Dict[str, Any], result: Any):
    await Log.call_api_log(api, data, result)
