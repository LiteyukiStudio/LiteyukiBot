from extraApi.base import ExtraData
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.internal.permission import Permission


@Permission
async def AUTHUSER(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    return await ExtraData.getData(ExtraData.User, targetId=event.user_id, key="enable", default=False)


@Permission
async def NOTAUTHUSER(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    return not await ExtraData.getData(ExtraData.User, targetId=event.user_id, key="enable", default=False)
