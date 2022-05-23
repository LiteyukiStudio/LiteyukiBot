import aiofiles

from extraApi.base import ExtraData, ExConfig
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.internal.permission import Permission


@Permission
async def AUTHUSER(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    no_response = await ExtraData.get_global_data(key="no_response", default=[])
    if event.user_id in no_response:
        return False
    return await ExtraData.getData(ExtraData.User, targetId=event.user_id, key="enable", default=False)


@Permission
async def NOTAUTHUSER(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    no_response = await ExtraData.get_global_data(key="no_response", default=[])
    if event.user_id in no_response:
        return False
    return not await ExtraData.getData(ExtraData.User, targetId=event.user_id, key="enable", default=False)


@Permission
async def MASTER(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    try:
        async with aiofiles.open("README.md", encoding="utf-8") as file:
            if str(event.user_id) in await file.read():
                return True
            else:
                return False
    except BaseException:
        return False
