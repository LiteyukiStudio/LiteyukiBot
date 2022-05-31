import re

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent, GROUP_ADMIN, GROUP_OWNER
from nonebot.permission import SUPERUSER
from nonebot.rule import Rule
from nonebot.typing import T_State

from .base import ExtraData, Log, Command
from .permission import MASTER


@Rule
async def IS_BADWORD(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    escaped = Command.escape(event.raw_message)
    if await (GROUP_ADMIN | GROUP_OWNER | SUPERUSER | MASTER)(bot, event):
        if re.match("(添加)|(删除)(全局)?违禁词", event.raw_message) is not None:
            return False
    global_badwords: dict = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="badword",
                                                    default={})
    session_badwords: dict = await ExtraData.getData(targetType=ExtraData.Group, targetId=ExtraData.getTargetId(event),
                                                     key="badword", default={})
    session = await Log.get_session_name(bot, event)
    for re_badword in global_badwords.get("re", []) + session_badwords.get("re", []):
        if re.search(re_badword, event.raw_message) is not None:
            await Log.plugin_log("kami.badword", "%s 触发了违禁词：[re]%s" % (session, re_badword))
            return True

    for eq_badword in global_badwords.get("eq", []) + session_badwords.get("eq", []):
        if eq_badword == event.raw_message:
            await Log.plugin_log("kami.badword", "%s 触发了违禁词：[eq]%s" % (session, eq_badword))
            return True

    return False


async def badwordFilter(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State, message=None) -> str:
    """
    消息发送时过滤一下是不是违禁词
    :param bot:
    :param event:
    :param state:
    :param message:
    :return:
    """
    escaped = Command.escape(message)
    msg = message
    global_badwords: dict = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="badword",
                                                    default={})
    session_badwords: dict = await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event),
                                                     key="badword", default={})
    session = await Log.get_session_name(bot, event)
    for re_badword in global_badwords.get("re", []) + session_badwords.get("re", []):
        if re.search(re_badword, message) is not None:
            message = message.replace(re.search(re_badword, message).group(0), len(re.search(re_badword, message).group(0)) * "*")

    for eq_badword in global_badwords.get("eq", []) + session_badwords.get("eq", []):
        if eq_badword == message:
            message = len(message) * "*"

    return message
