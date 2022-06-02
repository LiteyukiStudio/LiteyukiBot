from nonebot.adapters.onebot.v11 import Bot, PrivateMessageEvent
from nonebot.rule import Rule
from nonebot.typing import T_State
from ...extraApi.base import ExtraData


@Rule
async def Online(bot: Bot, event: PrivateMessageEvent, state: T_State):
    state2 = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.online", default=False)
    return state2


@Rule
async def Not_Disconnect(bot: Bot, event: PrivateMessageEvent, state: T_State):
    """
    命令屏蔽器
    """
    if event.raw_message[0:4] in ["断开朋友", "屏蔽朋友", "连接朋友", "断绝朋友", "为朋友点歌"]:
        return False
    else:
        return True
